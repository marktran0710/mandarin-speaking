"""Hash legacy passwords and quarantine the shared default.

Revision ID: 0019
Revises: 0018
"""
from __future__ import annotations

import bcrypt
import hashlib
import hmac
import secrets

from alembic import op
import sqlalchemy as sa


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_PEPPER = b"mandarin-speaking-password-v1\x00"
_ROUNDS = 12


def _hash(password: str) -> str:
    material = _PEPPER + hashlib.sha256(password.encode("utf-8")).digest()
    return bcrypt.hashpw(material, bcrypt.gensalt(rounds=_ROUNDS)).decode("ascii")


def _migrate_table(table: str) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT id, password FROM {table}")).mappings().all()
    for row in rows:
        stored = row["password"] or ""
        if stored.startswith(("$2a$", "$2b$", "$2y$")):
            bind.execute(sa.text(f"UPDATE {table} SET password_reset_required = false WHERE id = :id"), {"id": row["id"]})
            continue
        if hmac.compare_digest(stored, "123456"):
            replacement = _hash(secrets.token_urlsafe(32))
            required = True
        else:
            replacement = _hash(stored)
            required = False
        bind.execute(
            sa.text(f"UPDATE {table} SET password = :password, password_reset_required = :required WHERE id = :id"),
            {"password": replacement, "required": required, "id": row["id"]},
        )


def upgrade() -> None:
    op.add_column("students", sa.Column("password_reset_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("teachers", sa.Column("password_reset_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    _migrate_table("students")
    _migrate_table("teachers")


def downgrade() -> None:
    op.drop_column("teachers", "password_reset_required")
    op.drop_column("students", "password_reset_required")
