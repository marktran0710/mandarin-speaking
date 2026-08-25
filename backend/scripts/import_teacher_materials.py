"""
Import teacher materials from a zip file produced by export_teacher_materials.py.

Usage:
    python import_teacher_materials.py teacher_materials_20260617_120000.zip
    python import_teacher_materials.py teacher_materials.zip --overwrite
"""

import argparse
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg.types.json import Jsonb  # noqa: E402

from database import connect_db  # noqa: E402

UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "uploads"))


def _story_columns() -> set:
    with connect_db() as db:
        rows = db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'custom_stories'"
        ).fetchall()
    return {row["column_name"] for row in rows}


def main():
    parser = argparse.ArgumentParser(description="Import teacher materials from a zip file.")
    parser.add_argument("zipfile", help="Path to the zip file produced by export_teacher_materials.py")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing stories with the same ID (default: skip duplicates)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.zipfile):
        print(f"ERROR: file not found: {args.zipfile}")
        raise SystemExit(1)

    with zipfile.ZipFile(args.zipfile, "r") as zf:
        if "stories.json" not in zf.namelist():
            print("ERROR: zip does not contain stories.json — is this a valid export?")
            raise SystemExit(1)

        stories = json.loads(zf.read("stories.json"))

        # Extract images first.
        image_entries = [n for n in zf.namelist() if n.startswith("uploads/")]
        for entry in image_entries:
            dest = os.path.join(UPLOAD_DIR, entry.removeprefix("uploads/").replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(entry) as src, open(dest, "wb") as dst:
                dst.write(src.read())
        print(f"Extracted {len(image_entries)} images to {UPLOAD_DIR}")

    columns = _story_columns()
    required = {
        "id", "title", "frames", "published", "lesson_number", "lesson_sub_order",
    }
    missing = required - columns
    if missing:
        print(f"ERROR: custom_stories table is missing columns: {sorted(missing)}")
        raise SystemExit(1)

    inserted = skipped = 0
    with connect_db() as db:
        for story in stories:
            existing = db.execute(
                "SELECT id FROM custom_stories WHERE id = %s", (story["id"],)
            ).fetchone()

            if existing and not args.overwrite:
                skipped += 1
                continue

            # Exports from before this cut-over stored frames double-encoded
            # (the SQLite TEXT column already held a JSON string); a fresh
            # export re-stringifies frames for the same on-disk format, so
            # this always arrives as a string here — parse it back before
            # handing it to Jsonb().
            frames = story["frames"]
            if isinstance(frames, str):
                frames = json.loads(frames)

            db.execute(
                """
                INSERT INTO custom_stories
                    (id, title, frames, published, lesson_number, lesson_sub_order)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    frames = EXCLUDED.frames,
                    published = EXCLUDED.published,
                    lesson_number = EXCLUDED.lesson_number,
                    lesson_sub_order = EXCLUDED.lesson_sub_order
                """,
                (
                    story["id"],
                    story["title"],
                    Jsonb(frames),
                    bool(story.get("published", False)),
                    story.get("lesson_number"),
                    story.get("lesson_sub_order"),
                ),
            )
            inserted += 1

    print(f"Imported {inserted} stories, skipped {skipped} duplicates.")
    if skipped:
        print("  (use --overwrite to replace duplicates)")


if __name__ == "__main__":
    main()
