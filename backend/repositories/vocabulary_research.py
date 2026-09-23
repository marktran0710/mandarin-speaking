"""Persistence boundary for vocab_research_studies / vocab_research_participants.

Pure CRUD only - no policy decisions (those live in
domain/vocabulary/research_policy.py). Every function takes an already-open
connection so the caller controls the transaction boundary.
"""
from typing import Optional


def find_active_participation(db, student_id: str) -> Optional[dict]:
    """The student's participant row joined with its study, if any exists at
    all (regardless of study/participant status - the caller decides what
    "active" means from the raw fields). A student can only ever be in one
    study at a time (no such constraint is enforced yet since only one study
    is expected to run at once in this Epic; enforcing "at most one active
    study per student" is deferred until a second concurrent study is a real
    possibility)."""
    return db.execute(
        """
        SELECT
            p.student_id,
            p.active AS participant_active,
            p.class_id,
            p.sequence_id,
            s.id AS study_id,
            s.status AS study_status,
            s.policy_version,
            s.assignment_version,
            s.config_json
        FROM vocab_research_participants p
        JOIN vocab_research_studies s ON s.id = p.study_id
        WHERE p.student_id = %s
        ORDER BY p.created_at DESC
        LIMIT 1
        """,
        (student_id,),
    ).fetchone()


def insert_study(
    db,
    *,
    id: str,
    name: str,
    status: str,
    config_json: dict,
    policy_version: str,
    assignment_version: str,
    created_at: str,
) -> None:
    from psycopg.types.json import Jsonb

    db.execute(
        """
        INSERT INTO vocab_research_studies
            (id, name, status, config_json, policy_version, assignment_version, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (id, name, status, Jsonb(config_json), policy_version, assignment_version, created_at),
    )


def insert_participant(
    db,
    *,
    study_id: str,
    student_id: str,
    class_id: Optional[str],
    sequence_id: Optional[str],
    active: bool,
    created_at: str,
) -> None:
    db.execute(
        """
        INSERT INTO vocab_research_participants
            (study_id, student_id, class_id, sequence_id, active, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (study_id, student_id, class_id, sequence_id, active, created_at),
    )
