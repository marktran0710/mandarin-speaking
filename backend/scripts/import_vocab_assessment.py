"""Validate and optionally attach a fixed CSV assessment to a custom story.

Validation is the default. Database writes require an explicit story id and
``--publish`` so an incomplete educational bank cannot be stored silently.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg.types.json import Jsonb  # noqa: E402

from database import connect_db  # noqa: E402
from vocab_assessment import build_vocabulary_items, parse_vocab_assessment_csv  # noqa: E402


def assessment_payload(source: str | Path) -> list[dict]:
    questions = parse_vocab_assessment_csv(source)
    items = build_vocabulary_items(questions)
    return [
        {
            "questionId": question.question_id,
            "wordId": question.word_id,
            "targetWord": question.target_word,
            "pinyin": question.pinyin,
            "pos": question.part_of_speech,
            "simpleEnglishMeaning": question.simple_english_meaning,
            "level": question.level.casefold(),
            "difficultyWeight": question.difficulty_weight,
            "questionType": question.question_type,
            "answerFormat": question.answer_format,
            "prompt": question.prompt,
            "options": list(question.options),
            "correctAnswer": question.correct_answer,
            "acceptedAnswers": list(question.accepted_answers),
            "explanation": question.explanation,
            # Keep the source row available for audit/replay; the normalized
            # fields above are the runtime contract, while this is provenance.
            "raw": dict(question.raw),
        }
        for item in items
        for question in item.observations
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--story-id", help="custom_stories.id to update")
    parser.add_argument("--publish", action="store_true", help="write the validated bank to the story")
    args = parser.parse_args()

    payload = assessment_payload(args.csv_path)
    print(f"Vocabulary items: {len({row['wordId'] for row in payload})} [OK]")
    print(f"Questions: {len(payload)} [OK]")
    if not args.publish:
        print("Validation only; no database changes made.")
        return 0
    if not args.story_id:
        parser.error("--story-id is required with --publish")

    with connect_db() as db:
        updated = db.execute(
            "UPDATE custom_stories SET vocab_assessment = %s WHERE id = %s RETURNING id",
            (Jsonb(payload), args.story_id),
        ).fetchone()
    if not updated:
        raise SystemExit(f"Story not found: {args.story_id}")
    print(f"Imported assessment into story {args.story_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
