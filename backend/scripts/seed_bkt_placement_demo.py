"""A scoped, reproducible placement + diagnostic BKT demo on mandarin.

Preview: python -m scripts.seed_bkt_placement_demo
Write:   python -m scripts.seed_bkt_placement_demo --apply
Cleanup preview: python -m scripts.seed_bkt_placement_demo --cleanup
Cleanup write:   python -m scripts.seed_bkt_placement_demo --cleanup --apply

Uses only existing SIM001-SIM040. Answers go through the placement importer
and the normal published-assessment service. IDs carry the run marker;
repeating an unchanged run cannot add responses or observations.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import random
import re
import sys
from typing import Any

from analytics.learner_model.bkt.assessment_resolver import _accepted_answers, resolve_assessment_response
from analytics.learner_model.bkt.core import TYPED_QUESTION_TYPES
from analytics.learner_model.bkt.mastery import rebuild_student_vocabulary_mastery
from analytics.learner_model.srs import DAY_SECONDS
from api.schemas.models import VocabQuizAttemptRequest
from db import STUDENT_OWNED_TABLES, connect_db
from domain.vocabulary.assessment import normalize_answer
from scripts.import_placement_bkt_workbook import (
    EXPECTED_STUDENT_IDS, _existing_state, _grade, apply_import, build_import_plan, load_active_blueprint,
)
from services.vocab_quiz_attempt_service import record_attempt

RUN_ID = "bkt-demo-20260928"
SEED = 20260928
START_AT = datetime(2026, 9, 28, tzinfo=timezone.utc)
GENERATOR = {"prior": 0.35, "learn": 0.10, "guess": 0.25, "slip": 0.12,
             "guess_typed": 0.04, "slip_typed": 0.18}
KINDS = ("basic_meaning_mcq", "character_to_pinyin_typing", "context_cloze_mcq")
COHORT = list(EXPECTED_STUDENT_IDS)


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str,
                             separators=(",", ":")).encode()).hexdigest()


def _protected_data(db: Any) -> dict[str, str]:
    """Check every account and all non-cohort student-owned data in this snapshot."""
    result = {"students": _digest(db.execute("SELECT * FROM students ORDER BY id").fetchall())}
    for table in STUDENT_OWNED_TABLES:
        rows = db.execute(f"SELECT * FROM {table} WHERE student_id IS NULL OR NOT (student_id = ANY(%s))",
                          (COHORT,)).fetchall()
        result[table] = _digest(sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, default=str)))
    return result


def _answer(item: dict[str, Any], correct: bool, *, placement: bool = False) -> str:
    if placement:
        accepted = [str(value) for value in item.get("acceptedAnswers") or [item["correctAnswer"]]]
    else:
        kind = item["questionType"]
        _, accepted = _accepted_answers(item, f"tier{item['round']}", kind)
    if not accepted or not accepted[0]:
        raise ValueError(f"Empty canonical answer: {item['questionId']}")
    if correct:
        return accepted[0]
    accepted_normalized = {normalize_answer(value) for value in accepted}
    if item["questionType"] in TYPED_QUESTION_TYPES:
        return "bkt-demo-invalid-answer"
    wrong = next((str(value) for value in item.get("options") or []
                  if normalize_answer(str(value)) not in accepted_normalized), None)
    if wrong is None:
        raise ValueError(f"No canonical wrong MCQ option: {item['questionId']}")
    return wrong


def build_demo(db: Any, run_id: str) -> dict[str, Any]:
    db.execute("SELECT id FROM placement_test_blueprints WHERE id='active' FOR SHARE")
    blueprint = load_active_blueprint(db)
    questions = blueprint["questions"]
    words = [q["sourceWordId"] for q in questions]
    if len(words) != 28 or len(set(words)) != 28:
        raise ValueError("Demo requires 28 distinct blueprint words.")
    if any(q["questionType"] in TYPED_QUESTION_TYPES for q in questions):
        raise ValueError("Demo's specified 3360/1120 format split requires MCQ placement questions.")
    students = {row["id"]: row for row in db.execute(
        "SELECT id, name, is_test_account FROM students WHERE id = ANY(%s) FOR SHARE", (COHORT,),
    ).fetchall()}
    if set(students) != set(COHORT) or not all(row["is_test_account"] for row in students.values()):
        raise ValueError("All 40 existing SIM accounts must be marked test accounts.")
    if db.execute("SELECT 1 FROM vocab_research_participants WHERE student_id = ANY(%s) LIMIT 1", (COHORT,)).fetchone():
        raise ValueError("SIM demo accounts must not participate in a research study.")
    stories = {row["id"]: row for row in db.execute(
        "SELECT id, vocab_assessment, vocabulary_version FROM custom_stories "
        "WHERE published=TRUE AND id = ANY(%s) FOR SHARE",
        (sorted({q["sourceStoryId"] for q in questions}),),
    ).fetchall()}
    items: dict[tuple[str, int], dict[str, Any]] = {}
    for q in questions:
        story = stories.get(q["sourceStoryId"])
        if story is None:
            raise ValueError(f"Unpublished blueprint story: {q['sourceStoryId']}")
        for round_number, kind in enumerate(KINDS, start=1):
            candidates = [item for item in story["vocab_assessment"]
                          if item.get("wordId") == q["sourceWordId"]
                          and item.get("questionType") == kind and item.get("round") == round_number]
            if not candidates:
                raise ValueError(f"Missing published round {round_number}: {q['sourceWordId']}")
            items[q["sourceWordId"], round_number] = sorted(candidates, key=lambda item: item["questionId"])[0]
    prefix = run_id + ":"
    outside = db.execute(
        "SELECT count(*) AS n FROM vocab_quiz_responses WHERE student_id = ANY(%s) "
        "AND word_id = ANY(%s) AND left(quiz_id, %s) <> %s",
        (COHORT, words, len(prefix), prefix),
    ).fetchone()["n"]
    if outside:
        raise ValueError(f"Demo target histories already contain {outside} responses from another run.")

    rng = random.Random(SEED)
    outcomes: dict[tuple[str, str, int], bool] = {}
    for student_id in COHORT:
        for q in questions:
            word_id = q["sourceWordId"]
            known = rng.random() < GENERATOR["prior"]
            for position in range(4):
                kind = q["questionType"] if position == 0 else KINDS[position - 1]
                typed = kind in TYPED_QUESTION_TYPES
                guess = GENERATOR["guess_typed" if typed else "guess"]
                slip = GENERATOR["slip_typed" if typed else "slip"]
                outcomes[student_id, word_id, position] = rng.random() >= slip if known else rng.random() < guess
                if not known and rng.random() < GENERATOR["learn"]:
                    known = True

    rows = []
    for student_id in COHORT:
        for q in questions:
            correct = outcomes[student_id, q["sourceWordId"], 0]
            selected = _answer(q, correct, placement=True)
            if _grade(q, selected) != correct:
                raise ValueError(f"Placement grading mismatch: {q['questionId']}")
            rows.append({"student_id": student_id, "student_name": students[student_id]["name"],
                         "placement_session_id": f"{run_id}:placement:{student_id}",
                         "item_id": q["questionId"], "mode": q["tier"], "selected_answer": selected,
                         "source_story_id": q["sourceStoryId"], "time_ms": 800})
    placement = build_import_plan(rows, blueprint, imported_at=START_AT.isoformat())
    _existing_state(db, placement)  # Validate reruns during preview too.
    attempts = []
    for student_index, student_id in enumerate(COHORT):
        for round_number in range(1, 4):
            by_story: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for q in questions:
                by_story[q["sourceStoryId"]].append(q)
            for story_index, (story_id, group) in enumerate(sorted(by_story.items())):
                moment = START_AT + timedelta(hours=round_number, seconds=student_index * 30 + story_index * 30)
                attempt_id = f"{run_id}:{student_id}:tier{round_number}:{story_index:02d}"
                results = []
                for index, q in enumerate(group):
                    item = items[q["sourceWordId"], round_number]
                    correct = outcomes[student_id, q["sourceWordId"], round_number]
                    results.append({"word": item["targetWord"], "correct": correct, "timeMs": 800,
                                    "itemId": item["questionId"], "conceptId": item["wordId"],
                                    "questionKind": item["questionType"], "itemVersion": run_id,
                                    "selectedAnswer": _answer(item, correct), "presentedOptions": item.get("options") or [],
                                    "quizId": attempt_id, "answeredAt": (moment + timedelta(seconds=index)).isoformat()})
                attempt = VocabQuizAttemptRequest(
                    id=attempt_id, storyId=story_id, baseStoryId=story_id,
                    vocabularyVersion=stories[story_id]["vocabulary_version"],
                    studentName=students[student_id]["name"], mode=f"tier{round_number}", level=f"tier{round_number}",
                    completedAt=(moment + timedelta(seconds=len(results))).isoformat(),
                    totalQuestions=len(results), correctCount=sum(r["correct"] for r in results),
                    totalTimeMs=800 * len(results), questionResults=results,
                )
                for result in results:
                    resolved = resolve_assessment_response(db, attempt, result)
                    if not resolved.get("authoritativeResolved") or not resolved.get("isBktEligible") or resolved["correct"] != result["correct"]:
                        raise ValueError(f"Server grading/eligibility mismatch: {attempt_id}/{result['itemId']}")
                attempts.append((student_id, attempt, moment))
    return {"placement": placement, "attempts": attempts,
            "summary": {"runId": run_id, "seed": SEED, "generatorParameters": GENERATOR,
                        "blueprintRevision": blueprint["revision"], "students": 40, "words": 28,
                        "responses": 4480, "sequences": 1120, "observationsPerSequence": 4,
                        "mcq": 3360, "typed": 1120, "correct": sum(outcomes.values()),
                        "placementAttempts": 40, "diagnosticAttempts": len(attempts),
                        "planDigest": _digest([rows, [a.model_dump() for _, a, _ in attempts]])}}


def _run_counts(db: Any, run_id: str) -> dict[str, Any]:
    prefix = run_id + ":"
    return dict(db.execute(
        "SELECT count(*) AS responses, count(DISTINCT student_id) AS students, "
        "count(DISTINCT (student_id, word_id)) AS sequences, "
        "count(*) FILTER (WHERE evidence_origin <> 'synthetic' OR NOT bkt_eligible) AS invalid "
        "FROM vocab_quiz_responses WHERE left(quiz_id, %s) = %s", (len(prefix), prefix),
    ).fetchone())


def cleanup_demo(db: Any, run_id: str, apply: bool) -> dict[str, Any]:
    prefix = run_id + ":"
    rows = db.execute("SELECT * FROM vocab_quiz_responses WHERE left(quiz_id,%s)=%s",
                      (len(prefix), prefix)).fetchall()
    if any(row["student_id"] not in COHORT or row["evidence_origin"] != "synthetic" for row in rows):
        raise ValueError("Cleanup marker includes responses outside the synthetic SIM cohort.")
    attempts = db.execute("SELECT id, student_id, completed_at FROM vocab_quiz_attempts WHERE left(id,%s)=%s",
                          (len(prefix), prefix)).fetchall()
    placements = db.execute("SELECT id, student_id FROM placement_test_attempts WHERE left(id,%s)=%s",
                            (len(prefix), prefix)).fetchall()
    if any(a["student_id"] not in COHORT for a in [*attempts, *placements]):
        raise ValueError("Cleanup marker includes another student's attempt.")
    owners = sorted({r["student_id"] for r in rows} | {a["student_id"] for a in [*attempts, *placements]})
    accounts = db.execute("SELECT id, is_test_account FROM students WHERE id=ANY(%s) FOR SHARE", (owners,)).fetchall()
    if len(accounts) != len(owners) or any(not a["is_test_account"] for a in accounts):
        raise ValueError("Cleanup requires the original test accounts.")
    schedules = []
    moments = {datetime.fromisoformat(str(a["completed_at"]).replace("Z", "+00:00")) for a in attempts}
    for student_id, word_id in sorted({(r["student_id"], r["word_id"]) for r in rows}):
        events = db.execute("SELECT * FROM student_vocab_srs_events WHERE student_id=%s AND word_id=%s ORDER BY id",
                            (student_id, word_id)).fetchall()
        marked = [e for e in events if e["event_type"] == "enrollment" and e["occurred_at"] in moments]
        if not marked:
            continue
        if len(events) != 1 or db.execute(
            "SELECT 1 FROM vocab_quiz_responses WHERE student_id=%s AND word_id=%s AND left(quiz_id,%s)<>%s LIMIT 1",
            (student_id, word_id, len(prefix), prefix),
        ).fetchone():
            raise ValueError(f"Demo schedule subsequently used; refusing cleanup: {student_id}/{word_id}")
        schedules.append((student_id, word_id, marked[0]["id"]))
    result = {"runId": run_id, "applied": apply, "responses": len(rows), "diagnosticAttempts": len(attempts),
              "placementAttempts": len(placements), "demoSchedules": len(schedules)}
    if apply:
        for student_id, word_id, event_id in schedules:
            db.execute("DELETE FROM student_vocab_srs WHERE student_id=%s AND word_id=%s", (student_id, word_id))
            db.execute("DELETE FROM student_vocab_srs_events WHERE id=%s", (event_id,))
        db.execute("DELETE FROM vocab_quiz_responses WHERE left(quiz_id,%s)=%s", (len(prefix), prefix))
        db.execute("DELETE FROM vocab_quiz_attempts WHERE left(id,%s)=%s", (len(prefix), prefix))
        db.execute("DELETE FROM placement_test_attempts WHERE left(id,%s)=%s", (len(prefix), prefix))
        for student_id in sorted({r["student_id"] for r in rows}):
            rebuild_student_vocabulary_mastery(db, student_id)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Commit the seed or cleanup transaction.")
    parser.add_argument("--cleanup", action="store_true", help="Remove only this run's demo evidence.")
    parser.add_argument("--run-id", default=RUN_ID)
    args = parser.parse_args()
    if not re.fullmatch(r"bkt-demo-[A-Za-z0-9-]+", args.run_id) or len(args.run_id) > 60:
        parser.error("--run-id must match bkt-demo-[A-Za-z0-9-]+ and be at most 60 characters")
    with connect_db() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        if db.execute("SELECT current_database() AS name").fetchone()["name"] != "mandarin":
            raise ValueError("Demo may only use database mandarin.")
        if args.apply:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("mandarin:bkt-demo",))
            for student_id in COHORT:
                db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (student_id,))
        before = _protected_data(db)
        if args.cleanup:
            result = cleanup_demo(db, args.run_id, args.apply)
        else:
            plan = build_demo(db, args.run_id)
            result = {**plan["summary"], "applied": args.apply, "existing": _run_counts(db, args.run_id)}
            if args.apply:
                result["placementWrite"] = apply_import(db, plan["placement"])
                if result["placementWrite"]["created_students"]:
                    raise ValueError("Demo must not create accounts.")
                last_student = None
                for student_id, attempt, moment in plan["attempts"]:
                    if student_id != last_student:
                        print(f"Seeding {student_id}", file=sys.stderr, flush=True)
                        last_student = student_id
                    resolved = record_attempt(db, attempt, student_id, now=moment + timedelta(seconds=attempt.totalQuestions),
                                              day_seconds=DAY_SECONDS)
                    if len(resolved) != attempt.totalQuestions:
                        raise ValueError(f"Response count mismatch: {attempt.id}")
                result["actual"] = _run_counts(db, args.run_id)
                if result["actual"] != {"responses": 4480, "students": 40, "sequences": 1120, "invalid": 0}:
                    raise ValueError(f"Unexpected seeded counts: {result['actual']}")
                lengths = db.execute(
                    "SELECT count(*) AS n FROM vocab_quiz_responses WHERE left(quiz_id,%s)=%s "
                    "GROUP BY student_id,word_id HAVING count(*)<>4", (len(args.run_id + ':'), args.run_id + ':'),
                ).fetchall()
                if lengths:
                    raise ValueError("Seeded histories must each contain exactly four responses.")
        if before != _protected_data(db):
            raise ValueError("Another account or non-cohort data changed in this transaction.")
        result["otherDataUnchanged"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
