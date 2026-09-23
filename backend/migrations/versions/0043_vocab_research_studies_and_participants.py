"""Research Policy Layer, Epic 1: study + participant tables.

Pure scaffolding - nothing reads these tables yet. A student only becomes a
research participant once an admin/offline tool inserts a row into
vocab_research_participants for an active/pilot study, which does not exist
until a later Epic. Every existing student's behavior is unaffected: no
migration here touches students, vocab_quiz_attempts, student_vocab_mastery,
or any other production table.

config_json/policy_version/assignment_version are versioned so a later
Epic's frozen assignment engine (Epic 2) can pin exactly which rules a
participant experienced, even if the study config changes afterward.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vocab_research_studies",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            server_default="draft",
        ),
        sa.Column("config_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("policy_version", sa.Text, nullable=False),
        sa.Column("assignment_version", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("frozen_at", sa.Text),
        sa.Column("started_at", sa.Text),
        sa.Column("completed_at", sa.Text),
        sa.CheckConstraint(
            "status IN ('draft', 'pilot', 'frozen', 'active', 'completed')",
            name="ck_vocab_research_studies_status",
        ),
    )

    op.create_table(
        "vocab_research_participants",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column(
            "study_id",
            sa.Text,
            sa.ForeignKey("vocab_research_studies.id"),
            nullable=False,
        ),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("class_id", sa.Text),
        sa.Column("sequence_id", sa.Text),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.UniqueConstraint(
            "study_id", "student_id", name="uq_vocab_research_participants_study_student"
        ),
    )
    # Query pattern: "is this student in any active research study right now?"
    op.create_index(
        "ix_vocab_research_participants_student",
        "vocab_research_participants",
        ["student_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vocab_research_participants_student",
        table_name="vocab_research_participants",
    )
    op.drop_table("vocab_research_participants")
    op.drop_table("vocab_research_studies")
