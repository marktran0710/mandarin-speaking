"""Store the generated server-side filename for student recordings."""

from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audio_records", sa.Column("audio_name", sa.Text))


def downgrade() -> None:
    op.drop_column("audio_records", "audio_name")
