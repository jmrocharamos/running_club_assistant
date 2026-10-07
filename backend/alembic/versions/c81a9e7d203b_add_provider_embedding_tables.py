"""Add provider embedding tables and copy legacy OpenAI vectors.

Revision ID: c81a9e7d203b
Revises: 72d849ab01f3

The legacy column remains for the existing retrieval and indexing code.
These tables have fixed dimensions; other dimensions require new storage.
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "c81a9e7d203b"
down_revision = "72d849ab01f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for provider, dimensions in (("openai", 1536), ("ollama", 1024)):
        op.create_table(
            f"knowledge_embeddings_{provider}",
            sa.Column("chunk_id", sa.UUID(), nullable=False),
            sa.Column("model", sa.String(255), nullable=False),
            sa.Column("embedding", Vector(dimensions), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["chunk_id"], ["knowledge_chunks.id"],
                                    ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("chunk_id", "model"),
        )

    # The existing client always indexes with text-embedding-3-small.
    op.execute(sa.text("""
        INSERT INTO knowledge_embeddings_openai
            (chunk_id, model, embedding, created_at, updated_at)
        SELECT id, 'text-embedding-3-small', embedding, created_at, updated_at
        FROM knowledge_chunks
    """))


def downgrade() -> None:
    # Original chunks and vectors were retained by upgrade().
    op.drop_table("knowledge_embeddings_ollama")
    op.drop_table("knowledge_embeddings_openai")
