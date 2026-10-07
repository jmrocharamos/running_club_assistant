"""Allow local-only chunks and track the title used for embedding.

Revision ID: d932a4b81e60
Revises: c81a9e7d203b
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "d932a4b81e60"
down_revision = "c81a9e7d203b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("knowledge_chunks", "embedding",
                    existing_type=Vector(1536), nullable=True)
    op.add_column("knowledge_chunks", sa.Column("embedding_title", sa.String(255)))
    op.execute(sa.text("""
        UPDATE knowledge_chunks AS chunk
        SET embedding_title = document.title
        FROM knowledge_base AS document
        WHERE chunk.knowledge_base_id = document.id
    """))


def downgrade() -> None:
    # Restore legacy vectors where possible. NOT NULL deliberately fails if
    # local-only chunks remain: rebuild the OpenAI index before downgrading.
    op.execute(sa.text("""
        UPDATE knowledge_chunks AS chunk
        SET embedding = stored.embedding
        FROM knowledge_embeddings_openai AS stored
        WHERE stored.chunk_id = chunk.id
          AND stored.model = 'text-embedding-3-small'
          AND chunk.embedding IS NULL
    """))
    op.alter_column("knowledge_chunks", "embedding",
                    existing_type=Vector(1536), nullable=False)
    op.drop_column("knowledge_chunks", "embedding_title")
