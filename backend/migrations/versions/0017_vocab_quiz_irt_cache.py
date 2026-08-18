"""Cache table for the vocab-quiz ability/difficulty/speed joint IRT fit
used by weak-word scoring (see analytics/weak_words.py). Refit on every new
attempt and read back on every weak-words request, rather than fitting the
model live inside a read request.

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vocab_quiz_irt_cache",
        # Single-row cache: always id=1, upserted in place on refit.
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("student_ability", postgresql.JSONB, nullable=False),
        sa.Column("item_difficulty", postgresql.JSONB, nullable=False),
        sa.Column("student_speed", postgresql.JSONB, nullable=False),
        sa.Column("item_time_intensity", postgresql.JSONB, nullable=False),
        sa.Column("n_responses", sa.Integer, nullable=False),
        sa.Column("fitted_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("vocab_quiz_irt_cache")
