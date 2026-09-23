"""Research Policy Layer, Epic 7 (independent outcome bank + read-only
probes), Tasks 7.1-7.4.

Adds:
- ``vocab_research_assessment_items``: the outcome/measurement question
  bank. Deliberately separate from the training/core question content on
  ``custom_stories`` (Task 7.1's "training questions and outcome questions
  must be separate") - a probe or posttest must never reuse a word's
  core-round question, or repeated-exposure itself would become a second,
  uncontrolled treatment. ``correct_answer`` is server-only; routers must
  never serialize it into a student-facing response (Task 7.6).
- ``vocab_research_probe_assignments``: which assessment item is scheduled
  for which student and when it becomes due (Task 7.3). One row per
  (student, word, probe_type) - Task 7.7 requires a word's probe pool to be
  disjoint per learner (a word is never both a 7-day AND a 21-day probe for
  the same student), enforced by the unique constraint below plus the pure
  partitioning function in domain/vocabulary/research_probes.py.
- ``vocab_research_probe_responses``: one immutable, ungraded-to-the-student
  answer per assignment (Task 7.5/7.6) - "never submit a probe through the
  normal quiz-attempt API" means this never touches vocab_quiz_responses or
  vocab_quiz_attempts.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vocab_research_assessment_items",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("study_id", sa.Text, sa.ForeignKey("vocab_research_studies.id"), nullable=False),
        sa.Column("word_id", sa.Text, nullable=False),
        sa.Column("assessment_type", sa.Text, nullable=False),
        sa.Column("question_type", sa.Text, nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("choices", postgresql.JSONB),
        sa.Column("correct_answer", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint(
            "assessment_type IN ('pretest', 'midtest', 'posttest', 'probe_7d', 'probe_21d', 'final_retention')",
            name="ck_vocab_research_assessment_items_type",
        ),
    )
    op.create_index(
        "ix_vocab_research_assessment_items_study_word_type",
        "vocab_research_assessment_items",
        ["study_id", "word_id", "assessment_type"],
    )

    op.create_table(
        "vocab_research_probe_assignments",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("study_id", sa.Text, sa.ForeignKey("vocab_research_studies.id"), nullable=False),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("word_id", sa.Text, nullable=False),
        sa.Column(
            "assessment_item_id",
            sa.Text,
            sa.ForeignKey("vocab_research_assessment_items.id"),
            nullable=False,
        ),
        sa.Column("probe_type", sa.Text, nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint(
            "probe_type IN ('probe_7d', 'probe_21d', 'final_retention')",
            name="ck_vocab_research_probe_assignments_type",
        ),
        sa.UniqueConstraint(
            "study_id", "student_id", "word_id", "probe_type",
            name="uq_vocab_research_probe_assignments_student_word_type",
        ),
    )
    # Query pattern: "which of this student's probes are due right now"
    # (Task 7.5's GET /probes/due).
    op.create_index(
        "ix_vocab_research_probe_assignments_due",
        "vocab_research_probe_assignments",
        ["student_id", "study_id", "due_at"],
    )

    op.create_table(
        "vocab_research_probe_responses",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "probe_assignment_id",
            sa.BigInteger,
            sa.ForeignKey("vocab_research_probe_assignments.id"),
            nullable=False,
        ),
        sa.Column("study_id", sa.Text, nullable=False),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("word_id", sa.Text, nullable=False),
        sa.Column("assessment_item_id", sa.Text, nullable=False),
        sa.Column("response_value", sa.Text, nullable=False),
        sa.Column("correct", sa.Boolean, nullable=False),
        sa.Column("source_response_id", sa.Text, nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        # One probe is answered at most once - a read-only measurement, not a
        # retriable quiz (Task 7.6: no feedback loop that a retry could game).
        sa.UniqueConstraint("probe_assignment_id", name="uq_vocab_research_probe_responses_assignment"),
    )


def downgrade() -> None:
    op.drop_table("vocab_research_probe_responses")
    op.drop_index("ix_vocab_research_probe_assignments_due", table_name="vocab_research_probe_assignments")
    op.drop_table("vocab_research_probe_assignments")
    op.drop_index("ix_vocab_research_assessment_items_study_word_type", table_name="vocab_research_assessment_items")
    op.drop_table("vocab_research_assessment_items")
