"""Remove runtime data belonging to the retired Lesson 5-8 stories.

The command is deliberately a dry run unless ``--execute`` is supplied::

    python -m scripts.purge_custom_stories
    python -m scripts.purge_custom_stories --execute

It only removes rows whose story/topic id is in the explicit manifest below
(including the historic ``teacher-`` aliases). Shared BKT models and
word-level SRS schedules remain intact; vocabulary mastery is rebuilt only for
students whose scoped quiz responses were removed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import connect_db  # noqa: E402
from analytics.bkt_mastery import rebuild_student_vocabulary_mastery  # noqa: E402
from config import settings  # noqa: E402


# Kept in one manifest instead of deriving targets at runtime: this makes a
# destructive command reviewable and protects unrelated stories from being
# removed accidentally. It covers every Lesson 5-8 story source, including
# legacy IDs that appeared only in old fixtures.
TARGET_STORY_IDS: tuple[str, ...] = (
    "custom-story-1785137028726",
    "custom-story-1785204635939",
    "custom-story-1785205277637",
    "custom-story-1785235297869",
    "custom-story-1785310310407",
    "custom-story-1784770916021",
    "custom-story-1783739495489",
    "custom-story-1782894133778",
    "custom-story-1783556771524",
    "custom-story-1784207590772",
    "lesson-wo-de-fangjian",
    "lesson-vv-kan",
    "modern-chinese-l6-dialogue-1",
    "modern-chinese-l6-dialogue-2",
    "modern-chinese-l6-reading",
    "modern-chinese-l7-dialogue-1",
    "modern-chinese-l7-dialogue-2",
    "modern-chinese-l7-reading",
    "modern-chinese-l8-dialogue-1",
    "modern-chinese-l8-dialogue-2",
    "modern-chinese-l8-reading",
)

def target_ids_with_aliases(story_ids: Iterable[str] = TARGET_STORY_IDS) -> tuple[str, ...]:
    """Return canonical, tier, and legacy ``teacher-`` topic identifiers."""
    canonical = tuple(story_ids)
    tiered = tuple(
        identifier
        for story_id in canonical
        for identifier in (story_id, f"{story_id}-medium", f"{story_id}-hard")
    )
    teacher_aliases = tuple(f"teacher-{identifier}" for identifier in tiered)
    return tiered + teacher_aliases


TARGET_IDS = target_ids_with_aliases()


def _table_exists(db: Any, table_name: str) -> bool:
    return bool(db.execute("SELECT to_regclass(%s) AS name", (f"public.{table_name}",)).fetchone()["name"])


def _column_exists(db: Any, table_name: str, column_name: str) -> bool:
    return bool(
        db.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
            (table_name, column_name),
        ).fetchone()
    )


def _count(db: Any, sql: str, params: tuple[Any, ...]) -> int:
    return int(db.execute(sql, params).fetchone()["count"])


def _audio_ids(db: Any, target_ids: tuple[str, ...]) -> list[str]:
    if not _table_exists(db, "audio_records"):
        return []
    rows = db.execute(
        "SELECT id FROM audio_records WHERE topic_id = ANY(%s)", (list(target_ids),)
    ).fetchall()
    return [str(row["id"]) for row in rows]


def _item_id_patterns(target_ids: tuple[str, ...]) -> list[str]:
    return [f"{story_id}:%" for story_id in target_ids]


def _contains_id_patterns(target_ids: tuple[str, ...]) -> list[str]:
    """Patterns for legacy JSON/text columns that embed a story id."""
    return [f"%{story_id}%" for story_id in target_ids]


def _response_scope(target_ids: tuple[str, ...]) -> tuple[str, tuple[Any, ...]]:
    return (
        "lesson_id = ANY(%s) OR quiz_id = ANY(%s) OR item_id LIKE ANY(%s)",
        (list(target_ids), list(target_ids), _item_id_patterns(target_ids)),
    )


def _affected_response_students(db: Any, target_ids: tuple[str, ...]) -> list[str]:
    if not _table_exists(db, "vocab_quiz_responses"):
        return []
    where, params = _response_scope(target_ids)
    rows = db.execute(
        f"SELECT DISTINCT student_id FROM vocab_quiz_responses WHERE student_id IS NOT NULL AND ({where})",
        params,
    ).fetchall()
    return [str(row["student_id"]) for row in rows]


def _rebuild_affected_mastery(db: Any, student_ids: Iterable[str]) -> int:
    if not _table_exists(db, "student_vocab_mastery"):
        return 0
    rebuilt = 0
    for student_id in student_ids:
        rebuild_student_vocabulary_mastery(db, student_id)
        rebuilt += 1
    return rebuilt


UPLOAD_ROOT = Path(settings.upload_dir).resolve()


def _upload_path(value: Any) -> Path | None:
    """Resolve a stored upload URL while refusing paths outside UPLOAD_ROOT."""
    if not isinstance(value, str) or not value:
        return None
    if value.startswith("/uploads/"):
        relative = value.removeprefix("/uploads/")
    elif value.startswith("uploads/"):
        relative = value.removeprefix("uploads/")
    else:
        return None
    candidate = (UPLOAD_ROOT / relative.replace("/", os.sep)).resolve()
    if UPLOAD_ROOT not in candidate.parents:
        return None
    return candidate


def _collect_upload_paths(value: Any, paths: set[Path]) -> None:
    if isinstance(value, dict):
        for child in value.values():
            _collect_upload_paths(child, paths)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_upload_paths(child, paths)
    else:
        path = _upload_path(value)
        if path is not None:
            paths.add(path)


def _target_upload_paths(
    db: Any,
    target_ids: tuple[str, ...],
    audio_ids: list[str],
    submission_ids: list[str],
) -> set[Path]:
    """Snapshot local media paths before deleting their database owners."""
    paths: set[Path] = set()
    if _table_exists(db, "custom_stories"):
        for row in db.execute(
            "SELECT frames FROM custom_stories WHERE id = ANY(%s)", (list(target_ids),)
        ).fetchall():
            _collect_upload_paths(row.get("frames"), paths)
    if _table_exists(db, "audio_records"):
        for row in db.execute(
            "SELECT image_url, audio_url FROM audio_records WHERE id = ANY(%s)",
            (audio_ids,),
        ).fetchall():
            _collect_upload_paths(row, paths)
    if _table_exists(db, "story_submissions"):
        for row in db.execute(
            "SELECT concatenated_audio_url, scenes FROM story_submissions WHERE id = ANY(%s)",
            (submission_ids,),
        ).fetchall():
            _collect_upload_paths(row, paths)
    if audio_ids or submission_ids:
        if _table_exists(db, "media_assets"):
            for row in db.execute(
                "SELECT storage_key FROM media_assets WHERE source_id = ANY(%s)",
                (audio_ids + submission_ids,),
            ).fetchall():
                _collect_upload_paths(row.get("storage_key"), paths)
    return paths


def _remove_upload_paths(paths: Iterable[Path]) -> tuple[int, list[Path]]:
    removed = 0
    failed: list[Path] = []
    for path in sorted(set(paths)):
        try:
            if path.is_file():
                path.unlink()
                removed += 1
        except OSError:
            failed.append(path)
    return removed, failed


def deletion_order() -> tuple[str, ...]:
    """Child records first; ``custom_stories`` is intentionally last."""
    return (
        "teacher_pronunciation_ratings",
        "media_assets",
        "learning_measurement_events",
        "speaking_progress",
        "audio_records",
        "story_submissions",
        "vocab_quiz_attempts",
        "vocab_quiz_responses",
        "custom_stories",
    )


def count_candidates(db: Any, target_ids: tuple[str, ...] = TARGET_IDS) -> dict[str, int]:
    """Count every affected row without changing the database."""
    audio_ids = _audio_ids(db, target_ids)
    counts: dict[str, int] = {}
    direct_topic_tables = {
        "learning_measurement_events": "topic_id",
        "speaking_progress": "topic_id",
        "audio_records": "topic_id",
        "story_submissions": "story_id",
        "vocab_quiz_attempts": "story_id",
        "custom_stories": "id",
    }
    for table, column in direct_topic_tables.items():
        if not _table_exists(db, table):
            continue
        where = f"{column} = ANY(%s)"
        params: tuple[Any, ...] = (list(target_ids),)
        if table == "vocab_quiz_attempts":
            where += " OR question_results::text LIKE ANY(%s)"
            params = (list(target_ids), _contains_id_patterns(target_ids))
        counts[table] = _count(
            db,
            f"SELECT count(*) AS count FROM {table} WHERE {where}",
            params,
        )

    if _table_exists(db, "vocab_quiz_responses"):
        response_where, response_params = _response_scope(target_ids)
        counts["vocab_quiz_responses"] = _count(
            db,
            f"SELECT count(*) AS count FROM vocab_quiz_responses WHERE {response_where}",
            response_params,
        )
    if _table_exists(db, "teacher_pronunciation_ratings"):
        rating_where: list[str] = []
        rating_params: list[Any] = []
        if _column_exists(db, "teacher_pronunciation_ratings", "audio_record_id"):
            rating_where.append("audio_record_id = ANY(%s)")
            rating_params.append(audio_ids)
        if _column_exists(db, "teacher_pronunciation_ratings", "item_id"):
            rating_where.append("item_id LIKE ANY(%s)")
            rating_params.append(_item_id_patterns(target_ids))
        if rating_where:
            counts["teacher_pronunciation_ratings"] = _count(
                db,
                "SELECT count(*) AS count FROM teacher_pronunciation_ratings WHERE "
                + " OR ".join(rating_where),
                tuple(rating_params),
            )
    submission_ids: list[str] = []
    if _table_exists(db, "story_submissions"):
        submission_ids = [
            str(row["id"])
            for row in db.execute(
                "SELECT id FROM story_submissions WHERE story_id = ANY(%s)",
                (list(target_ids),),
            ).fetchall()
        ]
    if (audio_ids or submission_ids) and _table_exists(db, "media_assets"):
        counts["media_assets"] = _count(
            db,
            "SELECT count(*) AS count FROM media_assets WHERE source_id = ANY(%s)",
            (audio_ids + submission_ids,),
        )
    return {table: counts.get(table, 0) for table in deletion_order() if table in counts}


def _delete(db: Any, table: str, where: str, params: tuple[Any, ...]) -> int:
    return int(db.execute(f"DELETE FROM {table} WHERE {where}", params).rowcount)


def execute_purge(db: Any, target_ids: tuple[str, ...] = TARGET_IDS) -> dict[str, int]:
    """Delete scoped runtime rows inside the caller's transaction."""
    audio_ids = _audio_ids(db, target_ids)
    affected_students = _affected_response_students(db, target_ids)
    submission_ids: list[str] = []
    if _table_exists(db, "story_submissions"):
        submission_ids = [
            str(row["id"])
            for row in db.execute(
                "SELECT id FROM story_submissions WHERE story_id = ANY(%s)",
                (list(target_ids),),
            ).fetchall()
        ]
    deleted: dict[str, int] = {}
    if _table_exists(db, "teacher_pronunciation_ratings"):
        rating_where: list[str] = []
        rating_params: list[Any] = []
        if _column_exists(db, "teacher_pronunciation_ratings", "audio_record_id"):
            rating_where.append("audio_record_id = ANY(%s)")
            rating_params.append(audio_ids)
        if _column_exists(db, "teacher_pronunciation_ratings", "item_id"):
            rating_where.append("item_id LIKE ANY(%s)")
            rating_params.append(_item_id_patterns(target_ids))
        if rating_where:
            deleted["teacher_pronunciation_ratings"] = _delete(
                db, "teacher_pronunciation_ratings", " OR ".join(rating_where), tuple(rating_params)
            )
    if (audio_ids or submission_ids) and _table_exists(db, "media_assets"):
        deleted["media_assets"] = _delete(
            db, "media_assets", "source_id = ANY(%s)", (audio_ids + submission_ids,)
        )

    for table, column in (
        ("learning_measurement_events", "topic_id"),
        ("speaking_progress", "topic_id"),
        ("audio_records", "topic_id"),
        ("story_submissions", "story_id"),
        ("vocab_quiz_attempts", "story_id"),
    ):
        if _table_exists(db, table):
            where = f"{column} = ANY(%s)"
            params: tuple[Any, ...] = (list(target_ids),)
            if table == "vocab_quiz_attempts":
                where += " OR question_results::text LIKE ANY(%s)"
                params = (list(target_ids), _contains_id_patterns(target_ids))
            deleted[table] = _delete(db, table, where, params)
    if _table_exists(db, "vocab_quiz_responses"):
        response_where, response_params = _response_scope(target_ids)
        deleted["vocab_quiz_responses"] = _delete(
            db,
            "vocab_quiz_responses",
            response_where,
            response_params,
        )
    _rebuild_affected_mastery(db, affected_students)
    if _table_exists(db, "custom_stories"):
        deleted["custom_stories"] = _delete(db, "custom_stories", "id = ANY(%s)", (list(target_ids),))
    return {table: deleted.get(table, 0) for table in deletion_order() if table in deleted}


def verify_no_candidates(db: Any, target_ids: tuple[str, ...] = TARGET_IDS) -> dict[str, int]:
    """Return remaining scoped rows; all values should be zero after execute."""
    return count_candidates(db, target_ids)


def _record_audit(db: Any, counts: dict[str, int], *, dry_run: bool) -> None:
    """Keep a retention record without retaining the deleted story content."""
    if not _table_exists(db, "retention_audit_log"):
        return
    db.execute(
        """
        INSERT INTO retention_audit_log
            (actor_id, actor_role, action, reason, candidate_count, affected_ids, dry_run)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            "lesson-5-8-cleanup",
            "system",
            "delete",
            "Retire all story-derived Lesson 5-8 runtime data",
            sum(counts.values()),
            json.dumps({"story_ids": list(TARGET_STORY_IDS), "counts": counts}),
            dry_run,
        ),
    )


def _print_counts(label: str, counts: dict[str, int]) -> None:
    print(label)
    for table in deletion_order():
        if table in counts:
            print(f"  {table}: {counts[table]}")
    print(f"  total: {sum(counts.values())}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--execute", action="store_true", help="perform the deletion; default is dry-run")
    args = parser.parse_args()

    upload_paths: set[Path] = set()
    with connect_db() as db:
        before = count_candidates(db)
        audio_ids = _audio_ids(db, TARGET_IDS)
        submission_ids = [
            str(row["id"])
            for row in db.execute(
                "SELECT id FROM story_submissions WHERE story_id = ANY(%s)",
                (list(TARGET_IDS),),
            ).fetchall()
        ] if _table_exists(db, "story_submissions") else []
        upload_paths = _target_upload_paths(db, TARGET_IDS, audio_ids, submission_ids)
        _print_counts("Candidates for Lesson 5-8 runtime cleanup:", before)
        print(f"  local upload files found: {len(upload_paths)}")
        if not args.execute:
            print("Dry run only. Re-run with --execute to delete these rows.")
            return
        deleted = execute_purge(db)
        _print_counts("Deleted:", deleted)
        remaining = verify_no_candidates(db)
        _print_counts("Verification (must be zero):", remaining)
        if any(remaining.values()):
            raise RuntimeError("Scoped rows remain; transaction will be rolled back.")
        _record_audit(db, deleted, dry_run=False)
        # The transaction is committed by database.connect_db() only after
        # verification succeeds. Shared BKT model tables and word-level SRS
        # schedules remain untouched because they aggregate other lessons.

    removed, failed = _remove_upload_paths(upload_paths)
    print(f"Removed local upload files: {removed}")
    if failed:
        print("Could not remove local upload files:")
        for path in failed:
            print(f"  {path}")
        raise RuntimeError("Database purge committed, but some local media files remain.")


if __name__ == "__main__":
    main()
