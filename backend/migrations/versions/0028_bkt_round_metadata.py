"""Persist diagnostic round and learning-dimension metadata for replay."""

from alembic import op
import sqlalchemy as sa


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vocab_quiz_responses", sa.Column("round_type", sa.Text, nullable=True))
    op.add_column("vocab_quiz_responses", sa.Column("knowledge_dimension", sa.Text, nullable=True))
    op.add_column("vocab_quiz_responses", sa.Column("activity_type", sa.Text, nullable=True))
    op.create_index(
        "ix_vocab_quiz_responses_student_lesson_mode",
        "vocab_quiz_responses",
        ["student_id", "lesson_id", "quiz_mode", "bkt_eligible"],
    )


def downgrade() -> None:
    op.drop_index("ix_vocab_quiz_responses_student_lesson_mode", table_name="vocab_quiz_responses")
    op.drop_column("vocab_quiz_responses", "activity_type")
    op.drop_column("vocab_quiz_responses", "knowledge_dimension")
    op.drop_column("vocab_quiz_responses", "round_type")
