"""Import the locked, verified quiz-question export into approved material.

The CSV is a review artifact, not a live student data source.  This script
validates it first, then can either refresh the checked-in seed fixture or
explicitly publish the same approved snapshots to ``custom_stories``.

Examples::

    # Validate only (the safe default)
    python -m scripts.import_verified_quiz_questions

    # Publish the verified snapshot into the reproducible fixture, after review
    python -m scripts.import_verified_quiz_questions --publish-fixture

    # Publish to the configured database (explicit on purpose)
    python -m scripts.import_verified_quiz_questions --publish-db
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE = SCRIPT_DIR.parents[1] / "questions_verified_v3_book_locked.csv"
DEFAULT_FIXTURE = SCRIPT_DIR / "data" / "custom_stories.json"

TIERS = ("easy", "medium", "hard")
QUESTION_TYPES = {"translation", "reverse", "listening", "pinyin", "pos", "cloze", "synonym"}
DISTRACTOR_QUESTION_TYPES = {"translation", "cloze", "synonym"}
SOURCE_OPTION_QUESTION_TYPES = QUESTION_TYPES - DISTRACTOR_QUESTION_TYPES
REQUIRED_COLUMNS = {
    "story_id",
    "story_title",
    "published",
    "lesson_number",
    "tier",
    "frame_index",
    "word_index",
    "word",
    "question_type",
    "prompt",
    "correct_answer",
    "translation",
    "pinyin",
    "part_of_speech",
    "options_from_source",
    "context_sentence",
    "source",
    "validation_status",
    "validation_errors",
    "lesson_sub_order",
}
MAX_PUBLISHED_WRONG_OPTIONS = 3
EXPECTED_SOURCE = "verified_v3_book_locked"


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _options(row: dict[str, str], row_number: int) -> list[str]:
    try:
        parsed = json.loads(row.get("options_from_source", ""))
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"row {row_number}: options_from_source is not valid JSON") from error
    if not isinstance(parsed, list) or not all(isinstance(value, str) for value in parsed):
        raise ValueError(f"row {row_number}: options_from_source must be a JSON string array")
    values = [value.strip() for value in parsed if value.strip()]
    if len({_normalized(value) for value in values}) != len(values):
        raise ValueError(f"row {row_number}: options_from_source contains duplicate values")
    answer = row.get("correct_answer", "").strip()
    if row.get("question_type") in DISTRACTOR_QUESTION_TYPES and _normalized(answer) in {
        _normalized(value) for value in values
    }:
        raise ValueError(f"row {row_number}: correct answer appears in its distractor list")
    if row.get("question_type") in SOURCE_OPTION_QUESTION_TYPES and row.get("question_type") != "pos":
        if _normalized(answer) not in {_normalized(value) for value in values}:
            raise ValueError(f"row {row_number}: correct answer is missing from source options")
    return values


def read_verified_questions(source: Path) -> list[dict[str, str]]:
    """Read and strictly validate the locked export before it can be imported."""
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

        rows: list[dict[str, str]] = []
        identities: set[tuple[str, str, int, int, str]] = set()
        story_metadata: dict[str, tuple[str, str, str, str, str]] = {}
        for row_number, raw_row in enumerate(reader, start=2):
            row = {key: (value or "").strip() for key, value in raw_row.items() if key is not None}
            if row.get("validation_status") != "ok":
                raise ValueError(
                    f"row {row_number}: validation_status must be ok, got {row.get('validation_status')!r}"
                )
            if row.get("validation_errors"):
                raise ValueError(f"row {row_number}: validation_errors is not empty")
            if row.get("source") != EXPECTED_SOURCE:
                raise ValueError(
                    f"row {row_number}: source must be {EXPECTED_SOURCE!r}, got {row.get('source')!r}"
                )
            if not row.get("story_id") or not row.get("word") or not row.get("correct_answer"):
                raise ValueError(f"row {row_number}: story_id, word, and correct_answer are required")
            tier = row.get("tier")
            question_type = row.get("question_type")
            if tier not in TIERS:
                raise ValueError(f"row {row_number}: unsupported tier {tier!r}")
            if question_type not in QUESTION_TYPES:
                raise ValueError(f"row {row_number}: unsupported question_type {question_type!r}")
            try:
                frame_index = int(row.get("frame_index", ""))
                word_index = int(row.get("word_index", ""))
            except ValueError as error:
                raise ValueError(f"row {row_number}: frame_index and word_index must be integers") from error
            if frame_index < 0 or word_index < 0:
                raise ValueError(f"row {row_number}: frame_index and word_index must be non-negative")
            _options(row, row_number)

            metadata = (
                row.get("story_title", ""),
                row.get("published", ""),
                row.get("lesson_number", ""),
                row.get("lesson_sub_order", ""),
                row.get("source", ""),
            )
            previous_metadata = story_metadata.setdefault(row["story_id"], metadata)
            if previous_metadata != metadata:
                raise ValueError(f"row {row_number}: inconsistent metadata for story {row['story_id']!r}")

            identity = (row["story_id"], tier, frame_index, word_index, question_type)
            if identity in identities:
                raise ValueError(f"row {row_number}: duplicate question identity {identity!r}")
            identities.add(identity)
            rows.append(row)

    if not rows:
        raise ValueError("CSV contains no question rows")
    return rows


def _candidate(row: dict[str, str], options: Iterable[str]) -> dict[str, Any]:
    # The locked export stores the visible blank in context_sentence.  The
    # frontend's approved-material shape intentionally stores the source
    # sentence with the word present and replaces it at render time.
    sentence = row["context_sentence"].replace("____", row["word"], 1).strip()
    if sentence.count(row["word"]) != 1:
        raise ValueError(
            f"{row['story_id']}/{row['tier']}: cloze sentence must contain "
            f"{row['word']!r} exactly once"
        )
    return {
        "sentence": sentence,
        "distractors": list(options)[:MAX_PUBLISHED_WRONG_OPTIONS],
    }


def build_approved_snapshots(rows: list[dict[str, str]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Build the snapshot shape consumed by ``storyToTopic`` in approved mode.

    The CSV contains seven question types.  The current runtime stores the
    teacher-approved pools for translation, cloze, and synonym explicitly;
    reverse/listening/pinyin/POS options continue to be generated from the
    same canonical vocabulary/pinyin/POS fields at runtime.  We still validate
    every row above so the source remains a complete, auditable question bank.
    """
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["story_id"], row["tier"])].append(row)

    snapshots: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(dict)
    for (story_id, tier), group in grouped.items():
        by_word: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
        first_location: dict[str, tuple[int, int]] = {}
        for row in group:
            word = row["word"]
            location = (int(row["frame_index"]), int(row["word_index"]))
            first_location.setdefault(word, location)
            by_word[word][row["question_type"]].append(row)

        entries: list[dict[str, Any]] = []
        for word in sorted(by_word, key=lambda value: first_location[value]):
            material = by_word[word]
            translations = material.get("translation", [])
            if not translations:
                raise ValueError(f"{story_id}/{tier}: missing translation row for {word!r}")
            translation_values = {
                row.get("translation", "").strip() or row["correct_answer"].strip()
                for row in translations
            }
            if len(translation_values) != 1 or not next(iter(translation_values)):
                raise ValueError(f"{story_id}/{tier}: inconsistent translation rows for {word!r}")

            entry: dict[str, Any] = {
                "word": word,
                "translation": next(iter(translation_values)),
                "distractors": _options(translations[0], 0)[:MAX_PUBLISHED_WRONG_OPTIONS],
                "cloze": [],
                "synonym": [],
            }
            cloze_rows = material.get("cloze", [])
            if cloze_rows:
                entry["cloze"] = [_candidate(cloze_rows[0], _options(cloze_rows[0], 0))]
            synonym_rows = material.get("synonym", [])
            if synonym_rows:
                synonym = synonym_rows[0]["correct_answer"].strip()
                entry["synonym"] = [
                    {
                        "synonym": synonym,
                        "distractors": _options(synonym_rows[0], 0)[:MAX_PUBLISHED_WRONG_OPTIONS],
                    }
                ]
            entries.append(entry)
        snapshots[story_id][tier] = entries

    return {story_id: dict(levels) for story_id, levels in snapshots.items()}


def publish_fixture(source: Path, fixture: Path) -> tuple[int, int]:
    rows = read_verified_questions(source)
    snapshots = build_approved_snapshots(rows)
    materials = json.loads(fixture.read_text(encoding="utf-8"))
    if not isinstance(materials, list):
        raise ValueError("fixture must contain a JSON list")
    by_id = {material.get("id"): material for material in materials if isinstance(material, dict)}
    missing = sorted(set(snapshots) - set(by_id))
    if missing:
        raise ValueError(f"fixture is missing CSV stories: {missing}")
    for story_id, story_snapshot in snapshots.items():
        current = by_id[story_id].get("quiz_approved_snapshot")
        if not isinstance(current, dict):
            current = {}
        current.update(story_snapshot)
        by_id[story_id]["quiz_approved_snapshot"] = current
    fixture.write_text(json.dumps(materials, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(rows), len(snapshots)


def publish_to_database(source: Path) -> tuple[int, int]:
    rows = read_verified_questions(source)
    snapshots = build_approved_snapshots(rows)
    # Keep database imports explicit: unlike fixture generation, this changes
    # the currently published student material.
    from psycopg.types.json import Jsonb

    from database import connect_db

    with connect_db() as db:
        found = {
            row["id"]
            for row in db.execute(
                "SELECT id FROM custom_stories WHERE id = ANY(%s)",
                (list(snapshots),),
            ).fetchall()
        }
        missing = sorted(set(snapshots) - found)
        if missing:
            raise ValueError(f"database is missing CSV stories: {missing}")
        for story_id, snapshot in snapshots.items():
            db.execute(
                "UPDATE custom_stories SET quiz_approved_snapshot = %s WHERE id = %s",
                (Jsonb(snapshot), story_id),
            )
    return len(rows), len(snapshots)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--publish-fixture",
        action="store_true",
        help="Publish the verified snapshot into the seed fixture after teacher review.",
    )
    parser.add_argument(
        "--publish-db",
        action="store_true",
        help="Publish the verified snapshot to custom_stories after teacher review.",
    )
    args = parser.parse_args()

    rows = read_verified_questions(args.source)
    snapshots = build_approved_snapshots(rows)
    print(f"Verified {len(rows)} rows for {len(snapshots)} stories.")
    print("Approved entries by tier:", ", ".join(
        f"{story_id}={len(levels.get('easy', []))}/{len(levels.get('medium', []))}/{len(levels.get('hard', []))}"
        for story_id, levels in sorted(snapshots.items())
    ))
    if args.publish_fixture:
        publish_fixture(args.source, args.fixture)
        print(f"Updated fixture: {args.fixture}")
    if args.publish_db:
        publish_to_database(args.source)
        print("Published verified snapshots to custom_stories.")


if __name__ == "__main__":
    main()
