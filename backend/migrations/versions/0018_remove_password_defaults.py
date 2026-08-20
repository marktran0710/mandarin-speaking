"""Remove insecure database-level password defaults.

Legacy plaintext values remain readable so the login handlers can replace
them with bcrypt hashes after a successful verification.

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("students", "password", existing_type=sa.Text(), server_default=None)
    op.alter_column("teachers", "password", existing_type=sa.Text(), server_default=None)


def downgrade() -> None:
    op.alter_column("students", "password", existing_type=sa.Text(), server_default="123456")
    op.alter_column("teachers", "password", existing_type=sa.Text(), server_default="123456")
