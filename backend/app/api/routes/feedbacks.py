import json
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.client_openai import get_recommendation
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.recommendation import Recommendation
from app.models.user import User
from app.prompts.feedback_input import build_feedback_revision_input
from app.prompts.feedback_prompt import (
    get_adapted_feedback_prompt,
    get_feedback_prompt,
)
from app.schemas.feedback import FeedbackCreate, FeedbackRead, HealthUpdateCreate
from app.schemas.recommendation import RecommendationRead
from app.services.feedback_manager import assess_feedback_safety
from app.services.feedback_service import (
    build_health_update_feedback,
    create_feedback,
    get_feedback_by_recommendation_id,
)
from app.services.plan_revision_service import PlanFinishedError, build_remaining_plan_context
from app.services.recommendation_title_service import build_revision_title
from app.services.running_plan_service import (
    synchronize_weekly_distances,
    validate_plan_mode,
    validate_revision_load,
)


router = APIRouter(
    prefix="/recommendations",
    tags=["Feedback"],
)

def _get_owned_recommendation(
        recommendation_id: UUID,
        current_user: User,
        db: Session,
) -> Recommendation:
    recommendation = db.get(Recommendation, recommendation_id)

    if not recommendation or recommendation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recommendation not found",
        )

    return recommendation


@router.post(
    "/{recommendation_id}/feedback",
    response_model=FeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
def add_recommendation_feedback(
    recommendation_id: UUID,
    feedback_data: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recommendation = _get_owned_recommendation(recommendation_id, current_user, db)

    feedback = create_feedback(
        db,
        recommendation,
        feedback_data,
    )

    db.commit()
    db.refresh(feedback)

    return feedback


@router.get(
    "/{recommendation_id}/feedback",
    response_model=list[FeedbackRead],
)
def get_recommendation_feedback(
    recommendation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recommendation = _get_owned_recommendation(recommendation_id, current_user, db)

    return get_feedback_by_recommendation_id(
        db,
        recommendation.id,
    )


@router.post(
    "/{recommendation_id}/revise",
    response_model=RecommendationRead,
    status_code=status.HTTP_201_CREATED,
)
def revise_recommendation_from_feedback(
    recommendation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recommendation = _get_owned_recommendation(recommendation_id, current_user, db)

    feedback_entries = get_feedback_by_recommendation_id(
        db,
        recommendation_id,
    )

    if not feedback_entries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add feedback before requesting a revised plan",
        )

    recommendation_dict = {
        "id": str(recommendation.id),
        "survey_id": str(recommendation.survey_id),
        "user_id": str(recommendation.user_id),
        "recommendation_type": recommendation.recommendation_type,
        "title": recommendation.title,
        "content": recommendation.content,
        "explanation": recommendation.explanation,
        "survey_snapshot": recommendation.survey_snapshot,
    }
    feedback_dicts = [
        {
            "created_at": entry.created_at.isoformat(),
            "feedback": entry.feedback,
        }
        for entry in feedback_entries
    ]

    revision_date = date.today()
    try:
        remaining_plan = build_remaining_plan_context(recommendation_dict, revision_date)
    except PlanFinishedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    try:
        safety_assessment = assess_feedback_safety(
            recommendation_dict,
            feedback_dicts,
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Your coach couldn't review this plan right now. Please try again in a moment.",
        ) from error

    if safety_assessment["decision"] == "needs_health_update":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "needs_health_update",
                "message": safety_assessment["message"],
            },
        )

    if safety_assessment["decision"] == "requires_coach_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "requires_coach_review",
                "message": safety_assessment["message"],
            },
        )

    plan_mode = safety_assessment["plan_mode"]

    requested_start_date = safety_assessment.get("requested_start_date")
    if requested_start_date is not None:
        remaining_plan = build_remaining_plan_context(
            recommendation_dict,
            revision_date,
            requested_start_date=requested_start_date,
        )

    if plan_mode == "normal_running":
        prompt_version = "remaining"
        instructions = get_feedback_prompt(
            prompt_version
        )
    else:
        prompt_version, instructions = (
            get_adapted_feedback_prompt(
                plan_mode
            )
        )

    input_text = build_feedback_revision_input(
        recommendation_dict,
        feedback_dicts,
        remaining_plan,
        safety_assessment,
    )

    expected_dates = [
        day["date"] for day in remaining_plan["remaining_training_days"]
    ]
    generation_input = input_text
    for attempt in range(2):
        try:
            revised = get_recommendation(
                generation_input,
                instructions,
                prompt_version,
                plan_mode=plan_mode,
            )
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Your coach couldn't generate an updated plan right now. Please try again in a moment.",
            ) from error
        try:
            revised = synchronize_weekly_distances(revised)
            revised = validate_plan_mode(
                revised,
                plan_mode,
                safety_assessment.get("medically_cleared_activities") or [],
            )
            actual_dates = [
                day["date"] for day in revised["content"]["training_days"]
            ]
            if actual_dates != expected_dates:
                raise ValueError("The revised plan changed the required schedule dates.")
            validate_revision_load(
                revised, remaining_plan,
                recommendation.survey_snapshot or {}, plan_mode,
            )
            break
        except ValueError as error:
            if attempt == 1:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Your coach couldn't produce a consistent revised schedule. Please try again. No revised plan was saved.",
                ) from error
            generation_input = (
                input_text
                + "\n\nPREVIOUS OUTPUT TO CORRECT\n"
                + json.dumps(revised, ensure_ascii=False)
                + "\n\nVALIDATION FAILURE\n"
                + str(error)
                + "\nReturn a corrected complete plan satisfying all original constraints."
            )

    new_recommendation = Recommendation(
        survey_id=recommendation.survey_id,
        user_id=recommendation.user_id,
        recommendation_type=recommendation.recommendation_type,
        title=build_revision_title(recommendation.title),
        content=revised["content"],
        explanation=revised.get("explanation"),
        survey_snapshot=recommendation.survey_snapshot,
    )

    db.add(new_recommendation)
    db.commit()
    db.refresh(new_recommendation)

    return new_recommendation


@router.post(
    "/{recommendation_id}/health-update",
    response_model=FeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
def add_health_update_feedback(
    recommendation_id: UUID,
    health_update: HealthUpdateCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recommendation = _get_owned_recommendation(
        recommendation_id,
        current_user,
        db,
    )

    feedback_data = build_health_update_feedback(
        health_update,
    )

    feedback = create_feedback(
        db,
        recommendation,
        feedback_data,
    )

    db.commit()
    db.refresh(feedback)

    return feedback
