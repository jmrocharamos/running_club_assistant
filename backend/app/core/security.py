import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import (
    AUTH_COOKIE_NAME,
    IS_PRODUCTION,
    JWT_ALGORITHM,
    JWT_EXPIRE_MINUTES,
    JWT_SECRET_KEY,
)
from app.db.session import get_db
from app.models.user import User

_password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against its stored hash; treat verification errors as a mismatch."""
    try:
        return _password_hasher.verify(password, password_hash)
    except Exception:
        return False


def create_access_token(user_id: UUID) -> str:
    """Sign an expiring session token identifying the user by UUID."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> UUID:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        ) from error
    except jwt.InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        ) from error

    subject = payload.get("sub")

    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    return UUID(subject)


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=JWT_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax",
    )


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Resolve the session cookie to a database user or reject unauthenticated access."""
    token = request.cookies.get(AUTH_COOKIE_NAME)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_id = decode_access_token(token)
    user = db.get(User, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return user


def hash_reset_token(raw_token: str) -> str:
    """Hash a reset token for storage and lookup without saving the usable token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_reset_token() -> tuple[str, str]:
    """Return a reset token for the link and its hash for database storage."""
    raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_reset_token(raw_token)
