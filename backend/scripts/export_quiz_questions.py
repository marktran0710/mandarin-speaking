"""Export the quiz question material stored in custom stories to CSV.

The story editor stores quiz material inside each frame as a mixture of
comma-separated text and JSON-encoded arrays.  This script normalizes that
material into one row per question so the result can be opened in Excel or
uploaded to Google Sheets.

Usage:
    python -m scripts.export_quiz_questions
    python -m scripts.export_quiz_questions --output ..\\output\\quiz_questions.csv

The default output is ``quiz_questions_<timestamp>.csv`` in the current
directory.  The file is UTF-8 with a BOM, which makes Traditional Chinese
display correctly in Excel on Windows.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import connect_db  # noqa: E402


TIERS = ("easy", "medium", "hard")

CSV_FIELDS = (
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
)


def _json_value(value: Any, fallback: Any) -> Any:
    """Decode a JSON-encoded frame field without making export fail."""
    if value is None or value == "":
        return fallback
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str):
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _csv_values(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _json_options(values: Iterable[Any]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _row(
    story: dict[str, Any],
    tier: str,
    frame_index: int,
    word_index: int,
    word: str,
    question_type: str,
    prompt: str,
    correct_answer: str,
    translation: str,
    pinyin: str,
    part_of_speech: str,
    options: Iterable[Any],
    context_sentence: str = "",
    source: str = "live",
) -> dict[str, Any]:
    return {
        "story_id": story.get("id", ""),
        "story_title": story.get("title", ""),
        "published": bool(story.get("published")),
        "lesson_number": story.get("lesson_number") or "",
        "tier": tier,
        "frame_index": frame_index,
        "word_index": word_index,
        "word": word,
        "question_type": question_type,
        "prompt": prompt,
        "correct_answer": correct_answer,
        "translation": translation,
        "pinyin": pinyin,
        "part_of_speech": part_of_speech,
        "options_from_source": _json_options(options),
        "context_sentence": context_sentence,
        "source": source,
    }


def _material_rows(
    story: dict[str, Any],
    tier: str,
    frame_index: int,
    frame: dict[str, Any],
    *,
    source: str,
    ai_material: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Flatten one frame's vocabulary and question pools."""
    # Quiz identity intentionally stays on the Easy/base vocabulary for all
    # tiers. The frontend uses that same stable list so a Medium/Hard story
    # level does not shift AI material onto a different word by array index.
    words = _csv_values(frame.get("vocabulary"))
    translations = _csv_values(frame.get("vocabularyTranslation"))
    pinyins = _csv_values(frame.get("vocabularyPinyin"))
    parts_of_speech = _csv_values(frame.get("vocabularyPos"))

    # AI pools are only index-aligned with the Easy vocabulary in the
    # application. Approved snapshots are keyed by word, so they are mapped
    # separately below and never accidentally shifted onto a tier word.
    if ai_material is None:
        distractors_by_word = _json_value(frame.get("vocabularyDistractors"), [])
        cloze_by_word = _json_value(frame.get("vocabularyCloze"), [])
        synonym_by_word = _json_value(frame.get("vocabularySynonym"), [])
    else:
        distractors_by_word = []
        cloze_by_word = []
        synonym_by_word = []

    suggested_answer = str(frame.get("suggestedAnswer") or "").strip()
    valid_indices = [
        index
        for index, word in enumerate(words)
        if index < len(translations)
        and translations[index]
        and (not suggested_answer or word in suggested_answer)
    ]
    all_translations = [translations[index] for index in valid_indices]
    all_words = [words[index] for index in valid_indices]
    all_pinyins = [pinyins[index] for index in valid_indices if index < len(pinyins) and pinyins[index]]
    rows: list[dict[str, Any]] = []

    for word_index, word in enumerate(words):
        translation = translations[word_index] if word_index < len(translations) else ""
        pinyin = pinyins[word_index] if word_index < len(pinyins) else ""
        part_of_speech = parts_of_speech[word_index] if word_index < len(parts_of_speech) else ""

        if ai_material is not None:
            entry = ai_material.get(word) or {}
            distractors = entry.get("distractors") or []
            cloze_candidates = entry.get("cloze") or []
            synonym_candidates = entry.get("synonym") or []
        else:
            distractors = (
                distractors_by_word[word_index]
                if isinstance(distractors_by_word, list) and word_index < len(distractors_by_word)
                else []
            )
            cloze_candidates = (
                cloze_by_word[word_index]
                if isinstance(cloze_by_word, list) and word_index < len(cloze_by_word)
                else []
            )
            synonym_candidates = (
                synonym_by_word[word_index]
                if isinstance(synonym_by_word, list) and word_index < len(synonym_by_word)
                else []
            )

        # collectQuizEntries() applies the same gates: a quiz entry needs a
        # translation and, when present, must occur in the scene sentence.
        if not translation or word_index not in valid_indices:
            continue

        if translation:
            rows.append(
                _row(
                    story, tier, frame_index, word_index, word, "translation", word,
                    translation, translation, pinyin, part_of_speech, distractors,
                    source=source,
                )
            )
            if len(all_words) >= 2:
                rows.append(
                    _row(
                        story, tier, frame_index, word_index, word, "reverse", translation,
                        word, translation, pinyin, part_of_speech, all_words,
                        source=source,
                    )
                )
                rows.append(
                    _row(
                        story, tier, frame_index, word_index, word, "listening", word, word,
                        translation, pinyin, part_of_speech, all_words, source=source,
                    )
                )
        if pinyin:
            rows.append(
                _row(
                    story, tier, frame_index, word_index, word, "pinyin", word, pinyin,
                    translation, pinyin, part_of_speech, all_pinyins, source=source,
                )
            )
        if part_of_speech:
            rows.append(
                _row(
                    story, tier, frame_index, word_index, word, "pos", word, part_of_speech,
                    translation, pinyin, part_of_speech, [], source=source,
                )
            )

        for candidate in cloze_candidates if isinstance(cloze_candidates, list) else []:
            if not isinstance(candidate, dict):
                continue
            sentence = str(candidate.get("sentence") or "")
            if not sentence or sentence.count(word) != 1:
                continue
            rows.append(
                _row(
                    story, tier, frame_index, word_index, word, "cloze",
                    sentence.replace(word, "____", 1), word, translation, pinyin,
                    part_of_speech, candidate.get("distractors") or [], sentence, source,
                )
            )

        for candidate in synonym_candidates if isinstance(synonym_candidates, list) else []:
            if not isinstance(candidate, dict):
                continue
            synonym = str(candidate.get("synonym") or "")
            if not synonym:
                continue
            rows.append(
                _row(
                    story, tier, frame_index, word_index, word, "synonym", word, synonym,
                    translation, pinyin, part_of_speech, candidate.get("distractors") or [],
                    source=source,
                )
            )

    return rows


def _approved_by_level(snapshot: Any) -> dict[str, dict[str, dict[str, Any]]]:
    """Normalize approved snapshot JSON into level -> word -> material."""
    decoded = _json_value(snapshot, {})
    if not isinstance(decoded, dict):
        return {}
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for level, entries in decoded.items():
        if not isinstance(entries, list):
            continue
        by_word: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if isinstance(entry, dict) and str(entry.get("word") or "").strip():
                by_word[str(entry["word"]).strip()] = entry
        if by_word:
            result[str(level)] = by_word
    return result


def build_question_rows(stories: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build normalized rows from database story dictionaries."""
    rows: list[dict[str, Any]] = []
    for story in stories:
        frames = story.get("frames") or []
        if not isinstance(frames, list):
            continue
        approved = _approved_by_level(story.get("quiz_approved_snapshot"))
        for frame_index, frame in enumerate(frames):
            if not isinstance(frame, dict):
                continue
            # Live material follows the current story editor, which is the
            # source used by teacher review and by legacy quiz fallback.
            for tier in TIERS:
                rows.extend(_material_rows(story, tier, frame_index, frame, source="live"))

                # An approved snapshot is keyed by level and word. It is
                # exported separately so a teacher can compare draft vs the
                # material actually approved for students.
                approved_material = approved.get(tier)
                if approved_material:
                    rows.extend(
                        _material_rows(
                            story, tier, frame_index, frame, source="approved",
                            ai_material=approved_material,
                        )
                    )
    return rows


def export_questions(output: str | Path) -> tuple[Path, int]:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as db:
        stories = [dict(row) for row in db.execute(
            "SELECT id, title, published, lesson_number, frames, quiz_approved_snapshot "
            "FROM custom_stories ORDER BY lesson_number NULLS LAST, created_at, id"
        ).fetchall()]

    rows = build_question_rows(stories)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return output_path, len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export all stored quiz questions to an Excel-friendly CSV.")
    parser.add_argument(
        "--output",
        default=f"quiz_questions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        help="Output CSV path (default: quiz_questions_<timestamp>.csv)",
    )
    args = parser.parse_args()
    output_path, row_count = export_questions(args.output)
    print(f"Exported {row_count} questions to {output_path}")


if __name__ == "__main__":
    main()
