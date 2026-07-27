"""Add custom_stories.quiz_approved_snapshot — the per-word AI quiz material
a teacher has explicitly approved via the Quiz Review page's "Approve &
Publish" action, keyed by difficulty tier like quiz_material_snapshot.
topicQuizEntries/storyToTopic read this (not the live per-word fields) to
build a student's quiz, so editing a story or a student's own background
pool growth (StoryRecorder's growVocabularyDistractorPool and friends) can
never change what students see until a teacher re-approves. Nullable: a
story that has never been approved simply serves no AI material yet.

Revision ID: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "custom_stories",
        sa.Column("quiz_approved_snapshot", postgresql.JSONB),
    )


def downgrade() -> None:
    op.drop_column("custom_stories", "quiz_approved_snapshot")
