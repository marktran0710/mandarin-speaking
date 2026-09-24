"""Drop the unused IRT cache table and two indexes made redundant by others.

- vocab_quiz_irt_cache: nothing has read or written it since weak words moved
  from the joint-IRT fit to BKT. It only ever held one regenerable cache row.
- students_name_key (UNIQUE name): uq_students_lower_name (UNIQUE lower(name))
  already rejects every name this one would, and nothing uses ON CONFLICT (name).
- ix_student_vocab_mastery_student (student_id): a prefix of
  uq_student_vocab_mastery_student_word (student_id, word_id).

Revision ID: 0042
Revises: 0041
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("vocab_quiz_irt_cache")
    op.drop_constraint("students_name_key", "students", type_="unique")
    op.drop_index("ix_student_vocab_mastery_student", table_name="student_vocab_mastery")


def downgrade() -> None:
    op.create_index("ix_student_vocab_mastery_student", "student_vocab_mastery", ["student_id"])
    op.create_unique_constraint("students_name_key", "students", ["name"])
    op.create_table(
        "vocab_quiz_irt_cache",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("student_ability", postgresql.JSONB, nullable=False),
        sa.Column("item_difficulty", postgresql.JSONB, nullable=False),
        sa.Column("student_speed", postgresql.JSONB, nullable=False),
        sa.Column("item_time_intensity", postgresql.JSONB, nullable=False),
        sa.Column("n_responses", sa.Integer, nullable=False),
        sa.Column("fitted_at", sa.Text, nullable=False),
    )
