"""Validate and publish the canonical Chapters 5–8 question bank.

The workbook's Questions sheet is exported to
``data/quiz_assessments/modern-chinese-ch5-to-ch8-question-bank.csv`` so the
seed is repeatable in the backend container.  Validation runs by default;
database writes require the explicit ``--publish`` flag.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg.types.json import Jsonb  # noqa: E402

from db import connect_db  # noqa: E402
from scripts.seed_quiz_assessments import find_story_for_part  # noqa: E402
from domain.vocabulary.assessment import (
    ANSWER_FORMAT_BY_ROUND,
    QUESTION_TYPE_BY_ROUND,
    TIER_BY_ROUND,
    validate_assessment_payload,
)  # noqa: E402


BANK_PATH = Path(__file__).resolve().parent / "data" / "quiz_assessments" / "modern-chinese-ch5-to-ch8-question-bank.csv"
ROUNDS = {
    "Round 1": 1,
    "Round 2": 2,
    "Round 3": 3,
}
REQUIRED_COLUMNS = {
    "Question ID", "Word Key", "Source Type", "Chapter", "Section", "Item",
    "Traditional Chinese", "Pinyin", "POS", "English Meaning", "Round",
    "Question Type", "Input Mode", "Prompt", "Option A", "Option B",
    "Option C", "Option D", "Correct Option", "Correct Answer", "Accepted Answers",
}

def read_rows(path: Path = BANK_PATH) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = REQUIRED_COLUMNS.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Workbook export is missing columns: {', '.join(sorted(missing))}")
        return [dict(row) for row in reader if row.get("Question ID")]


def _answers(value: str) -> list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]


def validate_source_rows(rows: Iterable[dict[str, str]]) -> list[str]:
    rows = list(rows)
    issues: list[str] = []
    if len(rows) != 648:
        issues.append(f"expected 648 rows, found {len(rows)}")
    seen_question_ids: set[str] = set()
    by_word: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        qid = row["Question ID"]
        if qid in seen_question_ids:
            issues.append(f"duplicate Question ID: {qid}")
        seen_question_ids.add(qid)
        if qid.casefold().endswith(("_easy", "_medium", "_hard")):
            issues.append(f"{qid}: Question ID must not use an Easy/Medium/Hard suffix")
        by_word[row["Word Key"]].append(row)
        section = row["Section"]
        if section not in {f"{chapter}-{part}" for chapter in range(5, 9) for part in range(1, 4)}:
            issues.append(f"{qid}: unsupported section {section}")
        round_info = ROUNDS.get(row["Round"])
        if round_info is None:
            issues.append(f"{qid}: unsupported round {row['Round']}")
            continue
        round_number = round_info
        answer_format = ANSWER_FORMAT_BY_ROUND[round_number]
        expected_type = QUESTION_TYPE_BY_ROUND[round_number]
        if row["Question Type"] != expected_type:
            issues.append(f"{qid}: {row['Round']} uses {row['Question Type']}, expected {expected_type}")
        if row["Input Mode"] == "click" and answer_format != "single_choice":
            issues.append(f"{qid}: click input is not a single-choice question")
        if row["Input Mode"] == "free_text" and answer_format != "free_text":
            issues.append(f"{qid}: free-text input has the wrong answer format")
        if answer_format == "single_choice":
            options = [row[f"Option {letter}"] for letter in "ABCD"]
            if len(set(options)) != 4 or any(not option for option in options):
                issues.append(f"{qid}: options must contain four distinct values")
            if row["Correct Option"] not in "ABCD":
                issues.append(f"{qid}: invalid correct option {row['Correct Option']!r}")
            elif options["ABCD".index(row["Correct Option"])] != row["Correct Answer"]:
                issues.append(f"{qid}: correct option does not match correct answer")
        else:
            accepted = _answers(row["Accepted Answers"])
            if row["Correct Answer"] not in accepted:
                issues.append(f"{qid}: pinyin correct answer is not accepted")
        for required in ("Word Key", "Traditional Chinese", "Pinyin", "POS", "English Meaning", "Prompt", "Correct Answer"):
            if not row[required].strip():
                issues.append(f"{qid}: empty {required}")
    for word_id, word_rows in by_word.items():
        if len(word_rows) != 3 or {ROUNDS.get(row["Round"]) for row in word_rows} != set(ROUNDS.values()):
            issues.append(f"{word_id}: expected exactly one row for each round")
        for field in ("Chapter", "Section", "Item", "Traditional Chinese", "Pinyin", "POS", "English Meaning"):
            if len({row[field] for row in word_rows}) != 1:
                issues.append(f"{word_id}: inconsistent {field} metadata")
    return issues


def _question(row: dict[str, str]) -> dict[str, Any]:
    round_number = ROUNDS[row["Round"]]
    answer_format = ANSWER_FORMAT_BY_ROUND[round_number]
    question_type = row["Question Type"]
    options = [row[f"Option {letter}"] for letter in "ABCD"] if answer_format == "single_choice" else []
    accepted = _answers(row["Accepted Answers"]) if row["Accepted Answers"] else [row["Correct Answer"]]
    explanation = f"Correct answer: {row['Correct Answer']}."
    return {
        "questionId": row["Question ID"],
        "wordId": row["Word Key"],
        "targetWord": row["Traditional Chinese"],
        "pinyin": row["Pinyin"],
        "pos": row["POS"],
        "simpleEnglishMeaning": row["English Meaning"],
        "round": round_number,
        "tier": TIER_BY_ROUND[round_number],
        "questionType": question_type,
        "answerFormat": answer_format,
        "prompt": row["Prompt"],
        "options": options,
        "correctAnswer": row["Correct Answer"],
        "acceptedAnswers": accepted,
        "explanation": explanation,
        "sourceType": row.get("Source Type", ""),
    }


def build_payloads(rows: Iterable[dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
    payloads: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        payloads[row["Section"]].append(_question(row))
    for section, payload in payloads.items():
        payload.sort(key=lambda question: (question["wordId"], question["round"]))
        issues = validate_assessment_payload(payload)
        if issues:
            rendered = "; ".join(f"{issue.code}: {issue.message}" for issue in issues[:8])
            raise ValueError(f"{section} payload failed validation ({len(issues)} issues): {rendered}")
    return dict(payloads)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lesson-part", action="append", dest="lesson_parts", help="Limit publishing to one or more parts, e.g. 5-2.")
    parser.add_argument("--publish", action="store_true", help="Write validated banks to matching existing stories.")
    args = parser.parse_args()
    rows = read_rows()
    source_issues = validate_source_rows(rows)
    if source_issues:
        raise SystemExit("Question bank validation failed:\n" + "\n".join(source_issues[:30]))
    payloads = build_payloads(rows)
    selected = args.lesson_parts or sorted(payloads)
    unknown = sorted(set(selected).difference(payloads))
    if unknown:
        raise SystemExit(f"Unsupported lesson part(s): {', '.join(unknown)}")
    for section in selected:
        print(f"Lesson {section}: {len({row['wordId'] for row in payloads[section]})} items, {len(payloads[section])} questions [OK]")
    if not args.publish:
        print("Validation only; no database changes made.")
        return 0
    with connect_db() as db:
        targets = {section: find_story_for_part(db, section) for section in selected}
        for section in selected:
            target = targets[section]
            db.execute("UPDATE custom_stories SET vocab_assessment = %s WHERE id = %s", (Jsonb(payloads[section]), target["id"]))
            print(f"Published Lesson {section} bank to {target['id']} ({target['title']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
