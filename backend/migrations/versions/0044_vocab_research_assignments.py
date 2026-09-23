"""Research Policy Layer, Epic 2: frozen item-assignment table.

One row per (study, student, word): the permanent experimental condition
that word carries for that student for the life of the study. Written once
by the offline generator (scripts/build_research_assignments.py), never by
a live request - see domain/vocabulary/research_assignment.py for why
assignment must be deterministic and frozen rather than computed on the
fly. Nothing reads this table yet; Epic 4/5 wire it into practice/retention
selection.
"""

from alembic import op
import sqlalchemy as sa


revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vocab_research_assignments",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "study_id",
            sa.Text,
            sa.ForeignKey("vocab_research_studies.id"),
            nullable=False,
        ),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("word_id", sa.Text, nullable=False),
        sa.Column("lesson_id", sa.Text),
        sa.Column("section_id", sa.Text),
        sa.Column("bkt_policy", sa.Text, nullable=False),
        sa.Column("retention_policy", sa.Text, nullable=False),
        sa.Column("sequence_id", sa.Text, nullable=False),
        sa.Column("related_set_id", sa.Text),
        sa.Column("yoke_source_word_id", sa.Text),
        sa.Column("assignment_version", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.UniqueConstraint(
            "study_id", "student_id", "word_id",
            name="uq_vocab_research_assignments_study_student_word",
        ),
        sa.CheckConstraint(
            "bkt_policy IN ('mastery_blind', 'bkt_personalized')",
            name="ck_vocab_research_assignments_bkt_policy",
        ),
        sa.CheckConstraint(
            "retention_policy IN ('yoked', 'adaptive_sm2')",
            name="ck_vocab_research_assignments_retention_policy",
        ),
        sa.CheckConstraint(
            "sequence_id IN ('A', 'B', 'C', 'D')",
            name="ck_vocab_research_assignments_sequence_id",
        ),
    )
    # Query pattern: "what's this student's condition for word X" (Epic 4/5).
    op.create_index(
        "ix_vocab_research_assignments_student_word",
        "vocab_research_assignments",
        ["student_id", "word_id"],
    )
    # Query pattern: balance auditing across one study.
    op.create_index(
        "ix_vocab_research_assignments_study",
        "vocab_research_assignments",
        ["study_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_vocab_research_assignments_study", table_name="vocab_research_assignments")
    op.drop_index("ix_vocab_research_assignments_student_word", table_name="vocab_research_assignments")
    op.drop_table("vocab_research_assignments")
