"""Remove obsolete vocabulary IDs and their production history from a local DB.

Run from backend/: ``python -m scripts.purge_legacy_vocab`` previews the scope.
Use ``--execute --backup private-data/legacy-vocab-backup.json`` to delete.
The caller owns the transaction; the backup must succeed before any deletion.
Mixed old/current quiz attempts stop the operation.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from analytics.learner_model.bkt.mastery import _known_words, normalize_word_id
from repositories.database import DATABASE_URL


WORD_TABLES = (
    "student_vocab_srs_events",
    "student_vocab_srs",
    "student_vocab_mastery",
    "vocab_quiz_responses",
)


def _result_word_id(result: dict[str, Any]) -> str:
    value = result.get("conceptId") or result.get("concept_id") or result.get("word")
    return normalize_word_id(value) if isinstance(value, str) else ""


def purge(db: Any, *, execute: bool = False, backup: Path | None = None) -> dict[str, Any]:
    """Plan, back up, and remove only IDs absent from the published pool."""
    if execute:
        if backup is None:
            raise ValueError("An explicit backup path is required before deletion.")
        db.execute("SET LOCAL lock_timeout = '5s'")
        tables = sorted({
            "custom_stories", "vocab_quiz_attempts", "learning_measurement_events",
            *WORD_TABLES,
        })
        db.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(
            sql.SQL(", ").join(sql.Identifier(table) for table in tables)
        ))

    published = _known_words(db)
    if not published:
        raise ValueError("Published vocabulary is empty; cannot identify obsolete IDs safely.")
    stored_ids: set[str] = set()
    for table in WORD_TABLES:
        rows = db.execute(sql.SQL("SELECT DISTINCT word_id FROM {}").format(sql.Identifier(table))).fetchall()
        stored_ids.update(row["word_id"] for row in rows)
    obsolete = sorted(stored_ids - set(published))
    snapshots = {
        table: list(db.execute(sql.SQL("SELECT * FROM {} WHERE word_id = ANY(%s)").format(
            sql.Identifier(table)
        ), (obsolete,)).fetchall())
        for table in WORD_TABLES
    }
    obsolete_set = set(obsolete)
    attempts = []
    for attempt in db.execute("SELECT * FROM vocab_quiz_attempts").fetchall():
        results = attempt["question_results"] or []
        old = [item for item in results if _result_word_id(item) in obsolete_set]
        if not old:
            continue
        if len(old) != len(results):
            raise ValueError(f"Quiz {attempt['id']} mixes obsolete and current IDs; refusing deletion.")
        attempts.append(attempt)
    snapshots["vocab_quiz_attempts"] = attempts
    attempt_ids = [row["id"] for row in attempts]
    snapshots["learning_measurement_events"] = list(db.execute(
        "SELECT * FROM learning_measurement_events WHERE attempt_id = ANY(%s)",
        (attempt_ids,),
    ).fetchall())
    report = {
        "publishedWordCount": len(published),
        "obsoleteWordCount": len(obsolete),
        "obsoleteWordIds": obsolete,
        "rows": {table: len(rows) for table, rows in snapshots.items()},
        "executed": False,
    }
    if not execute or not obsolete:
        return report

    backup.parent.mkdir(parents=True, exist_ok=True)
    with backup.open("x", encoding="utf-8") as handle:
        json.dump({
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "report": report,
            "tables": snapshots,
        }, handle, ensure_ascii=False, default=str)
        handle.flush()
        os.fsync(handle.fileno())

    scopes = {
        **{table: ("word_id", obsolete) for table in WORD_TABLES},
        "learning_measurement_events": ("attempt_id", attempt_ids),
        "vocab_quiz_attempts": ("id", attempt_ids),
    }
    for table, (column, values) in scopes.items():
        deleted = db.execute(sql.SQL("DELETE FROM {} WHERE {} = ANY(%s)").format(
            sql.Identifier(table), sql.Identifier(column)
        ), (values,)).rowcount
        if deleted != len(snapshots[table]):
            raise RuntimeError(f"Deletion count changed for {table}; roll back this transaction.")
    if _known_words(db) != published:
        raise RuntimeError("Published vocabulary changed; roll back this transaction.")
    report["executed"] = True
    report["backup"] = str(backup.resolve())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if urlparse(args.database_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("This cleanup is restricted to a local database.")
    if args.execute and not args.backup:
        parser.error("--execute requires --backup.")
    with psycopg.connect(args.database_url, row_factory=dict_row) as db:
        if not args.execute:
            db.execute("SET TRANSACTION READ ONLY")
        report = purge(db, execute=args.execute, backup=args.backup)
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
