"""Reset production quiz/audio learning data while preserving authored stories.

The command is dry-run by default.  The complete local reset is explicit::

    python -m scripts.reset_learning_content --quizzes --audio \
        --dependent-learning-state --execute

It does not touch students, teachers, accounts, authentication, story rows,
story images, or isolated ``vocab_research_*`` tables.  Research-tagged rows
in the shared quiz-attempt/response tables are also retained.  Runtime audio
directories ``uploads/audio`` and ``uploads/story_audio`` are in scope; the
separate ``uploads/examples`` fixture directory and all image directories are
not.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg.types.json import Jsonb  # noqa: E402

from config import settings  # noqa: E402
from db import connect_db  # noqa: E402
from services.content.reset import (  # noqa: E402
    clean_json_value,
    clean_story_content,
    contains_nonempty_audio_reference,
    story_preservation_snapshot,
)


QUIZ_TABLES = (
    "vocab_quiz_attempts",
    "vocab_quiz_responses",
)

DEPENDENT_TABLES = (
    "student_vocab_mastery",
    "student_vocab_srs",
    "student_vocab_srs_events",
    "speaking_progress",
    "learning_measurement_events",
    "bkt_model_student_folds",
    "bkt_model_refit_requests",
    "teacher_pronunciation_ratings",
)

AUDIO_MEDIA_PREDICATE = """
    (
        kind ILIKE '%%audio%%'
        OR mime_type ILIKE 'audio/%%'
        OR storage_key ILIKE '/uploads/audio/%%'
        OR storage_key ILIKE '/uploads/story_audio/%%'
    )
"""


def _table_exists(db: Any, table_name: str) -> bool:
    return bool(
        db.execute(
            "SELECT to_regclass(%s) AS name",
            (f"public.{table_name}",),
        ).fetchone()["name"]
    )


def _column_exists(db: Any, table_name: str, column_name: str) -> bool:
    return bool(
        db.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
            """,
            (table_name, column_name),
        ).fetchone()
    )


def _public_tables(db: Any) -> set[str]:
    return {
        str(row["table_name"])
        for row in db.execute(
            """SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"""
        ).fetchall()
    }


def _count(db: Any, table: str, where: str = "TRUE", params: tuple[Any, ...] = ()) -> int:
    if not _table_exists(db, table):
        return 0
    return int(db.execute(f"SELECT count(*) AS count FROM {table} WHERE {where}", params).fetchone()["count"])


def _delete(db: Any, table: str, where: str = "TRUE", params: tuple[Any, ...] = ()) -> int:
    if not _table_exists(db, table):
        return 0
    return int(db.execute(f"DELETE FROM {table} WHERE {where}", params).rowcount)


def _research_scope(db: Any, table: str) -> str:
    """Scope shared production tables without deleting research evidence."""

    return "research_study_id IS NULL" if _column_exists(db, table, "research_study_id") else "TRUE"


def _story_rows(db: Any) -> list[dict[str, Any]]:
    if not _table_exists(db, "custom_stories"):
        raise RuntimeError("custom_stories is required; refusing to reset an unexpected schema")
    return list(
        db.execute(
            """
            SELECT id, title, lesson_number, lesson_sub_order, published,
                   frames, conversation_turns, story_vocabulary, story_phrases,
                   vocab_assessment
            FROM custom_stories
            ORDER BY lesson_number NULLS LAST, lesson_sub_order NULLS LAST, created_at, id
            """
        ).fetchall()
    )


def _audio_dir_paths() -> tuple[Path, Path]:
    upload_root = Path(settings.upload_dir).resolve()
    paths = tuple((upload_root / name).resolve() for name in ("audio", "story_audio"))
    for path in paths:
        try:
            path.relative_to(upload_root)
        except ValueError as exc:  # pragma: no cover - defensive configuration guard
            raise RuntimeError(f"Refusing an audio directory outside UPLOAD_DIR: {path}") from exc
    return paths  # type: ignore[return-value]


def _audio_files() -> list[Path]:
    files: list[Path] = []
    for directory in _audio_dir_paths():
        if directory.is_dir():
            files.extend(path for path in directory.rglob("*") if path.is_file())
    return sorted(files)


def _local_upload_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    if not value.startswith("/uploads/"):
        return None
    upload_root = Path(settings.upload_dir).resolve()
    candidate = (upload_root / value.removeprefix("/uploads/").replace("/", os.sep)).resolve()
    try:
        candidate.relative_to(upload_root)
    except ValueError:
        return None
    return candidate


def _story_image_paths(stories: Iterable[Mapping[str, Any]]) -> set[Path]:
    paths: set[Path] = set()
    for story in stories:
        frames = story.get("frames") or []
        for frame in frames:
            if isinstance(frame, Mapping):
                path = _local_upload_path(frame.get("imageUrl"))
                if path is not None:
                    paths.add(path)
    return paths


def _story_audio_reference_count(stories: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    for story in stories:
        for field in ("frames", "conversation_turns", "story_vocabulary", "story_phrases"):
            if contains_nonempty_audio_reference(story.get(field)):
                count += 1
    return count


def _validate_research_holds(db: Any) -> int:
    if not _table_exists(db, "media_assets"):
        return 0
    if not _column_exists(db, "media_assets", "research_hold_until"):
        return 0
    held = _count(
        db,
        "media_assets",
        f"{AUDIO_MEDIA_PREDICATE} AND (research_hold_until > now() OR research_hold_reason IS NOT NULL)",
    )
    if held:
        raise RuntimeError(
            f"{held} audio media rows are research-held; refusing to delete them. "
            "Resolve the hold or review ownership before rerunning."
        )
    return held


def _submission_rows(db: Any) -> list[dict[str, Any]]:
    if not _table_exists(db, "story_submissions"):
        return []
    return list(
        db.execute(
            "SELECT id, concatenated_audio_url, scenes, story_feedback FROM story_submissions"
        ).fetchall()
    )


def _submission_has_audio(row: Mapping[str, Any]) -> bool:
    return any(
        contains_nonempty_audio_reference(row.get(field))
        for field in ("concatenated_audio_url", "scenes", "story_feedback")
    )


def _clean_story_rows(
    db: Any,
    stories: list[dict[str, Any]],
    *,
    remove_quiz: bool,
    remove_audio: bool,
) -> int:
    if not (remove_quiz or remove_audio):
        return 0
    columns = {
        str(row["column_name"])
        for row in db.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'custom_stories'
            """
        ).fetchall()
    }
    changed = 0
    for story in stories:
        cleaned = clean_story_content(
            story,
            remove_quiz=remove_quiz,
            remove_audio=remove_audio,
        )
        assignments: list[str] = []
        values: list[Any] = []
        for column, value in (
            ("frames", cleaned["frames"]),
            ("conversation_turns", cleaned.get("conversation_turns")),
            ("story_vocabulary", cleaned.get("story_vocabulary")),
            ("story_phrases", cleaned.get("story_phrases")),
        ):
            if column in columns:
                assignments.append(f"{column} = %s")
                values.append(Jsonb(value) if value is not None else None)
        if remove_quiz and "vocab_assessment" in columns:
            assignments.append("vocab_assessment = %s")
            values.append(Jsonb([]))
        if assignments:
            values.append(story["id"])
            result = db.execute(
                f"UPDATE custom_stories SET {', '.join(assignments)} WHERE id = %s",
                tuple(values),
            )
            changed += int(result.rowcount)
    return changed


def _reset_submissions(db: Any) -> dict[str, int]:
    rows = _submission_rows(db)
    audio_submission_ids = [str(row["id"]) for row in rows if _submission_has_audio(row)]
    deleted = 0
    if audio_submission_ids:
        deleted = _delete(db, "story_submissions", "id = ANY(%s)", (audio_submission_ids,))
    # A text-only legacy submission can remain useful to the teacher, but its
    # compatibility audio keys are removed so it cannot point to deleted files.
    cleaned = 0
    for row in rows:
        if str(row["id"]) in audio_submission_ids:
            continue
        scenes = clean_json_value(row.get("scenes"), remove_audio=True)
        feedback = clean_json_value(row.get("story_feedback"), remove_audio=True)
        if row.get("concatenated_audio_url") is not None or scenes != row.get("scenes") or feedback != row.get("story_feedback"):
            db.execute(
                """
                UPDATE story_submissions
                SET concatenated_audio_url = NULL, scenes = %s, story_feedback = %s
                WHERE id = %s
                """,
                (Jsonb(scenes or []), Jsonb(feedback) if feedback is not None else None, row["id"]),
            )
            cleaned += 1
    return {"story_submissions_deleted": deleted, "story_submissions_cleared": cleaned}


def _media_audio_count(db: Any) -> int:
    return _count(db, "media_assets", AUDIO_MEDIA_PREDICATE)


def _delete_audio_data(db: Any) -> dict[str, int]:
    _validate_research_holds(db)
    counts: dict[str, int] = {}
    submission_counts = _reset_submissions(db) if _table_exists(db, "story_submissions") else {}
    counts.update(submission_counts)
    counts["audio_records"] = _delete(db, "audio_records")
    counts["media_assets_audio"] = _delete(db, "media_assets", AUDIO_MEDIA_PREDICATE)
    return counts


def _delete_quiz_data(db: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in QUIZ_TABLES:
        counts[table] = _delete(db, table, _research_scope(db, table))
    return counts


def _delete_dependent_state(db: Any) -> dict[str, int]:
    return {table: _delete(db, table) for table in DEPENDENT_TABLES if _table_exists(db, table)}


def _quiz_like_unknown_tables(db: Any) -> list[str]:
    known = set(QUIZ_TABLES) | {"custom_stories"}
    candidates = sorted(
        table
        for table in _public_tables(db)
        if table not in known
        and not table.startswith("vocab_research_")
        and ("quiz" in table.casefold() or "assessment" in table.casefold())
    )
    # Empty compatibility/retired tables do not contain reset scope. Only a
    # table with live rows needs an explicit audit before a destructive reset.
    return [
        table
        for table in candidates
        if _count(db, table) > 0
    ]


def _snapshot_counts(db: Any, *, preserve_research: bool = True) -> dict[str, int]:
    stories = _story_rows(db)
    counts = {
        "stories": _count(db, "custom_stories"),
        "frames": int(
            db.execute(
                """SELECT COALESCE(sum(jsonb_array_length(COALESCE(frames, '[]'::jsonb))), 0) AS count FROM custom_stories"""
            ).fetchone()["count"]
        ),
        "quiz_questions": int(
            db.execute(
                """SELECT COALESCE(sum(jsonb_array_length(COALESCE(vocab_assessment, '[]'::jsonb))), 0) AS count FROM custom_stories"""
            ).fetchone()["count"]
        ),
        "quiz_attempts": _count(db, "vocab_quiz_attempts", _research_scope(db, "vocab_quiz_attempts")) if preserve_research else _count(db, "vocab_quiz_attempts"),
        "quiz_responses": _count(db, "vocab_quiz_responses", _research_scope(db, "vocab_quiz_responses")) if preserve_research else _count(db, "vocab_quiz_responses"),
        "audio_records": _count(db, "audio_records"),
        "content_audio_references": sum(
            1
            for story in stories
            if any(
                contains_nonempty_audio_reference(story.get(field))
                for field in ("frames", "conversation_turns", "story_vocabulary", "story_phrases")
            )
        ),
        "audio_media_assets": _media_audio_count(db),
        "bkt_mastery": _count(db, "student_vocab_mastery"),
        "srs_states": _count(db, "student_vocab_srs"),
        "srs_events": _count(db, "student_vocab_srs_events"),
        "speaking_progress": _count(db, "speaking_progress"),
        "learning_measurement_events": _count(db, "learning_measurement_events"),
        "students": _count(db, "students"),
        "teachers": _count(db, "teachers"),
    }
    return counts


def _verify(
    db: Any,
    *,
    before_story_snapshot: dict[str, Any],
    image_paths: set[Path],
    remove_quiz: bool,
    remove_audio: bool,
    remove_dependent_state: bool,
) -> dict[str, Any]:
    stories = _story_rows(db)
    actual_snapshot = story_preservation_snapshot(
        stories,
        remove_quiz=remove_quiz,
        remove_audio=remove_audio,
    )
    if actual_snapshot != before_story_snapshot:
        raise RuntimeError("Story/frame identity or authored content changed during cleanup")
    missing_images = sorted(str(path) for path in image_paths if not path.is_file())
    if missing_images:
        raise RuntimeError(f"Story image files disappeared during cleanup: {missing_images[:5]}")

    remaining = _snapshot_counts(db)
    if remove_quiz and any(remaining[key] for key in ("quiz_questions", "quiz_attempts", "quiz_responses")):
        raise RuntimeError(f"Quiz reset verification failed: {remaining}")
    if remove_audio and any(remaining[key] for key in ("audio_records", "content_audio_references", "audio_media_assets")):
        raise RuntimeError(f"Audio reset verification failed: {remaining}")
    if remove_dependent_state and any(
        remaining[key]
        for key in (
            "bkt_mastery",
            "srs_states",
            "srs_events",
            "speaking_progress",
            "learning_measurement_events",
        )
    ):
        raise RuntimeError(f"Dependent learning-state reset verification failed: {remaining}")
    return remaining


def reset_learning_content(
    *,
    remove_quiz: bool,
    remove_audio: bool,
    remove_dependent_state: bool,
    execute: bool,
) -> dict[str, Any]:
    if not any((remove_quiz, remove_audio, remove_dependent_state)):
        raise ValueError("Choose at least one cleanup scope")

    audio_files_before = _audio_files() if remove_audio else []
    deleted: dict[str, int] = {}
    research_tables_untouched: list[str] = []
    with connect_db() as db:
        unknown_tables = _quiz_like_unknown_tables(db)
        if unknown_tables:
            raise RuntimeError(
                "Unexpected quiz-like tables require explicit audit before reset: "
                + ", ".join(unknown_tables)
            )
        _validate_research_holds(db) if remove_audio else None
        stories_before = _story_rows(db)
        before_story_snapshot = story_preservation_snapshot(
            stories_before,
            remove_quiz=remove_quiz,
            remove_audio=remove_audio,
        )
        image_paths = _story_image_paths(stories_before)
        missing_before = sorted(str(path) for path in image_paths if not path.is_file())
        if missing_before:
            raise RuntimeError(
                f"Referenced story images are already missing; refusing reset: {missing_before[:5]}"
            )
        before = _snapshot_counts(db)
        research_tables_untouched = sorted(
            table for table in _public_tables(db) if table.startswith("vocab_research_")
        )

        if not execute:
            return {
                "dryRun": True,
                "before": before,
                "audioFilesInScope": len(audio_files_before),
                "preservedImages": len(image_paths),
                "preservedStories": len(stories_before),
                "researchTablesUntouched": research_tables_untouched,
            }

        _clean_story_rows(
            db,
            stories_before,
            remove_quiz=remove_quiz,
            remove_audio=remove_audio,
        )
        if remove_quiz:
            deleted.update(_delete_quiz_data(db))
        if remove_audio:
            deleted.update(_delete_audio_data(db))
        if remove_dependent_state:
            deleted.update(_delete_dependent_state(db))
        remaining = _verify(
            db,
            before_story_snapshot=before_story_snapshot,
            image_paths=image_paths,
            remove_quiz=remove_quiz,
            remove_audio=remove_audio,
            remove_dependent_state=remove_dependent_state,
        )

    files_removed = 0
    if execute and remove_audio:
        for path in audio_files_before:
            if path.is_file():
                path.unlink()
                files_removed += 1
        remaining_files = _audio_files()
        if remaining_files:
            raise RuntimeError(
                "Database reset committed, but runtime audio files remain: "
                + ", ".join(str(path) for path in remaining_files[:5])
            )
    return {
        "dryRun": False,
        "before": before,
        "deleted": deleted,
        "after": remaining,
        "audioFilesRemoved": files_removed,
        "preservedImages": len(image_paths),
        "preservedStories": len(stories_before),
        "researchTablesUntouched": research_tables_untouched,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quizzes", action="store_true", help="clear the canonical/legacy production quiz bank and evidence")
    parser.add_argument("--audio", action="store_true", help="clear content/student audio references, records, ledger rows, and runtime files")
    parser.add_argument("--dependent-learning-state", action="store_true", help="reset production BKT/SRS/IRT/speaking/measurement state")
    parser.add_argument("--execute", action="store_true", help="commit the reset; without this flag only report candidates")
    args = parser.parse_args(argv)
    try:
        result = reset_learning_content(
            remove_quiz=args.quizzes,
            remove_audio=args.audio,
            remove_dependent_state=args.dependent_learning_state,
            execute=args.execute,
        )
    except Exception as exc:
        print(f"reset_learning_content failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
