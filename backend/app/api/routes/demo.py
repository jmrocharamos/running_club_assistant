from datetime import datetime, timedelta
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy.orm import Session

from app.core.config import AUTH_COOKIE_NAME, JWT_SECRET_KEY, JWT_ALGORITHM, IS_PRODUCTION
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserRead
from app.services import demo_session_service as demos

router = APIRouter(prefix="/demo", tags=["Demo"])
BROWSER_COOKIE_NAME = "demo_browser"


def browser_identity(request: Request) -> str:
    """Identify a browser without grouping everyone behind a deployment proxy."""
    try:
        payload = jwt.decode(request.cookies.get(BROWSER_COOKIE_NAME, ""), JWT_SECRET_KEY,
                             algorithms=[JWT_ALGORITHM], options={"require": ["exp", "kind", "nonce"]})
        if payload["kind"] == "demo_browser":
            return UUID(payload["nonce"]).hex
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
        pass
    return uuid4().hex


@router.get('/config')
def demo_config():
    return {"enabled": demos.DEMO_ENABLED, "minutes": demos.DEMO_MINUTES, "limits": demos.LIMITS}


@router.post('/start', response_model=UserRead)
def start_demo(request: Request, response: Response, db: Session = Depends(get_db)):
    existing = request.cookies.get(AUTH_COOKIE_NAME)
    if existing:
        try:
            payload = jwt.decode(existing, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        except jwt.InvalidTokenError:
            payload = None
        if payload:
            if payload.get("kind") != "demo":
                raise HTTPException(409, "You are already signed in. Use your account or open a private window for the demo.")
            user = db.get(User, payload['sub'])
            demo = demos.metadata(db, user.id) if user else None
            demos.assert_active(demo)
            user.is_demo = True
            user.demo_expires_at = demo['expires_at']
            return user
    visitor = browser_identity(request)
    user, demo = demos.start(db, visitor)
    # This marker only identifies a browser for start limits; it has no user
    # subject and cannot authenticate. Renew it across the rolling hour window.
    browser_token = jwt.encode({"kind": "demo_browser", "nonce": visitor,
                                "exp": demos.now() + timedelta(hours=1)},
                               JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    response.set_cookie(BROWSER_COOKIE_NAME, browser_token, max_age=3600, httponly=True,
                        secure=IS_PRODUCTION, samesite='lax', path='/')
    expires = datetime.fromisoformat(demo['expires_at'])
    token = jwt.encode({"sub": str(user.id), "kind": "demo", "iat": demos.now(), "exp": expires}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    response.set_cookie(AUTH_COOKIE_NAME, token, max_age=900, httponly=True, secure=IS_PRODUCTION, samesite='lax', path='/')
    # Informational marker for routing after the access cookie expires. It
    # never grants access; the signed token and stored expiry are authoritative.
    response.set_cookie('demo_expires_at', demo['expires_at'], max_age=3600, secure=IS_PRODUCTION, samesite='lax', path='/')
    user.is_demo = True
    user.demo_expires_at = demo['expires_at']
    return user


@router.get('/status')
def demo_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    demo = demos.metadata(db, user.id)
    if demo is None:
        raise HTTPException(404, "No demo session is active.")
    demos.assert_active(demo)
    return demos.status(demo)
