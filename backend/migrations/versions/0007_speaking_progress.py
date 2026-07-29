"""Add speaking_progress — resumable per-scene speaking-practice state.

Previously attempts/bestTone/bestFluency/mastery+content gates/cleared-word
drill state lived only in StoryRecorder's React state, so a reload or
navigating away lost everything. This table gives each (student, topic,
scene) exactly one row, upserted whenever that state changes, so the
practice screen can restore it on load.

`id` is deterministic (`f"{student_id}:{topic_id}:{scene_index}"`) rather
than client-generated, so the upsert can target it directly with
`ON CONFLICT (id) DO UPDATE` instead of needing a separate unique
constraint on the three parts.

Revision ID: 0007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

SQLITE_STYLE_NOW = sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")


def upgrade() -> None:
    op.create_table(
        "speaking_progress",
        sa.Column("id", sa.Text, primary_key=True),
        # Not a FK — same reasoning as vocab_quiz_attempts.student_id (0001):
        # progress for a student whose roster row later changes/disappears
        # must still be readable.
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("topic_id", sa.Text, nullable=False),
        sa.Column("scene_index", sa.Integer, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("best_tone", sa.Float, nullable=False, server_default="0"),
        sa.Column("best_fluency", sa.Float, nullable=False, server_default="0"),
        sa.Column("mastery_passed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("content_passed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("cleared_words", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.Text, nullable=False, server_default=SQLITE_STYLE_NOW),
    )
    op.create_index(
        "ix_speaking_progress_student_topic",
        "speaking_progress",
        ["student_id", "topic_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_speaking_progress_student_topic", table_name="speaking_progress")
    op.drop_table("speaking_progress")
