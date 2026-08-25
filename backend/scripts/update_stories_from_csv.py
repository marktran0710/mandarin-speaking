"""Replace the lesson 5-1 through 8-3 story frames from the locked CSV.

The generated fixture intentionally omits CSV-only metadata and seed defaults
the backend-required fields that are not part of the teaching material.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
# The tracked clean fixture has the same story/frame content as the incoming
# locked CSV, without the four metadata columns the application does not need.
# Pass --source to use the original CSV directly.
DEFAULT_CSV = SCRIPT_DIR.parents[1] / "stories_verified_v3_book_locked_clean.csv"
DEFAULT_FIXTURE = SCRIPT_DIR / "data" / "custom_stories.json"
TARGET_LESSONS = {(lesson, sub_order) for lesson in range(5, 9) for sub_order in range(1, 4)}
OMITTED_EXPORT_COLUMNS = {
    "learning_goal",
    "narrative_mode",
    "linear",
    "first_frame_is_example",
}
OMITTED_FIXTURE_FIELDS = OMITTED_EXPORT_COLUMNS
REQUIRED_COLUMNS = {
    "lesson_number",
    "lesson_sub_order",
    "story_id",
    "story_title",
    "published",
    "frame_index",
    "frame_json",
}


def _bool(value: str, *, field: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{field} must be True or False, got {value!r}")


def _read_csv(source: Path) -> tuple[list[str], list[dict[str, str]]]:
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        fieldnames = list(reader.fieldnames)
        missing_columns = REQUIRED_COLUMNS - set(fieldnames)
        if missing_columns:
            raise ValueError(f"CSV is missing required columns: {sorted(missing_columns)}")
        rows = list(reader)
    return fieldnames, rows


def _target_rows(source: Path) -> dict[str, list[dict[str, str]]]:
    _, rows = _read_csv(source)

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    story_lessons: dict[str, tuple[int, int]] = {}
    for row_number, row in enumerate(rows, start=2):
        try:
            lesson = (int(row["lesson_number"]), int(row["lesson_sub_order"]))
        except ValueError as error:
            raise ValueError(f"CSV row {row_number} has an invalid lesson number/order") from error
        if lesson not in TARGET_LESSONS:
            continue
        story_id = row["story_id"].strip()
        if not story_id:
            raise ValueError(f"CSV row {row_number} has a blank story_id")
        previous_lesson = story_lessons.setdefault(story_id, lesson)
        if previous_lesson != lesson:
            raise ValueError(f"story {story_id!r} appears in multiple target lessons")
        grouped[story_id].append(row)

    found_lessons = set(story_lessons.values())
    missing_lessons = TARGET_LESSONS - found_lessons
    duplicate_lessons = {lesson for lesson in found_lessons if list(story_lessons.values()).count(lesson) > 1}
    if missing_lessons or duplicate_lessons:
        raise ValueError(
            f"target lessons missing={sorted(missing_lessons)}, duplicated={sorted(duplicate_lessons)}"
        )
    if len(grouped) != len(TARGET_LESSONS):
        raise ValueError(f"expected {len(TARGET_LESSONS)} target stories, found {len(grouped)}")
    return grouped


def _story_from_rows(story_id: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    first = rows[0]
    lesson = (int(first["lesson_number"]), int(first["lesson_sub_order"]))
    for row in rows:
        if (int(row["lesson_number"]), int(row["lesson_sub_order"])) != lesson:
            raise ValueError(f"story {story_id!r} has inconsistent lesson metadata")
        if row["story_title"] != first["story_title"] or row["published"] != first["published"]:
            raise ValueError(f"story {story_id!r} has inconsistent story metadata")

    indexed_frames: dict[int, dict[str, Any]] = {}
    for row in rows:
        try:
            frame_index = int(row["frame_index"])
        except ValueError as error:
            raise ValueError(f"story {story_id!r} has an invalid frame_index") from error
        if frame_index in indexed_frames:
            raise ValueError(f"story {story_id!r} has duplicate frame_index {frame_index}")
        try:
            frame = json.loads(row["frame_json"])
        except json.JSONDecodeError as error:
            raise ValueError(f"story {story_id!r}, frame {frame_index} has invalid frame_json") from error
        if not isinstance(frame, dict):
            raise ValueError(f"story {story_id!r}, frame {frame_index} frame_json must be an object")
        indexed_frames[frame_index] = frame

    expected_indexes = list(range(len(indexed_frames)))
    if sorted(indexed_frames) != expected_indexes:
        raise ValueError(
            f"story {story_id!r} frame indexes must be consecutive from 0; got {sorted(indexed_frames)}"
        )
    return {
        "id": story_id,
        "title": first["story_title"],
        "frames": [indexed_frames[index] for index in expected_indexes],
        "published": _bool(first["published"], field=f"story {story_id!r} published"),
        "lesson_number": lesson[0],
        "lesson_sub_order": lesson[1],
    }


def update_fixture(source: Path, fixture: Path) -> None:
    grouped = _target_rows(source)
    replacements = {story_id: _story_from_rows(story_id, rows) for story_id, rows in grouped.items()}
    materials = json.loads(fixture.read_text(encoding="utf-8"))
    if not isinstance(materials, list):
        raise ValueError("fixture must be a JSON list")

    fixture_ids = [material.get("id") for material in materials if isinstance(material, dict)]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("fixture contains duplicate story IDs")
    fixture_target_ids = {
        material["id"]
        for material in materials
        if isinstance(material, dict)
        and (material.get("lesson_number"), material.get("lesson_sub_order")) in TARGET_LESSONS
    }
    if fixture_target_ids != set(replacements):
        raise ValueError(
            "fixture and CSV target IDs differ: "
            f"fixture_only={sorted(fixture_target_ids - set(replacements))}, "
            f"csv_only={sorted(set(replacements) - fixture_target_ids)}"
        )

    # Only teaching content comes from the locked CSV. Preserve existing
    # backend metadata while intentionally dropping CSV-only compatibility
    # fields; seed_materials supplies their stable defaults when needed.
    updated = [
        {
            **{key: value for key, value in material.items() if key not in OMITTED_FIXTURE_FIELDS},
            **replacements[material["id"]],
        }
        if material["id"] in replacements
        else material
        for material in materials
    ]
    fixture.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_export(source: Path, export: Path) -> None:
    """Write the target CSV with source rows intact except CSV-only metadata."""
    _target_rows(source)  # Run the same duplicate, missing-frame, and JSON checks.
    fieldnames, rows = _read_csv(source)
    output_fields = [field for field in fieldnames if field not in OMITTED_EXPORT_COLUMNS]
    target_rows = [
        row
        for row in rows
        if (int(row["lesson_number"]), int(row["lesson_sub_order"])) in TARGET_LESSONS
    ]
    with export.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows({field: row[field] for field in output_fields} for row in target_rows)


def update_database(source: Path) -> None:
    """Update only the twelve lesson stories in the configured application DB.

    The four omitted metadata fields are intentionally not written here. This
    keeps the system's existing values intact while replacing the story
    content that came from the locked CSV.
    """
    from psycopg.types.json import Jsonb

    from database import connect_db

    grouped = _target_rows(source)
    stories = [
        _story_from_rows(story_id, rows)
        for story_id, rows in sorted(grouped.items(), key=lambda item: item[0])
    ]

    with connect_db() as db:
        for story in stories:
            existing = db.execute(
                "SELECT id FROM custom_stories WHERE id = %s FOR UPDATE",
                (story["id"],),
            ).fetchone()
            if existing is None:
                raise ValueError(f"database story not found: {story['id']}")

        for story in stories:
            result = db.execute(
                """
                UPDATE custom_stories
                SET title = %s,
                    frames = %s,
                    published = %s,
                    lesson_number = %s,
                    lesson_sub_order = %s
                WHERE id = %s
                """,
                (
                    story["title"],
                    Jsonb(story["frames"]),
                    story["published"],
                    story["lesson_number"],
                    story["lesson_sub_order"],
                    story["id"],
                ),
            )
            if result.rowcount != 1:
                raise ValueError(f"database update affected {result.rowcount} rows for {story['id']}")

        for story in stories:
            saved = db.execute(
                "SELECT title, published, lesson_number, lesson_sub_order, frames "
                "FROM custom_stories WHERE id = %s",
                (story["id"],),
            ).fetchone()
            if saved is None or saved["title"] != story["title"]:
                raise ValueError(f"database verification failed for {story['id']}")
            if saved["published"] != story["published"]:
                raise ValueError(f"published verification failed for {story['id']}")
            if saved["lesson_number"] != story["lesson_number"] or saved["lesson_sub_order"] != story["lesson_sub_order"]:
                raise ValueError(f"lesson metadata verification failed for {story['id']}")
            if saved["frames"] != story["frames"]:
                raise ValueError(f"frame content verification failed for {story['id']}")

    print(f"Updated {len(stories)} stories in the configured application database")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--export",
        type=Path,
        help="Optional cleaned CSV export path; omitted by default.",
    )
    parser.add_argument(
        "--update-db",
        action="store_true",
        help="Also update the configured application database for these 12 stories.",
    )
    args = parser.parse_args()
    update_fixture(args.source, args.fixture)
    if args.export:
        update_export(args.source, args.export)
    if args.update_db:
        update_database(args.source)
    print(f"Updated {len(TARGET_LESSONS)} stories in {args.fixture}")


if __name__ == "__main__":
    main()
