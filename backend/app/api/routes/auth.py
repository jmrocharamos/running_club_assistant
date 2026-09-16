from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import FRONTEND_BASE_URL, PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
from app.core.security import (
    clear_auth_cookie,
    create_access_token,
    generate_reset_token,
    get_current_user,
    hash_password,
    hash_reset_token,
    set_auth_cookie,
    verify_password,
)
from app.db.session import get_db
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.schemas.user import UserRead
from app.services.email_sender import EmailSender, get_email_sender

router = APIRouter(prefix="/auth", tags=["Auth"])

GENERIC_FORGOT_PASSWORD_MESSAGE = (
    "If an account exists for that email, a reset link has been sent."
)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(
    register_data: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    if db.scalar(select(User).where(User.email == register_data.email)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    if db.scalar(select(User).where(User.username == register_data.username)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )

    user = User(
        username=register_data.username,
        email=register_data.email,
        full_name=register_data.full_name,
        password_hash=hash_password(register_data.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    set_auth_cookie(response, token)

    return user


@router.post("/login", response_model=UserRead)
def login(
    login_data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == login_data.email))

    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user.id)
    set_auth_cookie(response, token)

    return user


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
):
    clear_auth_cookie(response)
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    forgot_data: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    email_sender: EmailSender = Depends(get_email_sender),
):
    """Issue a reset link for known users and return the same message for every email."""
    user = db.scalar(select(User).where(User.email == forgot_data.email))

    if user:
        raw_token, token_hash = generate_reset_token()
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
        db.add(reset_token)
        db.commit()

        reset_url = f"{FRONTEND_BASE_URL}/reset-password?token={raw_token}"
        email_sender.send_password_reset_email(user.email, reset_url)

    return MessageResponse(message=GENERIC_FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    reset_data: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """Validate an unused reset token, then save the new password and mark the token used."""
    token_hash = hash_reset_token(reset_data.token)
    reset_token = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
        )
    )

    now = datetime.now(timezone.utc)

    if (
        not reset_token
        or reset_token.used_at is not None
        or reset_token.expires_at < now
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired",
        )

    user = db.get(User, reset_token.user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired",
        )

    user.password_hash = hash_password(reset_data.new_password)
    reset_token.used_at = now
    db.commit()

    return MessageResponse(message="Password updated. You can now log in.")


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    change_data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(change_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.password_hash = hash_password(change_data.new_password)
    db.commit()

    return MessageResponse(message="Password updated")
