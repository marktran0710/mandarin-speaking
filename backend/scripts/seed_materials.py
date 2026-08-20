"""Seed the versioned teaching materials recovered from the local database.

Materials are application data, not schema migrations. This script keeps them
reproducible on a fresh device while preserving an existing row by default.
Use ``--overwrite`` only when intentionally replacing a material with the
version committed in the fixture.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from psycopg.types.json import Jsonb

from database import connect_db


FIXTURE = Path(__file__).resolve().parent / "data" / "custom_stories.json"
JSON_COLUMNS = {
    "frames",
    "quiz_exclusions",
    "quiz_material_snapshot",
    "quiz_approved_snapshot",
    "quiz_pending_approvals",
    "rubric_scores",
}
COLUMNS = (
    "id",
    "title",
    "learning_goal",
    "frames",
    "published",
    "created_at",
    "linear",
    "lesson_number",
    "narrative_mode",
    "first_frame_is_example",
    "quiz_exclusions",
    "quiz_material_snapshot",
    "quiz_approved_snapshot",
    "quiz_pending_approvals",
    "lesson_sub_order",
    "rubric_scores",
)


def _values(material: dict) -> tuple[object, ...]:
    return tuple(
        Jsonb(material[column]) if column in JSON_COLUMNS and material[column] is not None else material[column]
        for column in COLUMNS
    )


def main() -> None:
    if os.getenv("APP_ENV", "development").lower() == "production":
        raise SystemExit("Development materials seed is disabled in production.")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing materials with the committed fixture.",
    )
    args = parser.parse_args()
    materials = json.loads(FIXTURE.read_text(encoding="utf-8"))
    columns_sql = ", ".join(COLUMNS)
    placeholders = ", ".join(["%s"] * len(COLUMNS))
    updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in COLUMNS if column != "id")
    inserted = 0
    skipped = 0

    with connect_db() as db:
        for material in materials:
            existing = db.execute(
                "SELECT 1 FROM custom_stories WHERE id = %s", (material["id"],)
            ).fetchone()
            if existing and not args.overwrite:
                skipped += 1
                continue
            conflict = f"ON CONFLICT (id) DO UPDATE SET {updates}" if args.overwrite else "ON CONFLICT (id) DO NOTHING"
            db.execute(
                f"INSERT INTO custom_stories ({columns_sql}) VALUES ({placeholders}) {conflict}",
                _values(material),
            )
            inserted += 1

    print(f"Materials seed complete: inserted_or_updated={inserted}, skipped={skipped}")


if __name__ == "__main__":
    main()
