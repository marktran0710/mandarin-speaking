"""Add replayable vocabulary responses and pooled BKT mastery state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vocab_quiz_responses",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("word_id", sa.Text, nullable=False),
        sa.Column("word", sa.Text, nullable=False),
        sa.Column("lesson_id", sa.Text),
        sa.Column("quiz_id", sa.Text, nullable=False),
        sa.Column("attempt_id", sa.Text, nullable=False),
        sa.Column("item_id", sa.Text, nullable=False),
        sa.Column("question_type", sa.Text, nullable=False),
        sa.Column("selected_answer", sa.Text),
        sa.Column("correct_answer", sa.Text),
        sa.Column("presented_options", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("question_prompt", sa.Text),
        sa.Column("answered_at", sa.Text),
        sa.Column("correct", sa.Boolean, nullable=False),
        sa.Column("response_time_ms", sa.Integer, nullable=False),
        sa.Column("occurred_at", sa.Text),
        sa.Column("attempt_order", sa.Integer, nullable=False),
        sa.Column("quiz_level", sa.Text),
        sa.Column("quiz_mode", sa.Text),
        sa.UniqueConstraint("quiz_id", "attempt_order", name="uq_vocab_quiz_response_order"),
    )
    op.create_index("ix_vocab_quiz_responses_student_word", "vocab_quiz_responses", ["student_id", "word_id"])
    op.create_index("ix_vocab_quiz_responses_student_time", "vocab_quiz_responses", ["student_id", "occurred_at", "id"])

    # Do not backfill legacy JSONB attempts here. At this revision the
    # server-owned eligibility decision did not yet exist, so normalizable
    # historical answers must remain audit-only until an explicit, reviewed
    # import is performed.

    op.create_table(
        "student_vocab_mastery",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("word_id", sa.Text, nullable=False),
        sa.Column("p_learned", sa.Float, nullable=False),
        sa.Column("observation_count", sa.Integer, nullable=False),
        sa.Column("correct_count", sa.Integer, nullable=False),
        sa.Column("incorrect_count", sa.Integer, nullable=False),
        sa.Column("last_response_at", sa.Text),
        sa.Column("last_item_id", sa.Text),
        sa.Column("last_question_type", sa.Text),
        sa.Column("last_lesson_id", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.UniqueConstraint("student_id", "word_id", name="uq_student_vocab_mastery_student_word"),
    )
    op.create_index("ix_student_vocab_mastery_student", "student_vocab_mastery", ["student_id"])


def downgrade() -> None:
    op.drop_table("student_vocab_mastery")
    op.drop_table("vocab_quiz_responses")
