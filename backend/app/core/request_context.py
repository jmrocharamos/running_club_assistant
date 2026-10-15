"""Request-local demo controls; normal account requests retain their settings."""

from contextvars import ContextVar
from datetime import datetime, timezone

from sqlalchemy import event
from sqlalchemy.orm import Session

demo_deadline: ContextVar[float | None] = ContextVar("demo_deadline", default=None)


def remaining_seconds():
    deadline = demo_deadline.get()
    if deadline is None:
        return None
    remaining = deadline - datetime.now(timezone.utc).timestamp()
    if remaining <= 0:
        from app.services.demo_session_service import expired
        raise expired()
    return remaining


@event.listens_for(Session, "before_commit")
def refuse_expired_demo_write(session):
    remaining_seconds()
