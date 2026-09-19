"""Flag test/synthetic student accounts so they can be excluded from
teacher-facing views and purged in bulk before a real launch.

Revision ID: 0040
Revises: 0039
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column("is_test_account", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_students_is_test_account", "students", ["is_test_account"])


def downgrade() -> None:
    op.drop_index("ix_students_is_test_account", table_name="students")
    op.drop_column("students", "is_test_account")
