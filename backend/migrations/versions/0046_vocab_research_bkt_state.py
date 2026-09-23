"""Research Policy Layer, Epic 4 (equal-budget BKT practice), Task 4.1/4.2.

Adds:
- ``vocab_quiz_responses.research_study_id`` (nullable, additive): stamps
  which study, if any, each response belongs to, so a treatment-BKT replay
  can scope itself to exactly that study's own evidence (Task 4.2) instead of
  a student's production weak_words/maintenance_review history from before or
  outside the study.
- ``vocab_research_bkt_state``: a separate treatment-mastery table (Task
  4.1), deliberately not sharing rows with production's
  ``student_vocab_mastery``. This keeps a future production BKT parameter
  recalibration from ever silently altering a frozen study's historical
  treatment-state record, and gives research an inspectable snapshot of the
  p(learned) that actually drove each practice-session selection.
"""

from alembic import op
import sqlalchemy as sa


revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vocab_quiz_responses", sa.Column("research_study_id", sa.Text))

    op.create_table(
        "vocab_research_bkt_state",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("study_id", sa.Text, nullable=False),
        sa.Column("word_id", sa.Text, nullable=False),
        sa.Column("p_learned", sa.Float, nullable=False),
        sa.Column("observation_count", sa.Integer, nullable=False),
        sa.Column("correct_count", sa.Integer, nullable=False),
        sa.Column("incorrect_count", sa.Integer, nullable=False),
        sa.Column("last_response_at", sa.Text),
        sa.Column("last_item_id", sa.Text),
        sa.Column("last_question_type", sa.Text),
        sa.Column("model_version", sa.Text),
        sa.Column("parameter_fingerprint", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.UniqueConstraint("student_id", "study_id", "word_id", name="uq_vocab_research_bkt_state_student_study_word"),
    )
    op.create_index("ix_vocab_research_bkt_state_student_study", "vocab_research_bkt_state", ["student_id", "study_id"])


def downgrade() -> None:
    op.drop_table("vocab_research_bkt_state")
    op.drop_column("vocab_quiz_responses", "research_study_id")
