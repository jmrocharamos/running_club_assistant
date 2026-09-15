"""Link recommendation ratings to their generation traces.

Revision ID: 72d849ab01f3
Revises: 6ec9df49298d
"""
from alembic import op
import sqlalchemy as sa

revision = '72d849ab01f3'
down_revision = '6ec9df49298d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('recommendations', sa.Column('langfuse_trace_id', sa.String(32), nullable=True))


def downgrade():
    op.drop_column('recommendations', 'langfuse_trace_id')
