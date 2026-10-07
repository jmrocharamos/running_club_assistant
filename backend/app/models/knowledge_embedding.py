"""Separate vector storage for each provider's current embedding dimensions."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeEmbeddingMixin:
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    model: Mapped[str] = mapped_column(String(255), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )


class KnowledgeEmbeddingOpenAI(KnowledgeEmbeddingMixin, Base):
    __tablename__ = "knowledge_embeddings_openai"

    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)


class KnowledgeEmbeddingOllama(KnowledgeEmbeddingMixin, Base):
    __tablename__ = "knowledge_embeddings_ollama"

    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
