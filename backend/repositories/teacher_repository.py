"""Persistence boundary for the ``teachers`` table.

Pure CRUD only - no session/auth decisions and no idempotency/visibility
business rules (those live in services/teacher_service.py). Every function
takes an already-open connection so the caller controls the transaction
boundary.
"""
from typing import Optional


def find_all(db) -> list[dict]:
    return db.execute("SELECT * FROM teachers ORDER BY lower(name)").fetchall()


def exists_name_ci(db, name: str) -> Optional[dict]:
    return db.execute(
        "SELECT 1 FROM teachers WHERE lower(name) = lower(%s)", (name,)
    ).fetchone()


def find_by_name_ci(db, name: str) -> Optional[dict]:
    return db.execute(
        "SELECT * FROM teachers WHERE lower(name) = lower(%s)", (name,)
    ).fetchone()


def insert(db, teacher_id: str, name: str, password_hash: str) -> dict:
    return db.execute(
        "INSERT INTO teachers (id, name, password) VALUES (%s, %s, %s) RETURNING *",
        (teacher_id, name, password_hash),
    ).fetchone()


def update_password_hash(db, teacher_id: str, password_hash: str) -> None:
    """Silent rehash-on-verify write; no RETURNING, matching prior behavior."""
    db.execute(
        "UPDATE teachers SET password = %s WHERE id = %s",
        (password_hash, teacher_id),
    )


def find_name_conflict(db, name: str, exclude_teacher_id: str) -> Optional[dict]:
    return db.execute(
        "SELECT 1 FROM teachers WHERE lower(name) = lower(%s) AND id <> %s",
        (name, exclude_teacher_id),
    ).fetchone()


def update_fields(db, teacher_id: str, set_clauses: list[str], params: list) -> Optional[dict]:
    query_params = [*params, teacher_id]
    return db.execute(
        f"UPDATE teachers SET {', '.join(set_clauses)} WHERE id = %s RETURNING *",
        tuple(query_params),
    ).fetchone()


def delete(db, teacher_id: str) -> Optional[dict]:
    return db.execute(
        "DELETE FROM teachers WHERE id = %s RETURNING id", (teacher_id,)
    ).fetchone()
