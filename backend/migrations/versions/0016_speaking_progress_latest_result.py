"""Add the resumable per-scene submission snapshot to speaking progress.

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "speaking_progress",
        sa.Column("latest_result", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("speaking_progress", "latest_result")
