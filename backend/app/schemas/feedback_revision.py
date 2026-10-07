from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.survey_options import MedicallyClearedActivity
from app.schemas.training_safety import TrainingPlanMode


class FeedbackSafetyAssessment(BaseModel):
    decision: Literal[
        "continue_revision",
        "needs_health_update",
        "requires_coach_review",
    ]
    message: str = Field(
        min_length=1,
        max_length=500,
    )
    requested_start_date: date | None = None

    plan_mode: TrainingPlanMode | None = None

    current_pain_level: int | None = Field(
        default=None,
        ge=0,
        le=10,
    )

    medically_cleared_activities: (
        list[MedicallyClearedActivity] | None
    ) = None

    @model_validator(mode="after")
    def validate_decision_mode(self) -> Self:
        if self.decision == "continue_revision" and self.plan_mode in (None, "blocked"):
            raise ValueError("continue_revision requires a permitted plan mode")
        if self.decision == "needs_health_update" and self.plan_mode is not None:
            raise ValueError("needs_health_update requires a null plan mode")
        if self.decision == "requires_coach_review" and self.plan_mode != "blocked":
            raise ValueError("requires_coach_review requires blocked plan mode")
        return self
