"""Add immutable server-verified audio linkage fields."""

from alembic import op
import sqlalchemy as sa


revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audio_records",
        sa.Column("server_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("audio_records", sa.Column("audio_sha256", sa.Text, nullable=True))
    op.add_column(
        "audio_records",
        sa.Column("server_verification_version", sa.Text, nullable=True),
    )
    op.add_column(
        "speaking_progress",
        sa.Column("verified_audio_record_id", sa.Text, nullable=True),
    )
    op.create_foreign_key(
        "fk_speaking_progress_verified_audio_record",
        "speaking_progress",
        "audio_records",
        ["verified_audio_record_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_speaking_progress_verified_audio_record",
        "speaking_progress",
        type_="foreignkey",
    )
    op.drop_column("speaking_progress", "verified_audio_record_id")
    op.drop_column("audio_records", "server_verification_version")
    op.drop_column("audio_records", "audio_sha256")
    op.drop_column("audio_records", "server_verified_at")
