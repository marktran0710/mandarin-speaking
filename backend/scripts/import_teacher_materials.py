"""
Import teacher materials from a zip file produced by export_teacher_materials.py.

Usage:
    python import_teacher_materials.py teacher_materials_20260617_120000.zip
    python import_teacher_materials.py teacher_materials.zip --overwrite
"""

import argparse
import json
import os
import sqlite3
import zipfile

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "mandarin_stories.db"),
)
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "uploads"))


def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_stories (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            learning_goal TEXT NOT NULL,
            level TEXT NOT NULL,
            frames TEXT NOT NULL,
            published INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Add published column if missing (older DBs).
    columns = {row[1] for row in conn.execute("PRAGMA table_info(custom_stories)").fetchall()}
    if "published" not in columns:
        conn.execute("ALTER TABLE custom_stories ADD COLUMN published INTEGER NOT NULL DEFAULT 0")
    conn.commit()


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

    conn = sqlite3.connect(DATABASE_PATH)
    init_db(conn)

    inserted = skipped = 0
    for story in stories:
        existing = conn.execute(
            "SELECT id FROM custom_stories WHERE id = ?", (story["id"],)
        ).fetchone()

        if existing and not args.overwrite:
            skipped += 1
            continue

        conn.execute(
            """
            INSERT OR REPLACE INTO custom_stories
                (id, title, learning_goal, level, frames, published, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                story["id"],
                story["title"],
                story["learning_goal"],
                story["level"],
                story["frames"],
                story.get("published", 0),
                story.get("created_at", ""),
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()

    print(f"Imported {inserted} stories, skipped {skipped} duplicates.")
    if skipped:
        print("  (use --overwrite to replace duplicates)")


if __name__ == "__main__":
    main()
