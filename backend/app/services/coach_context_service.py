from app.services.telemetry import traced
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import RecommendationType
from app.models.feedback import Feedback
from app.models.recommendation import Recommendation
from app.models.survey import Survey
from app.models.user import User


SURVEY_FIELDS = (
    "goal",
    "target_distance",
    "experience_level",
    "current_weekly_distance_km",
    "runs_per_week",
    "preferred_training_days",
    "current_issue_areas",
    "current_pain_level",
    "medically_cleared_activities",
    "main_preference",
    "diet_type",
)


@traced("build_coach_context", kind="span")
def build_coach_context(
    db: Session,
    user: User,
) -> dict[str, Any]:
    """Collect the user profile, latest running survey, and recent plans and feedback."""
    latest_survey = db.scalars(
        select(Survey)
        .where(
            Survey.user_id == user.id,
            Survey.survey_type == RecommendationType.RUNNING_PLAN,
        )
        .order_by(Survey.created_at.desc(), Survey.id.desc())
        .limit(1)
    ).first()

    recent_plans = db.scalars(
        select(Recommendation)
        .where(
            Recommendation.user_id == user.id,
            Recommendation.recommendation_type
            == RecommendationType.RUNNING_PLAN,
        )
        .order_by(
            Recommendation.created_at.desc(),
            Recommendation.id.desc(),
        )
        .limit(3)
    ).all()

    recent_feedback = db.execute(
        select(Feedback, Recommendation.title)
        .join(
            Recommendation,
            Feedback.recommendation_id == Recommendation.id,
        )
        .where(Recommendation.user_id == user.id)
        .order_by(
            Feedback.created_at.desc(),
            Feedback.id.desc(),
        )
        .limit(5)
    ).all()

    survey_context = None

    if latest_survey:
        survey_context = {
            "created_at": latest_survey.created_at.isoformat(),
            **{
                field: latest_survey.answers.get(field)
                for field in SURVEY_FIELDS
                if latest_survey.answers.get(field) is not None
            },
        }

    return {
        "profile": {
            "full_name": user.full_name,
            "height_cm": user.height_cm,
            "interests": user.interests or [],
        },
        "latest_survey": survey_context,
        "recent_plans": [
            {
                "id": str(plan.id),
                "title": plan.title,
                "summary": plan.content.get("summary"),
                "rating": plan.feedback_rating,
                "created_at": plan.created_at.isoformat(),
            }
            for plan in recent_plans
        ],
        "recent_feedback": [
            {
                "recommendation_id": str(feedback.recommendation_id),
                "plan_title": plan_title,
                "feedback": feedback.feedback,
                "created_at": feedback.created_at.isoformat(),
            }
            for feedback, plan_title in recent_feedback
        ],
    }
