from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RecommendationType


class Recommendation(Base):
    __tablename__ = "recommendations"

    __table_args__ = (
        CheckConstraint(
            'feedback_rating IS NULL OR feedback_rating BETWEEN 1 AND 5',
            name='check_feedback_rating_range',
        ),

    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    survey_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("surveys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    recommendation_type: Mapped[RecommendationType] = mapped_column(
        SQLEnum(RecommendationType),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    explanation: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    survey_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    langfuse_trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    feedback_rating: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )


    is_favorite: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    survey: Mapped['Survey'] = relationship(
        back_populates='recommendations',
    )

    feedbacks: Mapped[list['Feedback']] = relationship(
        back_populates='recommendation',
        cascade="all, delete-orphan",
        passive_deletes=True,
    )