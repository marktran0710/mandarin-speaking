"""Reset one student's lesson so its quiz and practice must be completed again.

Dry run: python -m scripts.reset_student_lesson --student-id ID --story-id ID
Apply: add --execute --backup private-data/student-lesson-before-reset.json
Authored content, accounts, other lessons, and recording files are preserved.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from analytics.learner_model.bkt.mastery import _known_words
from domain.vocabulary.story_scope import canonical_story_id, story_scope_ids
from repositories.database import DATABASE_URL
from services.vocab_quiz_progression_service import get_progression


def reset_lesson(
    db: Any, student_id: str, story_id: str, *, execute: bool = False, backup: Path | None = None,
) -> dict[str, Any]:
    if execute and backup is None:
        raise ValueError("An explicit backup path is required.")
    if execute:
        db.execute("SET LOCAL lock_timeout = '5s'")
        db.execute("""LOCK TABLE students, custom_stories, vocab_quiz_attempts,
            vocab_quiz_responses, student_vocab_mastery, student_vocab_srs,
            student_vocab_srs_events, speaking_progress, story_submissions
            IN SHARE ROW EXCLUSIVE MODE""")
    student = db.execute("SELECT id FROM students WHERE id = %s", (student_id,)).fetchone()
    if not student:
        raise ValueError("Student was not found.")
    canonical = canonical_story_id(story_id) or story_id
    known = _known_words(db, story_id=canonical)
    if not known:
        raise ValueError("Published lesson vocabulary was not found.")
    scope = story_scope_ids(canonical)
    responses = list(db.execute(
        "SELECT * FROM vocab_quiz_responses WHERE student_id = %s AND lesson_id = ANY(%s)",
        (student_id, scope),
    ).fetchall())
    word_ids = sorted(set(known) | {row["word_id"] for row in responses})
    shared = db.execute(
        """SELECT 1 FROM vocab_quiz_responses WHERE student_id = %s AND word_id = ANY(%s)
           AND (lesson_id IS NULL OR lesson_id <> ALL(%s)) LIMIT 1""",
        (student_id, word_ids, scope),
    ).fetchone()
    if shared:
        raise ValueError("Vocabulary evidence is shared with another lesson; refusing reset.")
    scopes = {
        "student_vocab_srs_events": ("word_id", word_ids),
        "student_vocab_srs": ("word_id", word_ids),
        "student_vocab_mastery": ("word_id", word_ids),
        "vocab_quiz_responses": ("lesson_id", scope),
        "vocab_quiz_attempts": ("story_id", scope),
        "speaking_progress": ("topic_id", scope),
        "story_submissions": ("story_id", scope),
    }
    snapshots = {
        table: list(db.execute(sql.SQL("SELECT * FROM {} WHERE student_id = %s AND {} = ANY(%s)").format(
            sql.Identifier(table), sql.Identifier(column),
        ), (student_id, values)).fetchall())
        for table, (column, values) in scopes.items()
    }
    report = {
        "studentId": student_id, "storyId": canonical, "wordCount": len(known),
        "rows": {table: len(rows) for table, rows in snapshots.items()}, "executed": False,
    }
    if not execute:
        return report
    backup.parent.mkdir(parents=True, exist_ok=True)
    with backup.open("x", encoding="utf-8") as handle:
        json.dump({"report": report, "tables": snapshots}, handle, ensure_ascii=False, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    for table, (column, values) in scopes.items():
        removed = db.execute(sql.SQL("DELETE FROM {} WHERE student_id = %s AND {} = ANY(%s)").format(
            sql.Identifier(table), sql.Identifier(column),
        ), (student_id, values)).rowcount
        if removed != len(snapshots[table]):
            raise RuntimeError(f"Deletion scope changed for {table}; roll back the transaction.")
    progression = get_progression(db, student_id, canonical)
    if progression["quizStars"] != 0 or progression["speakingUnlocked"] or progression["conversationUnlocked"]:
        raise RuntimeError("Lesson did not relock; roll back the transaction.")
    report.update(executed=True, backup=str(backup.resolve()), progression=progression)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--student-id", required=True)
    parser.add_argument("--story-id", required=True)
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if urlparse(args.database_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("This reset is restricted to a local database.")
    if args.execute and not args.backup:
        parser.error("--execute requires --backup.")
    with psycopg.connect(args.database_url, row_factory=dict_row) as db:
        if not args.execute:
            db.execute("SET TRANSACTION READ ONLY")
        report = reset_lesson(db, args.student_id, args.story_id, execute=args.execute, backup=args.backup)
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
