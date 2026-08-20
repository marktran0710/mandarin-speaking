"""Create local-only demo accounts for a fresh development database.

This script refuses to run in production. Real deployments must provision
accounts with individual passwords through the admin console.
"""
from __future__ import annotations

import os
import uuid

import auth
from database import connect_db


def _ensure_account(table: str, name: str, password: str) -> str:
    with connect_db() as db:
        existing = db.execute(
            f"SELECT id FROM {table} WHERE lower(name) = lower(%s)", (name,)
        ).fetchone()
        if existing:
            return existing["id"]
        row = db.execute(
            f"INSERT INTO {table} (id, name, password, password_reset_required) "
            "VALUES (%s, %s, %s, false) RETURNING id",
            (str(uuid.uuid4()), name, auth.hash_password(password)),
        ).fetchone()
    return row["id"]


def main() -> None:
    if os.getenv("APP_ENV", "development").lower() == "production":
        raise SystemExit("Demo accounts are disabled in production.")
    password = os.getenv("DEMO_ACCOUNT_PASSWORD", "123456")
    if len(password) < 6:
        raise SystemExit("DEMO_ACCOUNT_PASSWORD must be at least 6 characters.")
    student_id = _ensure_account("students", "Student Demo", password)
    teacher_id = _ensure_account("teachers", "Teacher Demo", password)
    print(f"Demo student ready: Student Demo ({student_id})")
    print(f"Demo teacher ready: Teacher Demo ({teacher_id})")
    print("Demo password: use DEMO_ACCOUNT_PASSWORD or the local default 123456")


if __name__ == "__main__":
    main()
