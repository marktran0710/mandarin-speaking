"""Add an admin-managed status to student accounts.

Teacher accounts already had an active/inactive status. Keeping the same
field on students lets the admin console suspend either account type without
deleting its learning history.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
    )
    op.create_check_constraint(
        "ck_students_status",
        "students",
        "status IN ('active', 'inactive')",
    )
    op.create_index(
        "uq_students_lower_name",
        "students",
        [sa.text("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_students_lower_name", table_name="students")
    op.drop_constraint("ck_students_status", "students", type_="check")
    op.drop_column("students", "status")
