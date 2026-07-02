"""
Export all teacher materials (custom stories + their images) to a zip file.

Usage:
    python export_teacher_materials.py
    python export_teacher_materials.py --output my_backup.zip
"""

import argparse
import json
import os
import sqlite3
import zipfile
from datetime import datetime

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "mandarin_stories.db"),
)
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "uploads"))


def main():
    parser = argparse.ArgumentParser(description="Export teacher materials to a zip file.")
    parser.add_argument(
        "--output",
        default=f"teacher_materials_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
        help="Output zip file path (default: teacher_materials_<timestamp>.zip)",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM custom_stories ORDER BY created_at").fetchall()
    conn.close()

    stories = [dict(row) for row in rows]
    print(f"Found {len(stories)} custom stories.")

    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("stories.json", json.dumps(stories, ensure_ascii=False, indent=2))

        image_count = 0
        for story in stories:
            frames = json.loads(story.get("frames") or "[]")
            for frame in frames:
                image_url = frame.get("imageUrl", "")
                if not image_url.startswith("/uploads/"):
                    continue
                relative = image_url.removeprefix("/uploads/").replace("/", os.sep)
                abs_path = os.path.join(UPLOAD_DIR, relative)
                if os.path.isfile(abs_path):
                    # Store inside zip as uploads/<relative> so the importer
                    # can reconstruct the same path on the new device.
                    zf.write(abs_path, arcname=os.path.join("uploads", relative))
                    image_count += 1
                else:
                    print(f"  WARNING: image not found on disk: {abs_path}")

    print(f"Exported {image_count} images.")
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
