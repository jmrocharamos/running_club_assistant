from app.services.telemetry import traced
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.coach_memory import CoachMemory
from app.schemas.running_structured_outputs import CoachMemorySummary


@traced("get_or_create_coach_memory", kind="span")
def get_or_create_coach_memory(
    db: Session,
    user_id: UUID,
) -> CoachMemory:
    coach_memory = db.scalars(
        select(CoachMemory).where(
            CoachMemory.user_id == user_id,
        )
    ).first()

    if coach_memory is None:
        coach_memory = CoachMemory(
            user_id=user_id,
            summary=CoachMemorySummary().model_dump(
                mode="json",
            ),
        )
        db.add(coach_memory)
        db.flush()

        return coach_memory

    return coach_memory
