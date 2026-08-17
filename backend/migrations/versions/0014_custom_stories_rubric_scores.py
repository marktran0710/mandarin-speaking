"""Add teacher rubric scores and source link to custom stories.

Revision ID: 0015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "custom_stories",
        sa.Column("rubric_scores", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("custom_stories", "rubric_scores")
