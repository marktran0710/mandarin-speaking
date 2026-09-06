"""Generate a reproducible synthetic Easy-level BKT pilot for one story.

The output is deliberately file-based and never writes to the application
database. It creates three diagnostic attempts per synthetic student with the
requested 20/22/25 question capacities, then fits the existing global BKT
estimator to the generated binary responses.

Run from ``backend/`` with::

    python scripts/generate_bkt_fake_data.py

The generated values are suitable for UI/demo work and pipeline smoke tests,
not for changing production BKT defaults or making research claims.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.knowledge_tracing import (  # noqa: E402
    BKT,
    BKTParameters,
    ResponseRecord,
    evaluate_prequential,
    fit_bkt_parameters,
    normalize_vocab_attempts,
)


STORY_TITLE = "我們去喝下午茶"
DEFAULT_STORY_ID = "custom-story-1784770916021"
QUIZ_SLOTS: tuple[tuple[str, str, int], ...] = (
    ("quiz_1", "tier1", 20),
    ("quiz_2", "tier2", 22),
    ("quiz_3", "tier3", 25),
)
QUESTION_KINDS = ("translation", "reverse", "listening")
TRUE_PARAMETERS = BKTParameters(prior=0.25, learn=0.18, guess=0.18, slip=0.08)
FIT_INITIAL_PARAMETERS = BKTParameters()


def _unique_words(story: dict[str, Any]) -> list[str]:
    words: list[str] = []
    for frame in story.get("frames") or []:
        raw_words = frame.get("vocabulary") or ""
        for word in raw_words.split(","):
            clean = word.strip()
            if clean and clean not in words:
                words.append(clean)
    return words


def load_story() -> tuple[str, str, list[str]]:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "components"
        / "__fixtures__"
        / "custom-stories.json"
    )
    stories = json.loads(fixture_path.read_text(encoding="utf-8"))
    story = next((item for item in stories if item.get("title") == STORY_TITLE), None)
    if story is None:
        raise RuntimeError(f"Could not find {STORY_TITLE!r} in {fixture_path}")
    words = _unique_words(story)
    if len(words) < 31:
        raise RuntimeError(f"Expected at least 31 unique vocabulary words, found {len(words)}")
    return str(story.get("id") or DEFAULT_STORY_ID), str(story.get("title") or STORY_TITLE), words


def build_schedule(word_count: int) -> list[tuple[str, str, int]]:
    """Return a balanced 20/22/25 item schedule over the story vocabulary."""
    if word_count < 31:
        raise ValueError("The requested schedule needs at least 31 vocabulary concepts")
    schedules = {
        "quiz_1": list(range(20)),
        "quiz_2": list(range(10)) + list(range(20, 31)) + [10],
        "quiz_3": list(range(10, 31)) + list(range(4)),
    }
    result: list[tuple[str, str, int]] = []
    for quiz_slot, mode, capacity in QUIZ_SLOTS:
        indices = schedules[quiz_slot]
        if len(indices) != capacity:
            raise AssertionError(f"{quiz_slot} has {len(indices)} scheduled items, expected {capacity}")
        result.extend((quiz_slot, mode, word_index) for word_index in indices)
    return result


def _record_for_simulation(
    student_id: str,
    word: str,
    correct: bool,
    attempt_id: str,
    mode: str,
    question_index: int,
    occurred_at: datetime,
) -> ResponseRecord:
    return ResponseRecord(
        student_id=student_id,
        concept_id=word,
        correct=correct,
        occurred_at=occurred_at,
        attempt_id=attempt_id,
        question_index=question_index,
        story_id=DEFAULT_STORY_ID,
        item_id=f"{DEFAULT_STORY_ID}:easy:{attempt_id}:{question_index + 1}",
        question_kind=QUESTION_KINDS[question_index % len(QUESTION_KINDS)],
        level="easy",
        mode=mode,
        item_version="fake-v1",
    )


def generate_attempts(
    story_id: str,
    words: list[str],
    student_count: int,
    seed: int,
) -> list[dict[str, Any]]:
    schedule = build_schedule(len(words))
    rng = random.Random(seed)
    attempts: list[dict[str, Any]] = []
    start = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)

    for student_number in range(1, student_count + 1):
        student_id = f"fake-student-{student_number:02d}"
        student_name = f"Synthetic Student {student_number:02d}"
        tracer = BKT(TRUE_PARAMETERS)
        schedule_offset = 0
        for quiz_number, (quiz_slot, mode, capacity) in enumerate(QUIZ_SLOTS, start=1):
            attempt_id = f"fake-bkt-{student_number:02d}-{quiz_slot}"
            completed_at = start + timedelta(days=student_number - 1, hours=quiz_number * 3)
            question_results: list[dict[str, Any]] = []
            total_time_ms = 0
            for question_index in range(capacity):
                _slot, _mode, word_index = schedule[schedule_offset + question_index]
                word = words[word_index]
                response_time_ms = max(900, int(rng.gauss(3200, 650)))
                probability = tracer.predict(student_id, word)
                correct = rng.random() < probability
                question_kind = QUESTION_KINDS[(schedule_offset + question_index) % len(QUESTION_KINDS)]
                item_id = f"{story_id}:easy:{quiz_slot}:item-{question_index + 1:02d}:{word_index:02d}"
                exposure_id = f"{student_id}:{story_id}:easy:{quiz_slot}:{question_index + 1:02d}"
                question_results.append({
                    "conceptId": word,
                    "word": word,
                    "correct": correct,
                    "questionKind": question_kind,
                    "level": "easy",
                    "mode": mode,
                    "diagnosticQuiz": quiz_slot,
                    "itemId": item_id,
                    "itemVersion": "fake-v1",
                    "diagnosticExposureId": exposure_id,
                    "isBktEligible": True,
                    "bktValidationStatus": "APPROVED",
                    "timeMs": response_time_ms,
                    "questionIndex": question_index,
                    "answeredAt": (completed_at + timedelta(milliseconds=total_time_ms)).isoformat(),
                })
                total_time_ms += response_time_ms
                tracer.update(_record_for_simulation(
                    student_id,
                    word,
                    correct,
                    attempt_id,
                    mode,
                    question_index,
                    completed_at,
                ))
            attempts.append({
                "id": attempt_id,
                "storyId": story_id,
                "baseStoryId": story_id,
                "studentId": student_id,
                "studentName": student_name,
                "mode": mode,
                "diagnosticQuiz": quiz_slot,
                "level": "easy",
                "completedAt": completed_at.isoformat(),
                "totalQuestions": capacity,
                "correctCount": sum(1 for result in question_results if result["correct"]),
                "totalTimeMs": total_time_ms,
                "questionResults": question_results,
            })
            schedule_offset += capacity
    return attempts


def score_records(records: Iterable[ResponseRecord], parameters: BKTParameters) -> dict[str, Any]:
    tracer = BKT(parameters)
    predictions: list[float] = []
    outcomes: list[bool] = []
    for record in records:
        prediction = tracer.predict(record.student_id, record.concept_id)
        predictions.append(prediction)
        outcomes.append(record.correct)
        tracer.update(record)
    if not outcomes:
        return {"n": 0, "accuracy": None, "logLoss": None, "brierScore": None}
    log_loss = -sum(
        math.log(probability if outcome else 1.0 - probability)
        for probability, outcome in zip(predictions, outcomes)
    ) / len(outcomes)
    brier = sum((probability - float(outcome)) ** 2 for probability, outcome in zip(predictions, outcomes)) / len(outcomes)
    return {
        "n": len(outcomes),
        "correct": sum(outcomes),
        "accuracy": sum(outcomes) / len(outcomes),
        "logLoss": log_loss,
        "brierScore": brier,
    }


def mastery_summary(records: Iterable[ResponseRecord], parameters: BKTParameters, words: list[str], student_count: int) -> list[dict[str, Any]]:
    records = list(records)
    tracer = BKT(parameters)
    for record in records:
        tracer.update(record)
    per_word: defaultdict[str, list[ResponseRecord]] = defaultdict(list)
    for record in records:
        per_word[record.concept_id].append(record)
    summary: list[dict[str, Any]] = []
    for word in words:
        rows = per_word[word]
        states = [tracer.mastery_for(f"fake-student-{number:02d}", word) for number in range(1, student_count + 1)]
        correct = sum(row.correct for row in rows)
        summary.append({
            "word": word,
            "responses": len(rows),
            "correct": correct,
            "accuracy": correct / len(rows) if rows else None,
            "averageMastery": sum(states) / len(states),
            "minMastery": min(states),
            "maxMastery": max(states),
        })
    return sorted(summary, key=lambda row: (row["averageMastery"], row["word"]))


def build_report(
    story_id: str,
    story_title: str,
    words: list[str],
    attempts: list[dict[str, Any]],
    seed: int,
    student_count: int,
) -> dict[str, Any]:
    normalized = normalize_vocab_attempts(attempts)
    eligible_normalized = normalize_vocab_attempts(
        attempts,
        eligible_only=True,
        deduplicate_diagnostic_exposures=True,
    )
    fitted = fit_bkt_parameters(normalized.records, initial=FIT_INITIAL_PARAMETERS, iterations=400)
    prequential = evaluate_prequential(
        normalized.records,
        model="bkt",
        train_fraction=0.5,
        bkt_parameters=FIT_INITIAL_PARAMETERS,
    )
    counts = Counter(record.concept_id for record in normalized.records)
    return {
        "syntheticOnly": True,
        "warning": "Synthetic data for UI and pipeline testing only; do not use it to set production BKT parameters.",
        "generation": {
            "seed": seed,
            "students": student_count,
            "storyId": story_id,
            "storyTitle": story_title,
            "level": "easy",
            "quizCapacities": {slot: capacity for slot, _mode, capacity in QUIZ_SLOTS},
            "questionsPerStudent": sum(capacity for _slot, _mode, capacity in QUIZ_SLOTS),
            "attempts": len(attempts),
            "responses": len(normalized.records),
            "uniqueVocabulary": len(words),
            "responsesPerWord": dict(sorted(counts.items())),
            "questionKinds": list(QUESTION_KINDS),
        },
        "generatingParameters": TRUE_PARAMETERS.to_dict(),
        "estimatedParametersFullData": fitted.to_dict(),
        "fullDataFit": score_records(normalized.records, fitted),
        "prequentialHalfSplit": {
            "parameters": prequential["parameters"],
            "trainResponses": prequential["train_n"],
            "evaluation": prequential["metrics"],
        },
        "dataQuality": normalized.counters,
        "bktEligibilityQuality": eligible_normalized.counters,
        "masteryByWord": mastery_summary(normalized.records, fitted, words, student_count),
    }


def render_markdown(report: dict[str, Any]) -> str:
    generation = report["generation"]
    true_params = report["generatingParameters"]
    fitted = report["estimatedParametersFullData"]
    prequential = report["prequentialHalfSplit"]
    rows = [
        "# Synthetic BKT pilot — 我們去喝下午茶",
        "",
        "> Synthetic data only. This report is for UI and analytics pipeline testing; it is not human-rated evidence and must not silently replace production defaults.",
        "",
        f"- Students: **{generation['students']}** (`fake-student-01` … `fake-student-{generation['students']:02d}`)",
        f"- Easy diagnostic questions per student: **{generation['questionsPerStudent']}** (20 + 22 + 25)",
        f"- Total response records: **{generation['responses']}**",
        f"- Unique vocabulary concepts: **{generation['uniqueVocabulary']}**",
        f"- Random seed: **{generation['seed']}**",
        "",
        "## BKT parameters",
        "",
        "| Parameter | Generating value | Estimated from all responses |",
        "|---|---:|---:|",
    ]
    labels = {
        "prior": "Prior mastery",
        "learn": "Learn rate",
        "guess": "Guess rate",
        "slip": "Slip rate",
    }
    for key, label in labels.items():
        rows.append(f"| {label} (`{key}`) | {true_params[key]:.4f} | {fitted[key]:.4f} |")
    rows.extend([
        "",
        "## Validation",
        "",
        f"- BKT-eligible responses after the repository validation gate: **{report['bktEligibilityQuality']['records_emitted']} / {generation['responses']}**",
        f"- Full-data sequential fit accuracy: **{report['fullDataFit']['accuracy']:.3f}**",
        f"- Full-data log loss: **{report['fullDataFit']['logLoss']:.4f}**",
        f"- Full-data Brier score: **{report['fullDataFit']['brierScore']:.4f}**",
        f"- Prequential evaluation responses: **{prequential['evaluation']['n']}** after a {prequential['trainResponses']}-response training prefix",
        f"- Prequential log loss: **{prequential['evaluation']['log_loss']:.4f}**",
        f"- Prequential Brier score: **{prequential['evaluation']['brier']:.4f}**",
        "",
        "## Interpretation",
        "",
        "The fitted values are a recovery check against the synthetic generator, not a calibrated recommendation. The production implementation currently uses engineering defaults of prior=0.20, learn=0.15, guess=0.20, and slip=0.10. Keep those values unchanged until real, approved student responses are collected and evaluated with the same eligibility gates.",
        "",
    ])
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--students", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument("--data-output", type=Path, default=Path(__file__).resolve().parent / "data" / "bkt_fake_our_story_25_students.json")
    parser.add_argument("--report-output", type=Path, default=Path(__file__).resolve().parent / "data" / "bkt_fake_our_story_report.md")
    args = parser.parse_args()
    if args.students < 1:
        parser.error("--students must be positive")

    story_id, story_title, words = load_story()
    attempts = generate_attempts(story_id, words, args.students, args.seed)
    report = build_report(story_id, story_title, words, attempts, args.seed, args.students)
    data = {
        "syntheticOnly": True,
        "generator": "backend/scripts/generate_bkt_fake_data.py",
        "seed": args.seed,
        "storyId": story_id,
        "storyTitle": story_title,
        "students": args.students,
        "attempts": attempts,
    }
    args.data_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.data_output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "dataOutput": str(args.data_output),
        "reportOutput": str(args.report_output),
        "estimatedParametersFullData": report["estimatedParametersFullData"],
        "generation": report["generation"],
        "dataQuality": report["dataQuality"],
        "bktEligibilityQuality": report["bktEligibilityQuality"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
