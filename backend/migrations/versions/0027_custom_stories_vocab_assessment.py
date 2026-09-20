"""Store validated CSV vocabulary assessment questions on a story."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "custom_stories",
        sa.Column("vocab_assessment", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("custom_stories", "vocab_assessment")
