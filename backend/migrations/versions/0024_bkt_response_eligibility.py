"""Persist the research eligibility decision alongside every raw response."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing response rows are not retroactively eligible. Only the current
    # server-side validator may mark a response as BKT evidence.
    op.add_column("vocab_quiz_responses", sa.Column("bkt_eligible", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("vocab_quiz_responses", sa.Column("bkt_eligibility_errors", postgresql.JSONB, nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("vocab_quiz_responses", "bkt_eligibility_errors")
    op.drop_column("vocab_quiz_responses", "bkt_eligible")
