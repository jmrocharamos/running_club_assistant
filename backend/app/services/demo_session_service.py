"""Short-lived anonymous runners backed by existing user and memory rows."""

from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import os
import re
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select, text

from app.core.config import JWT_SECRET_KEY
from app.models.coach_memory import CoachMemory
from app.models.feedback import Feedback
from app.models.password_reset_token import PasswordResetToken
from app.models.recommendation import Recommendation
from app.models.survey import Survey
from app.models.user import User
from app.models.enums import RecommendationType
from app.schemas.survey import RunningPlanSurveyAnswers
from app.services.coach_memory_manager import get_or_create_coach_memory

DEMO_ENABLED = os.getenv("DEMO_ENABLED", "false").lower() == "true"
DEMO_MINUTES = 15
LIMITS = {"chat": 5, "plans": 1, "revisions": 1, "summaries": 1, "requests": 250}
KEY = "demo_session"


def now():
    return datetime.now(timezone.utc)


def expired():
    return HTTPException(401, {"reason": "demo_expired", "message": "Your 15-minute demo has ended."})


def metadata(db, user_id):
    summary = db.scalar(select(CoachMemory.summary).where(CoachMemory.user_id == user_id))
    return (summary or {}).get(KEY)


def assert_active(demo):
    if not demo or datetime.fromisoformat(demo["expires_at"]) <= now():
        raise expired()


def sample_answers():
    return RunningPlanSurveyAnswers.model_validate({
        "goal": "build_consistency", "target_distance": "none", "plan_duration_weeks": 4,
        "plan_start_date": date.today().isoformat(), "target_event_date": None,
        "experience_level": "beginner", "current_weekly_distance_km": 10, "runs_per_week": 2,
        "longest_recent_run_km": 5, "preferred_training_days": ["tuesday", "saturday"],
        "preferred_long_run_day": "saturday", "max_session_minutes": 45,
        "preferred_terrain": "road", "available_equipment": ["none"],
        "current_issue_areas": ["none"], "current_pain_level": 0, "recovery_level": "good",
        "average_sleep_duration": "7_to_8_hours", "stress_level": "moderate",
        "diet_type": "omnivore", "weight_kg": None, "main_preference": "balanced_training",
        "detail_level": "balanced",
    }).model_dump(mode="json")


def start(db, client_host):
    if not DEMO_ENABLED:
        raise HTTPException(503, "The demo is not enabled right now.")
    # Use the server's client address, never a caller-supplied forwarded header.
    digest = hmac.new(JWT_SECRET_KEY.encode(), (client_host or "unknown").encode(), hashlib.sha256).hexdigest()
    db.execute(text("SELECT pg_advisory_xact_lock(19711, 1)"))
    since = (now() - timedelta(hours=1)).isoformat()
    rows = db.scalars(select(CoachMemory.summary).where(
        CoachMemory.summary[KEY]["created_at"].as_string() >= since,
    )).all()
    records = [row[KEY] for row in rows]
    if len(records) >= 20 or sum(item["client_hash"] == digest for item in records) >= 3:
        raise HTTPException(429, "Demo capacity reached. Please try later or create an account.")
    if sum(datetime.fromisoformat(item["expires_at"]) > now() for item in records) >= 5:
        raise HTTPException(429, "All demo places are in use. Please try again later.")
    identity = uuid4()
    user = User(id=identity, username=f"demo_{identity.hex}", full_name="Demo Runner",
                email=f"demo-{identity.hex}@demo.example.com", password_hash="!demo-no-password",
                birth=date(1995, 1, 1), interests=["Running", "Club activities"])
    db.add(user)
    db.flush()
    created = now()
    demo = {"created_at": created.isoformat(), "expires_at": (created + timedelta(minutes=DEMO_MINUTES)).isoformat(),
            "client_hash": digest, "used": {key: 0 for key in LIMITS}, "purged": False}
    db.add(CoachMemory(user_id=user.id, summary={KEY: demo, "chat": {}}))
    db.add(Survey(user_id=user.id, survey_type=RecommendationType.RUNNING_PLAN, answers=sample_answers()))
    db.commit()
    return user, demo


def authorize(db, user, method, path):
    """Reserve attempts before endpoint work; failed AI calls still consume quota."""
    demo = metadata(db, user.id)
    if demo is None:
        return None
    if not DEMO_ENABLED:
        raise HTTPException(503, "The demo is not enabled right now.")
    assert_active(demo)
    allowed = (
        (method == "GET" and (path in {"/auth/me", "/users/me", "/demo/status"}
                              or path.startswith(("/chatbot/history", "/surveys", "/recommendations", "/feedbacks"))))
        or (method == "POST" and (path in {"/auth/logout", "/chatbot", "/chatbot/", "/chatbot/end", "/surveys", "/surveys/", "/recommendations/generate"}
                                 or re.fullmatch(r"/recommendations/[0-9a-f-]+/(?:feedback|revise|health-update)", path)))
        or (method in {"PATCH", "DELETE"} and path.startswith("/chatbot/"))
    )
    if not allowed:
        raise HTTPException(403, "This action is unavailable in the demo. Create an account to continue.")
    user.is_demo = True
    user.demo_expires_at = demo["expires_at"]
    if path in {"/demo/status", "/auth/me", "/auth/logout"}:
        return demo
    memory = get_or_create_coach_memory(db, user.id, lock=True)
    demo = dict(memory.summary[KEY])
    assert_active(demo)
    used = dict(demo["used"])
    quota = None
    if method == "POST":
        if path.rstrip('/') == "/chatbot":
            quota = "chat"
        elif path == "/recommendations/generate":
            quota = "plans"
        elif path.endswith('/revise'):
            quota = "revisions"
        elif path == "/chatbot/end" and memory.summary.get("chat", {}).get("current_conversation"):
            quota = "summaries"
    for key in ["requests", *([quota] if quota else [])]:
        if used[key] >= LIMITS[key]:
            raise HTTPException(429, {"reason": "demo_quota", "message": f"Your demo {key} limit has been reached.", "quota": key})
        used[key] += 1
    demo["used"] = used
    memory.summary = {**memory.summary, KEY: demo}
    # Nothing in the endpoint has run yet. Committing here prevents failed
    # requests from refunding model attempts and allowing unlimited API spend.
    db.commit()
    return demo


def status(demo):
    return {"expires_at": demo["expires_at"], "limits": LIMITS,
            "remaining": {key: max(0, limit - demo["used"][key]) for key, limit in LIMITS.items()}}


def cleanup(db):
    """Purge expired content; keep only anonymous rate-limit records for one hour."""
    if not db.scalar(text("SELECT pg_try_advisory_xact_lock(19711, 2)")):
        return 0
    records = db.scalars(select(CoachMemory).where(
        CoachMemory.summary[KEY]["expires_at"].as_string() <= now().isoformat(),
    ).order_by(CoachMemory.created_at).limit(100)).all()
    count = 0
    for memory in records:
        demo = memory.summary[KEY]
        if datetime.fromisoformat(demo["created_at"]) <= now() - timedelta(hours=1):
            user = db.get(User, memory.user_id)
            if user:
                db.delete(user)
                count += 1
        elif not demo["purged"]:
            # Only rows belonging to a server-created, expired demo are touched.
            for model in (Feedback, Recommendation, Survey, PasswordResetToken):
                db.execute(delete(model).where(model.user_id == memory.user_id))
            memory.summary = {KEY: {**demo, "purged": True}, "chat": {}}
            count += 1
    db.commit()
    return count
