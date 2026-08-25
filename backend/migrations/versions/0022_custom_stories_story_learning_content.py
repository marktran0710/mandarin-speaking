"""Add nullable story-level vocabulary and phrase learning content."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "custom_stories",
        sa.Column("story_vocabulary", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "custom_stories",
        sa.Column("story_phrases", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("custom_stories", "story_phrases")
    op.drop_column("custom_stories", "story_vocabulary")
