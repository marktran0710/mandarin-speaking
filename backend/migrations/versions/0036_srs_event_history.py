"""Add immutable SRS transition history for research replay.

SRS state remains the current projection used by the queue. This append-only
table records how each enrollment or maintenance transition produced that
projection, including the scheduler version and old/new values.
"""

from alembic import op
import sqlalchemy as sa


revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_vocab_srs_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("word_id", sa.Text, nullable=False),
        sa.Column("source_response_id", sa.Text, nullable=True),
        sa.Column("quiz_id", sa.Text, nullable=True),
        sa.Column("attempt_id", sa.Text, nullable=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("correct", sa.Boolean, nullable=True),
        sa.Column("quality", sa.Integer, nullable=True),
        sa.Column("old_reps", sa.Integer, nullable=False),
        sa.Column("new_reps", sa.Integer, nullable=False),
        sa.Column("old_ease", sa.Float, nullable=False),
        sa.Column("new_ease", sa.Float, nullable=False),
        sa.Column("old_interval_days", sa.Integer, nullable=False),
        sa.Column("new_interval_days", sa.Integer, nullable=False),
        sa.Column("old_due_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_due_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("algorithm_version", sa.Text, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('enrollment', 'maintenance_success', 'maintenance_failure')",
            name="ck_student_vocab_srs_events_type",
        ),
        sa.UniqueConstraint(
            "student_id", "word_id", "event_type", "source_response_id",
            name="uq_student_vocab_srs_events_source",
        ),
    )
    op.create_index(
        "ix_student_vocab_srs_events_student_word_occurred",
        "student_vocab_srs_events",
        ["student_id", "word_id", "occurred_at"],
    )

def downgrade() -> None:
    op.drop_index(
        "ix_student_vocab_srs_events_student_word_occurred",
        table_name="student_vocab_srs_events",
    )
    op.drop_table("student_vocab_srs_events")
