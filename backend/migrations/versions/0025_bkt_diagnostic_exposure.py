"""Persist the exact diagnostic exposure used for first-response gating."""
from alembic import op
import sqlalchemy as sa


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vocab_quiz_responses", sa.Column("diagnostic_exposure_id", sa.Text, nullable=True))
    # Rows created before the complete exposure contract existed cannot be
    # reconstructed safely. Keep them in the raw ledger, but require a fresh
    # server validation before they influence mastery.
    op.execute(
        "UPDATE vocab_quiz_responses "
        "SET bkt_eligible = FALSE, bkt_eligibility_errors = '[\"LEGACY_BEFORE_EXPOSURE_CONTRACT\"]'::jsonb"
    )


def downgrade() -> None:
    op.drop_column("vocab_quiz_responses", "diagnostic_exposure_id")
