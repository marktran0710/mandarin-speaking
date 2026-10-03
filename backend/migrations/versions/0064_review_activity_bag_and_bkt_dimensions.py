"""Persist per-dimension BKT projections and per-word review shuffle bags."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "student_vocab_mastery",
        sa.Column(
            "dimension_states",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "student_vocab_srs",
        sa.Column(
            "review_activity_bag",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("student_vocab_srs", "review_activity_bag")
    op.drop_column("student_vocab_mastery", "dimension_states")
