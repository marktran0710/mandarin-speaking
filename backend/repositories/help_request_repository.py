"""Persistence boundary for the ``help_requests`` table.

Pure CRUD only. Every function takes an already-open connection so the
caller controls the transaction boundary.
"""
from typing import Optional


def find_all(db, limit: int, skip: int) -> list[dict]:
    return db.execute(
        """
        SELECT * FROM help_requests
        ORDER BY
            CASE status WHEN 'open' THEN 0 ELSE 1 END,
            created_at DESC
        LIMIT %s OFFSET %s
        """,
        (limit, skip),
    ).fetchall()


def upsert(
    db,
    *,
    id: str,
    student_name: str,
    message: str,
    status: str,
    created_at,
    resolved_at,
) -> None:
    db.execute(
        """
        INSERT INTO help_requests (
            id, student_name, message, status, created_at, resolved_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            student_name = EXCLUDED.student_name,
            message = EXCLUDED.message,
            status = EXCLUDED.status,
            created_at = EXCLUDED.created_at,
            resolved_at = EXCLUDED.resolved_at
        """,
        (id, student_name, message, status, created_at, resolved_at),
    )


def resolve(db, request_id: str, resolved_at: str) -> Optional[dict]:
    return db.execute(
        """
        UPDATE help_requests
        SET status = 'resolved', resolved_at = %s
        WHERE id = %s
        RETURNING *
        """,
        (resolved_at, request_id),
    ).fetchone()
