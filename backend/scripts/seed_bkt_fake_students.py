"""Seed the 25 synthetic BKT students and their quiz evidence.

This is a local/demo data import. It creates deterministic student roster rows
whose ids match ``bkt_fake_our_story_25_students.json`` and imports the raw
quiz attempts plus the normalized BKT response ledger. It is idempotent: rerun
it to repair or refresh the same synthetic rows without duplicating them.

Run from ``backend/`` with::

    python -m scripts.seed_bkt_fake_students

The imported rows are synthetic and must not be used as real learner evidence
or as a replacement for the production BKT defaults.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

import auth
from analytics.bkt_mastery import (
    rebuild_student_vocabulary_mastery,
    response_rows_for_attempt,
    upsert_raw_responses,
)
from database import connect_db


DEFAULT_DATA = Path(__file__).resolve().parent / "data" / "bkt_fake_our_story_25_students.json"
DEFAULT_STORY_TITLE = "我們去喝下午茶"
DEFAULT_PASSWORD = "bkt-demo-2026"
EXPECTED_STUDENT_COUNT = 25
EXPECTED_ATTEMPT_COUNT = EXPECTED_STUDENT_COUNT * 3
EXPECTED_RESPONSE_COUNT = EXPECTED_STUDENT_COUNT * (20 + 22 + 25)
SYNTHETIC_RESOLVER_VERSION = "synthetic-fixture-v1"


def _remap_attempt(attempt: dict[str, Any], source_story_id: str, target_story_id: str) -> dict[str, Any]:
    """Copy one attempt while binding all story-bearing ids to the live story."""
    mapped = copy.deepcopy(attempt)
    mapped["storyId"] = target_story_id
    mapped["baseStoryId"] = target_story_id
    for result in mapped.get("questionResults") or []:
        result["lessonId"] = target_story_id
        # Synthetic evidence follows the same normalized-ledger contract as a
        # server-resolved response, but remains structurally isolated by its
        # origin and can never be promoted by the database deployment guard.
        result["authoritativeResolved"] = True
        result["resolverVersion"] = SYNTHETIC_RESOLVER_VERSION
        result["activityType"] = "diagnostic"
        for key in ("itemId", "diagnosticExposureId"):
            value = result.get(key)
            if isinstance(value, str):
                result[key] = value.replace(source_story_id, target_story_id)
    return mapped


def _resolve_story_id(db: Any, requested: str | None, title: str) -> str:
    if requested:
        row = db.execute(
            "SELECT id FROM custom_stories WHERE id = %s",
            (requested,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Story id {requested!r} was not found in custom_stories")
        return str(row["id"])

    row = db.execute(
        """
        SELECT id
        FROM custom_stories
        WHERE title = %s AND published = TRUE
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (title,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Published story {title!r} was not found in custom_stories")
    return str(row["id"])


def _load_attempts(path: Path) -> tuple[str, list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    source_story_id = str(payload.get("storyId") or "")
    attempts = payload.get("attempts")
    if not source_story_id or not isinstance(attempts, list):
        raise RuntimeError(f"Invalid synthetic BKT fixture: {path}")
    if len(attempts) != EXPECTED_ATTEMPT_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_ATTEMPT_COUNT} attempts, found {len(attempts)} in {path}"
        )
    return source_story_id, attempts


def _student_rows(attempts: list[dict[str, Any]]) -> list[tuple[str, str]]:
    rows: dict[str, str] = {}
    for attempt in attempts:
        student_id = str(attempt.get("studentId") or "").strip()
        student_name = str(attempt.get("studentName") or "").strip()
        if not student_id or not student_name:
            raise RuntimeError("Every synthetic attempt needs studentId and studentName")
        previous = rows.setdefault(student_id, student_name)
        if previous != student_name:
            raise RuntimeError(f"Student {student_id!r} has inconsistent names")
    result = sorted(rows.items())
    if len(result) != EXPECTED_STUDENT_COUNT:
        raise RuntimeError(f"Expected {EXPECTED_STUDENT_COUNT} students, found {len(result)}")
    return result


def seed(data_path: Path, password: str, story_id: str | None) -> dict[str, Any]:
    if os.getenv("APP_ENV", "development").lower() == "production":
        raise RuntimeError("Synthetic BKT student seeding is disabled in production")
    auth.validate_password_policy(password)
    source_story_id, source_attempts = _load_attempts(data_path)
    students = _student_rows(source_attempts)

    with connect_db() as db:
        target_story_id = _resolve_story_id(db, story_id, DEFAULT_STORY_TITLE)
        password_hash = auth.hash_password(password)

        for student_id, student_name in students:
            db.execute(
                """
                INSERT INTO students (id, name, password, status, password_reset_required)
                VALUES (%s, %s, %s, 'active', FALSE)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    password = EXCLUDED.password,
                    status = 'active',
                    password_reset_required = FALSE
                """,
                (student_id, student_name, password_hash),
            )

        mapped_attempts = [
            _remap_attempt(attempt, source_story_id, target_story_id)
            for attempt in source_attempts
        ]
        attempt_ids = [str(attempt["id"]) for attempt in mapped_attempts]
        incompatible = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM vocab_quiz_responses
            WHERE attempt_id = ANY(%s) AND evidence_origin <> 'synthetic'
            """,
            (attempt_ids,),
        ).fetchone()["count"]
        if incompatible:
            raise RuntimeError(
                "Synthetic fixture ids already exist as non-synthetic ledger evidence; "
                "use a clean non-production database instead of rewriting immutable rows."
            )
        for attempt in mapped_attempts:
            db.execute(
                """
                INSERT INTO vocab_quiz_attempts
                    (id, story_id, student_name, student_id, mode, completed_at,
                     total_questions, correct_count, total_time_ms, question_results)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    story_id = EXCLUDED.story_id,
                    student_name = EXCLUDED.student_name,
                    student_id = EXCLUDED.student_id,
                    mode = EXCLUDED.mode,
                    completed_at = EXCLUDED.completed_at,
                    total_questions = EXCLUDED.total_questions,
                    correct_count = EXCLUDED.correct_count,
                    total_time_ms = EXCLUDED.total_time_ms,
                    question_results = EXCLUDED.question_results
                """,
                (
                    attempt["id"],
                    target_story_id,
                    attempt["studentName"],
                    attempt["studentId"],
                    attempt["mode"],
                    attempt["completedAt"],
                    attempt["totalQuestions"],
                    attempt["correctCount"],
                    attempt["totalTimeMs"],
                    Jsonb(attempt["questionResults"]),
                ),
            )
            response_rows = response_rows_for_attempt(attempt, attempt["studentId"])
            for row in response_rows:
                row["evidence_origin"] = "synthetic"
            upsert_raw_responses(db, response_rows)

        for student_id, _student_name in students:
            rebuild_student_vocabulary_mastery(db, student_id)

        student_ids = [student_id for student_id, _student_name in students]
        counts = {
            "students": db.execute(
                "SELECT COUNT(*) AS count FROM students WHERE id = ANY(%s)",
                (student_ids,),
            ).fetchone()["count"],
            "attempts": db.execute(
                "SELECT COUNT(*) AS count FROM vocab_quiz_attempts WHERE id = ANY(%s)",
                (attempt_ids,),
            ).fetchone()["count"],
            "responses": db.execute(
                """
                SELECT COUNT(*) AS count
                FROM vocab_quiz_responses
                WHERE attempt_id = ANY(%s) AND bkt_eligible = TRUE
                  AND evidence_origin = 'synthetic'
                  AND resolver_version = %s
                """,
                (attempt_ids, SYNTHETIC_RESOLVER_VERSION),
            ).fetchone()["count"],
            "mastery": db.execute(
                "SELECT COUNT(*) AS count FROM student_vocab_mastery WHERE student_id = ANY(%s)",
                (student_ids,),
            ).fetchone()["count"],
        }
        expected = {
            "students": EXPECTED_STUDENT_COUNT,
            "attempts": EXPECTED_ATTEMPT_COUNT,
            "responses": EXPECTED_RESPONSE_COUNT,
        }
        mismatches = {
            key: {"expected": value, "actual": int(counts[key])}
            for key, value in expected.items()
            if int(counts[key]) != value
        }
        if mismatches:
            raise RuntimeError(f"Synthetic BKT seed verification failed: {mismatches}")
    return {"storyId": target_story_id, "password": password, **counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--story-id", help="Override the published story id; defaults to the title match.")
    parser.add_argument(
        "--password",
        default=os.getenv("BKT_DEMO_STUDENT_PASSWORD", DEFAULT_PASSWORD),
        help="Shared local/demo password for all synthetic accounts.",
    )
    args = parser.parse_args()
    result = seed(args.data, args.password, args.story_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
