"""Seed the versioned teaching materials recovered from the local database.

Materials are application data, not schema migrations. This script keeps them
reproducible on a fresh device while preserving an existing row by default.
Use ``--overwrite`` only when intentionally replacing a material with the
version committed in the fixture.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
from pathlib import Path

from psycopg.types.json import Jsonb

from database import connect_db


FIXTURE = Path(__file__).resolve().parent / "data" / "custom_stories.json"
ASSET_ROOT = Path(__file__).resolve().parent / "data" / "assets"
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
    "frames",
    "published",
    "created_at",
    "lesson_number",
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


def _restore_assets() -> tuple[int, int]:
    """Restore versioned material images into the runtime upload directory."""
    upload_root = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).resolve().parents[1] / "uploads")))
    restored = 0
    skipped = 0
    if not ASSET_ROOT.exists():
        return restored, skipped

    for source in ASSET_ROOT.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(ASSET_ROOT)
        target = upload_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and filecmp.cmp(source, target, shallow=False):
            skipped += 1
            continue
        shutil.copy2(source, target)
        restored += 1
    return restored, skipped


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
    restored_assets, skipped_assets = _restore_assets()
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

    print(
        "Materials seed complete: "
        f"inserted_or_updated={inserted}, skipped={skipped}; "
        f"assets_restored={restored_assets}, assets_already_present={skipped_assets}"
    )


if __name__ == "__main__":
    main()
