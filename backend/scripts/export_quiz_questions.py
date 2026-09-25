"""Export the canonical ``custom_stories.vocab_assessment`` bank to CSV.

The exporter deliberately reads only the validated question bank. Frame-level
quiz pools and the removed Quiz Review snapshots are not compatibility inputs.
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

from db import connect_db  # noqa: E402


DEFAULT_TIERS = ("tier1",)
ALL_TIERS = ("tier1", "tier2", "tier3")

CSV_FIELDS = (
    "story_id", "story_title", "published", "lesson_number", "lesson_sub_order",
    "tier", "frame_index", "word_index", "word", "question_type", "prompt",
    "correct_answer", "translation", "pinyin", "part_of_speech",
    "options_from_source", "context_sentence", "source", "validation_status",
    "validation_errors",
)

VALIDATION_FIELDS = (
    "story_id", "story_title", "tier", "frame_index", "word_index", "word",
    "question_type", "prompt", "correct_answer", "options_from_source", "source",
    "validation_status", "validation_errors",
)


def _json_options(value: Any) -> str:
    return json.dumps(value if isinstance(value, list) else [], ensure_ascii=False)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _question_errors(question: dict[str, Any]) -> list[str]:
    errors = [
        f"missing_{field}"
        for field in ("word", "prompt", "correct_answer")
        if not _text(question.get(field))
    ]
    options = question.get("options")
    if not isinstance(options, list):
        errors.append("malformed_options")
        options = []
    normalized = [_text(option).casefold() for option in options if _text(option)]
    if len(normalized) != len(set(normalized)):
        errors.append("duplicate_options")
    if question.get("question_type") in {"basic_meaning_mcq", "context_cloze_mcq"}:
        answer = _text(question.get("correct_answer")).casefold()
        if answer and answer not in normalized:
            errors.append("correct_answer_missing_from_options")
    return errors


def _validation_record(story: dict[str, Any], question: dict[str, Any], errors: Iterable[str]) -> dict[str, Any]:
    error_list = list(dict.fromkeys(errors))
    return {
        "story_id": story.get("id", ""), "story_title": story.get("title", ""),
        "tier": question.get("tier", ""), "frame_index": "", "word_index": "",
        "word": question.get("word", ""), "question_type": question.get("question_type", ""),
        "prompt": question.get("prompt", ""), "correct_answer": question.get("correct_answer", ""),
        "options_from_source": _json_options(question.get("options")),
        "source": "vocab_assessment", "validation_status": "error" if error_list else "ok",
        "validation_errors": "; ".join(error_list),
    }


def _canonical_question(story: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    round_number = item.get("round")
    try:
        round_number = int(round_number)
    except (TypeError, ValueError):
        round_number = None
    tier = _text(item.get("tier"))
    if not tier and round_number in {1, 2, 3}:
        tier = f"tier{round_number}"
    return {
        "story_id": story.get("id", ""), "story_title": story.get("title", ""),
        "published": bool(story.get("published")), "lesson_number": story.get("lesson_number") or "",
        "lesson_sub_order": story.get("lesson_sub_order") or "",
        "tier": tier, "frame_index": "", "word_index": "",
        "word": _text(item.get("targetWord") or item.get("target_word") or item.get("wordId") or item.get("word_id")),
        "question_type": _text(item.get("questionType") or item.get("question_type")),
        "prompt": _text(item.get("prompt") or item.get("questionPrompt")),
        "correct_answer": _text(item.get("correctAnswer") or item.get("correct_answer")),
        "translation": _text(item.get("simpleEnglishMeaning") or item.get("translation")),
        "pinyin": _text(item.get("pinyin")),
        "part_of_speech": _text(item.get("pos") or item.get("partOfSpeech")),
        "options": item.get("options") if isinstance(item.get("options"), list) else [],
        "context_sentence": _text(item.get("contextSentence") or item.get("context_sentence")),
        "source": "vocab_assessment",
        "validation_status": _text(item.get("validationStatus") or item.get("validation_status")) or "ok",
        "validation_errors": "",
    }


def build_question_rows(
    stories: Iterable[dict[str, Any]], *, tiers: Iterable[str] = DEFAULT_TIERS,
    validation_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build normalized CSV rows from the canonical assessment bank."""
    allowed_tiers = set(tiers)
    rows: list[dict[str, Any]] = []
    for story in stories:
        assessment = story.get("vocab_assessment")
        if not isinstance(assessment, list):
            continue
        for item in assessment:
            if not isinstance(item, dict):
                if validation_rows is not None:
                    validation_rows.append(_validation_record(story, {}, ["invalid_question"]))
                continue
            row = _canonical_question(story, item)
            if row["tier"] not in allowed_tiers:
                continue
            errors = _question_errors(row)
            row["validation_status"] = "error" if errors else row["validation_status"]
            row["validation_errors"] = "; ".join(errors)
            row["options_from_source"] = _json_options(row.pop("options"))
            rows.append(row)
            if validation_rows is not None:
                validation_rows.append(_validation_record(story, _canonical_question(story, item), errors))
    return rows


def _export_questions_with_summary(
    output: str | Path, validation_output: str | Path | None = None, *,
    include_all_stories: bool = False, include_all_tiers: bool = False,
) -> tuple[Path, int, int, int]:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path = Path(validation_output) if validation_output else None
    if validation_path:
        validation_path.parent.mkdir(parents=True, exist_ok=True)
    query = (
        "SELECT id, title, published, lesson_number, lesson_sub_order, "
        "vocab_assessment FROM custom_stories "
    )
    if not include_all_stories:
        query += "WHERE published = TRUE AND lesson_number IS NOT NULL AND id LIKE 'custom-story-%' "
    query += "ORDER BY lesson_number NULLS LAST, created_at, id"
    with connect_db() as db:
        stories = [dict(row) for row in db.execute(query).fetchall()]
    validation_rows: list[dict[str, Any]] = []
    rows = build_question_rows(
        stories, tiers=ALL_TIERS if include_all_tiers else DEFAULT_TIERS,
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


def export_questions(output: str | Path, validation_output: str | Path | None = None, *, include_all_stories: bool = False, include_all_tiers: bool = False) -> Path:
    return _export_questions_with_summary(
        output, validation_output, include_all_stories=include_all_stories,
        include_all_tiers=include_all_tiers,
    )[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export canonical vocab_assessment questions to CSV.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validation-output", type=Path)
    parser.add_argument("--all-stories", action="store_true")
    parser.add_argument("--all-tiers", action="store_true")
    args = parser.parse_args()
    output = args.output or Path(f"quiz_questions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    output_path, question_count, story_count, error_count = _export_questions_with_summary(
        output, args.validation_output, include_all_stories=args.all_stories,
        include_all_tiers=args.all_tiers,
    )
    print(f"Exported {question_count} questions from {story_count} stories to {output_path}")
    if args.validation_output:
        print(f"Validation rows: {args.validation_output} ({error_count} errors)")


if __name__ == "__main__":
    main()
