"""Research Policy Layer, Epic 5 (adaptive SM-2 + yoked review), Task 5.1/5.2.

Adds:
- ``vocab_research_retention_state``: the current SM-2-shaped schedule per
  (student, study, word) for a research participant. Deliberately separate
  from production's ``student_vocab_srs`` (Task 5.1's "do not overload
  production" instruction) - a yoked word's schedule here is a mirror of its
  paired adaptive word's schedule, not its own graded outcome, which is not
  a state production's SRS table has any concept of.
- ``vocab_research_retention_events``: append-only transition history,
  mirroring ``student_vocab_srs_events``' shape plus ``study_id`` and an
  additional ``yoked_mirror`` event type (Task 5.6's schedule-copy step) and
  ``yoked_exposure`` (a yoked word was shown/answered without its own
  schedule being touched - kept for research audit only).
"""

from alembic import op
import sqlalchemy as sa


revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vocab_research_retention_state",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("study_id", sa.Text, nullable=False),
        sa.Column("word_id", sa.Text, nullable=False),
        sa.Column("reps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ease", sa.Float, nullable=False, server_default="2.5"),
        sa.Column("interval_days", sa.Integer, nullable=False, server_default="0"),
        sa.Column("due_on", sa.DateTime(timezone=True)),
        sa.Column("last_reviewed_on", sa.DateTime(timezone=True)),
        sa.Column("algorithm_version", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.UniqueConstraint("student_id", "study_id", "word_id", name="uq_vocab_research_retention_state_student_study_word"),
    )
    op.create_index("ix_vocab_research_retention_state_due", "vocab_research_retention_state", ["student_id", "study_id", "due_on"])

    op.create_table(
        "vocab_research_retention_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("study_id", sa.Text, nullable=False),
        sa.Column("word_id", sa.Text, nullable=False),
        sa.Column("source_response_id", sa.Text, nullable=False),
        sa.Column("quiz_id", sa.Text),
        sa.Column("attempt_id", sa.Text),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("correct", sa.Boolean),
        sa.Column("quality", sa.Integer),
        sa.Column("old_reps", sa.Integer, nullable=False),
        sa.Column("new_reps", sa.Integer, nullable=False),
        sa.Column("old_ease", sa.Float, nullable=False),
        sa.Column("new_ease", sa.Float, nullable=False),
        sa.Column("old_interval_days", sa.Integer, nullable=False),
        sa.Column("new_interval_days", sa.Integer, nullable=False),
        sa.Column("old_due_on", sa.DateTime(timezone=True)),
        sa.Column("new_due_on", sa.DateTime(timezone=True)),
        sa.Column("algorithm_version", sa.Text, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('enrollment', 'maintenance_success', 'maintenance_failure', 'yoked_mirror', 'yoked_exposure')",
            name="ck_vocab_research_retention_events_type",
        ),
        sa.UniqueConstraint("student_id", "study_id", "word_id", "source_response_id", name="uq_vocab_research_retention_events_source"),
    )
    op.create_index(
        "ix_vocab_research_retention_events_student_word_occurred",
        "vocab_research_retention_events",
        ["student_id", "study_id", "word_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_vocab_research_retention_events_student_word_occurred", table_name="vocab_research_retention_events")
    op.drop_table("vocab_research_retention_events")
    op.drop_index("ix_vocab_research_retention_state_due", table_name="vocab_research_retention_state")
    op.drop_table("vocab_research_retention_state")
