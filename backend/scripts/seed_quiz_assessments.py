"""Publish the canonical Lesson 5 textbook quiz banks to existing stories.

Validation is always performed first. Database writes require ``--publish``
and only update ``custom_stories.vocab_assessment``; Materials fields remain
outside this seed path. A lesson part must already exist in the database, so
this command never recreates stories that were intentionally removed.

Examples::

    python backend/scripts/seed_quiz_assessments.py
    python backend/scripts/seed_quiz_assessments.py --lesson-part 5-2 --publish
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg.types.json import Jsonb  # noqa: E402

from database import connect_db  # noqa: E402
from scripts.import_vocab_assessment import assessment_payload  # noqa: E402


BANK_DIRECTORY = Path(__file__).resolve().parent / "data" / "quiz_assessments"
BANKS: dict[str, Path] = {
    "5-2": BANK_DIRECTORY / "l5-2-vocab-assessment.csv",
    "5-3": BANK_DIRECTORY / "l5-3-vocab-assessment.csv",
}


def find_story_for_part(db: Any, lesson_part: str) -> dict[str, Any]:
    """Return the one existing story assigned to a lesson part.

    Matching by lesson metadata avoids hard-coding IDs from a deleted seed and
    makes the operation safe when a teacher imports a replacement story.
    """
    lesson_number, lesson_sub_order = (int(value) for value in lesson_part.split("-", 1))
    rows = db.execute(
        """
        SELECT id, title
        FROM custom_stories
        WHERE lesson_number = %s AND lesson_sub_order = %s
        ORDER BY created_at NULLS LAST, id
        """,
        (lesson_number, lesson_sub_order),
    ).fetchall()
    if not rows:
        raise LookupError(f"No existing story is assigned to lesson part {lesson_part}.")
    if len(rows) > 1:
        ids = ", ".join(str(row["id"]) for row in rows)
        raise LookupError(f"Lesson part {lesson_part} has multiple stories: {ids}.")
    return dict(rows[0])


def _parts(requested: str | None) -> list[str]:
    if requested is not None:
        if requested not in BANKS:
            raise ValueError(f"Unsupported lesson part: {requested}")
        return [requested]
    return list(BANKS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lesson-part", choices=tuple(BANKS), help="Only process one part, for example 5-2.")
    parser.add_argument("--publish", action="store_true", help="Attach validated banks to matching existing stories.")
    args = parser.parse_args()

    parts = _parts(args.lesson_part)
    payloads: dict[str, list[dict]] = {}
    for lesson_part in parts:
        payload = assessment_payload(BANKS[lesson_part])
        payloads[lesson_part] = payload
        print(
            f"Lesson {lesson_part}: "
            f"{len({row['wordId'] for row in payload})} vocabulary items, "
            f"{len(payload)} questions [OK]"
        )

    if not args.publish:
        print("Validation only; no database changes made.")
        return 0

    # Resolve every target before writing any row, so a missing/ambiguous part
    # cannot leave a partially published set of banks.
    with connect_db() as db:
        targets = {lesson_part: find_story_for_part(db, lesson_part) for lesson_part in parts}
        for lesson_part in parts:
            target = targets[lesson_part]
            db.execute(
                "UPDATE custom_stories SET vocab_assessment = %s WHERE id = %s",
                (Jsonb(payloads[lesson_part]), target["id"]),
            )
            print(f"Published Lesson {lesson_part} bank to {target['id']} ({target['title']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
