"""Export the quiz question material stored in custom stories to CSV.

The story editor stores quiz material inside each frame as a mixture of
comma-separated text and JSON-encoded arrays.  This script normalizes that
material into one row per question so the result can be opened in Excel or
uploaded to Google Sheets.

Usage:
    python -m scripts.export_quiz_questions
    python -m scripts.export_quiz_questions --output ..\\output\\quiz_questions.csv
    python -m scripts.export_quiz_questions --validation-output ..\\output\\quiz_validation.csv

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


DEFAULT_TIERS = ("easy",)
ALL_TIERS = ("easy", "medium", "hard")

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
    "validation_status",
    "validation_errors",
)

VALIDATION_FIELDS = (
    "story_id",
    "story_title",
    "tier",
    "frame_index",
    "word_index",
    "word",
    "question_type",
    "prompt",
    "correct_answer",
    "options_from_source",
    "source",
    "validation_status",
    "validation_errors",
)


def _json_value(value: Any, fallback: Any) -> tuple[Any, bool]:
    """Decode a JSON-encoded field and indicate whether it was malformed."""
    if value is None or value == "":
        return fallback, False
    if isinstance(value, (list, dict)):
        return value, False
    if not isinstance(value, str):
        return fallback, True
    try:
        return json.loads(value), False
    except (TypeError, json.JSONDecodeError):
        return fallback, True


def _csv_values(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _json_options(values: Iterable[Any]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _validation_record(
    story: dict[str, Any],
    tier: str,
    frame_index: int,
    word_index: int,
    word: str,
    question_type: str,
    errors: Iterable[str],
    *,
    prompt: str = "",
    correct_answer: str = "",
    options: Iterable[Any] = (),
    source: str = "live",
) -> dict[str, Any]:
    error_list = list(dict.fromkeys(errors))
    return {
        "story_id": story.get("id", ""),
        "story_title": story.get("title", ""),
        "tier": tier,
        "frame_index": frame_index,
        "word_index": word_index,
        "word": word,
        "question_type": question_type,
        "prompt": prompt,
        "correct_answer": correct_answer,
        "options_from_source": _json_options(options),
        "source": source,
        "validation_status": "error" if error_list else "ok",
        "validation_errors": "; ".join(error_list),
    }


def _question_errors(row: dict[str, Any]) -> list[str]:
    """Return quality issues where source options are intended as distractors."""
    errors = []
    for field in ("word", "prompt", "correct_answer"):
        if not str(row.get(field) or "").strip():
            errors.append(f"missing_{field}")

    try:
        options = json.loads(row["options_from_source"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return [*errors, "malformed_options_json"]
    if not isinstance(options, list):
        return [*errors, "malformed_options_json"]

    normalized_options = [
        " ".join(str(option).casefold().split())
        for option in options
        if str(option).strip()
    ]
    correct_answer = str(row.get("correct_answer") or "").strip()
    # Reverse/listening/pinyin rows use a pool of possible answers as their
    # source options, so the correct answer is expected to be present there.
    # Translation/cloze/synonym rows instead use AI-provided distractors, so
    # an answer appearing in those pools is a genuine quality defect.
    distractor_kinds = {"translation", "cloze", "synonym"}
    normalized_answer = " ".join(correct_answer.casefold().split())
    if row.get("question_type") in distractor_kinds and normalized_answer in normalized_options:
        errors.append("correct_answer_in_options")
    if len(normalized_options) != len(set(normalized_options)):
        errors.append("duplicate_options")
    return errors


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
        "validation_status": "ok",
        "validation_errors": "",
    }


def _material_rows(
    story: dict[str, Any],
    tier: str,
    frame_index: int,
    frame: dict[str, Any],
    *,
    source: str,
    ai_material: dict[str, Any] | None = None,
    validation_rows: list[dict[str, Any]] | None = None,
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
        distractors_by_word, distractors_malformed = _json_value(frame.get("vocabularyDistractors"), [])
        cloze_by_word, cloze_malformed = _json_value(frame.get("vocabularyCloze"), [])
        synonym_by_word, synonym_malformed = _json_value(frame.get("vocabularySynonym"), [])
        if validation_rows is not None:
            for field, malformed in (
                ("vocabularyDistractors", distractors_malformed),
                ("vocabularyCloze", cloze_malformed),
                ("vocabularySynonym", synonym_malformed),
            ):
                if malformed:
                    validation_rows.append(_validation_record(
                        story, tier, frame_index, -1, "", "source",
                        [f"malformed_json:{field}"], source=source,
                    ))
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
                if validation_rows is not None:
                    validation_rows.append(_validation_record(
                        story, tier, frame_index, word_index, word, "cloze",
                        ["cloze_sentence_must_contain_word_exactly_once"],
                        prompt=sentence, correct_answer=word,
                        options=candidate.get("distractors") or [], source=source,
                    ))
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
            if not synonym or synonym == word:
                if validation_rows is not None:
                    validation_rows.append(_validation_record(
                        story, tier, frame_index, word_index, word, "synonym",
                        ["empty_synonym" if not synonym else "synonym_matches_word"],
                        prompt=word, correct_answer=synonym,
                        options=candidate.get("distractors") or [], source=source,
                    ))
                continue
            rows.append(
                _row(
                    story, tier, frame_index, word_index, word, "synonym", word, synonym,
                    translation, pinyin, part_of_speech, candidate.get("distractors") or [],
                    source=source,
                )
            )

    for row in rows:
        errors = _question_errors(row)
        row["validation_status"] = "error" if errors else "ok"
        row["validation_errors"] = "; ".join(errors)
        if validation_rows is not None:
            validation_rows.append(_validation_record(
                story, tier, frame_index, row["word_index"], row["word"],
                row["question_type"], errors, prompt=row["prompt"],
                correct_answer=row["correct_answer"],
                options=json.loads(row["options_from_source"]), source=source,
            ))
    return rows


def _approved_by_level(snapshot: Any) -> tuple[dict[str, dict[str, dict[str, Any]]], bool]:
    """Normalize approved snapshot JSON into level -> word -> material."""
    decoded, malformed = _json_value(snapshot, {})
    if not isinstance(decoded, dict):
        return {}, malformed
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
    return result, malformed


def build_question_rows(
    stories: Iterable[dict[str, Any]],
    *,
    tiers: Iterable[str] = DEFAULT_TIERS,
    validation_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build normalized rows from database story dictionaries."""
    rows: list[dict[str, Any]] = []
    for story in stories:
        frames = story.get("frames") or []
        if not isinstance(frames, list):
            continue
        approved, approved_malformed = _approved_by_level(story.get("quiz_approved_snapshot"))
        for frame_index, frame in enumerate(frames):
            if not isinstance(frame, dict):
                continue
            if approved_malformed and validation_rows is not None:
                validation_rows.append(_validation_record(
                    story, "easy", frame_index, -1, "", "source",
                    ["malformed_json:quiz_approved_snapshot"], source="approved",
                ))
            # Live material follows the current story editor, which is the
            # source used by teacher review and by legacy quiz fallback.
            for tier in tiers:
                rows.extend(_material_rows(
                    story, tier, frame_index, frame, source="live", validation_rows=validation_rows,
                ))

                # An approved snapshot is keyed by level and word. It is
                # exported separately so a teacher can compare draft vs the
                # material actually approved for students.
                approved_material = approved.get(tier)
                if approved_material:
                    rows.extend(
                        _material_rows(
                            story, tier, frame_index, frame, source="approved",
                            ai_material=approved_material,
                            validation_rows=validation_rows,
                        )
                    )
    return rows


def _export_questions_with_summary(
    output: str | Path,
    validation_output: str | Path | None = None,
    *,
    include_all_stories: bool = False,
    include_all_tiers: bool = False,
) -> tuple[Path, int, int, int]:
    """Export questions and return output path, questions, stories, and errors."""
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path = Path(validation_output) if validation_output else None
    if validation_path:
        validation_path.parent.mkdir(parents=True, exist_ok=True)

    query = (
        "SELECT id, title, published, lesson_number, frames, quiz_approved_snapshot "
        "FROM custom_stories "
    )
    if not include_all_stories:
        query += (
            "WHERE published = TRUE AND lesson_number IS NOT NULL "
            "AND id LIKE 'custom-story-%' "
        )
    query += "ORDER BY lesson_number NULLS LAST, created_at, id"
    with connect_db() as db:
        stories = [dict(row) for row in db.execute(query).fetchall()]

    validation_rows: list[dict[str, Any]] = []
    rows = build_question_rows(
        stories,
        tiers=ALL_TIERS if include_all_tiers else DEFAULT_TIERS,
        validation_rows=validation_rows,
    )
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    if validation_path:
        with validation_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=VALIDATION_FIELDS)
            writer.writeheader()
            writer.writerows(validation_rows)
    error_count = sum(row["validation_status"] == "error" for row in validation_rows)
    return output_path, len(rows), len(stories), error_count


def export_questions(
    output: str | Path,
    validation_output: str | Path | None = None,
    *,
    include_all_stories: bool = False,
    include_all_tiers: bool = False,
) -> tuple[Path, int]:
    """Export questions, retaining the script's original public return shape."""
    output_path, row_count, _, _ = _export_questions_with_summary(
        output,
        validation_output,
        include_all_stories=include_all_stories,
        include_all_tiers=include_all_tiers,
    )
    return output_path, row_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export current published custom-story quiz questions to an Excel-friendly CSV."
    )
    parser.add_argument(
        "--output",
        default=f"quiz_questions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        help="Output CSV path (default: quiz_questions_<timestamp>.csv)",
    )
    parser.add_argument(
        "--validation-output",
        help="Optional CSV path for one quality-validation record per exported row or invalid candidate.",
    )
    parser.add_argument(
        "--all-stories",
        action="store_true",
        help="Include unpublished, unnumbered, and non-custom stories (default: current published custom-story scope).",
    )
    parser.add_argument(
        "--all-tiers",
        action="store_true",
        help="Export easy, medium, and hard tiers (default: easy/base only).",
    )
    args = parser.parse_args()
    output_path, row_count, story_count, error_count = _export_questions_with_summary(
        args.output,
        args.validation_output,
        include_all_stories=args.all_stories,
        include_all_tiers=args.all_tiers,
    )
    print(f"Exported {row_count} questions from {story_count} stories to {output_path}")
    if args.validation_output:
        print(f"Validation report: {args.validation_output} ({error_count} errors)")
    else:
        print(f"Validation errors: {error_count} (also included in the export CSV)")


if __name__ == "__main__":
    main()
