"""Admin Algorithm Verifier orchestration.

The mathematical endpoints compare production adapters with the independent
oracle in ``algorithm_verifier_reference``.  Integration runs use the normal
quiz attempt service with a reserved synthetic student and real published
assessment items, but are only available in development.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any

from psycopg.types.json import Jsonb

from analytics.learner_model.bkt.core import BKT_CONFIG, BKT_MODEL_VERSION, bkt_parameter_fingerprint, update_bkt_trace
from analytics.learner_model.bkt.mastery import get_vocabulary_mastery
from analytics.learner_model.review_queue import build_review_queue
from analytics.learner_model.srs import DAY_SECONDS, SrsState, enrollment_state, review
from analytics.learner_model.srs_store import load_srs_states
from api.schemas.models import VocabQuizAttemptRequest
from config import settings
from repositories.database import STUDENT_OWNED_TABLES
from services.algorithm_verifier_reference import bkt_sequence, bkt_step, sm2_enrollment, sm2_transition
from services.bkt_verification_golden import build_golden_report, golden_contract_status
from services.learning_engine_service import get_learning_engine_metadata
from services.vocab_quiz_attempt_service import record_attempt, record_response


INTEGRATION_RUN_ID = "algorithm-verifier-integration-001"
INTEGRATION_STUDENT_ID = "test-stu-verifier-integration-001"
FIXTURE_LESSON = 8
FIXTURE_SECTION = 3
FOCUS_WORD_IDS = ("C8-8-3-W203", "C8-8-3-W204", "C8-8-3-W205")
SUPPORT_WORD_IDS = ("C8-8-3-W206", "C8-8-3-W207", "C8-8-3-W208", "C8-8-3-W209")
BASE_TIME = datetime(2026, 8, 1, tzinfo=timezone.utc)


class AlgorithmVerifierError(Exception):
    pass


def _development_only() -> None:
    if settings.app_env.strip().lower() != "development":
        raise AlgorithmVerifierError("Persistent integration runs are available only in development.")


def _now(value: str | None = None) -> datetime:
    if not value:
        return BASE_TIME
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _fixture(db: Any) -> dict[str, Any]:
    row = db.execute(
        """
        SELECT id, title, lesson_number, lesson_sub_order, vocab_assessment, vocabulary_version
        FROM custom_stories
        WHERE published = TRUE AND lesson_number = %s AND lesson_sub_order = %s
        ORDER BY id
        LIMIT 1
        """,
        (FIXTURE_LESSON, FIXTURE_SECTION),
    ).fetchone()
    if not row:
        raise AlgorithmVerifierError("Published Lesson 8 reading fixture is unavailable.")
    assessment = [item for item in (row.get("vocab_assessment") or []) if isinstance(item, dict)]
    by_word = {str(item.get("wordId")): [] for item in assessment if item.get("wordId")}
    for item in assessment:
        if item.get("wordId") in by_word:
            by_word[str(item["wordId"])].append(item)
    expected = (*FOCUS_WORD_IDS, *SUPPORT_WORD_IDS)
    if set(by_word) != set(expected) or len(by_word) != 7:
        raise AlgorithmVerifierError("The published Lesson 8 reading fixture no longer has the expected seven-word pool.")
    for word_id in expected:
        rounds = {int(item.get("round")) for item in by_word[word_id] if str(item.get("round")).isdigit()}
        if rounds != {1, 2, 3}:
            raise AlgorithmVerifierError(f"Published fixture word {word_id} does not have rounds 1, 2, and 3.")
    revision_payload = json.dumps(assessment, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return {
        "storyId": row["id"],
        "vocabularyVersion": row["vocabulary_version"],
        "title": row.get("title"),
        "lesson": row.get("lesson_number"),
        "section": row.get("lesson_sub_order"),
        "revision": hashlib.sha256(revision_payload.encode("utf-8")).hexdigest(),
        "words": [
            {
                "wordId": word_id,
                "word": next(item.get("targetWord") for item in by_word[word_id] if item.get("targetWord")),
                "focus": word_id in FOCUS_WORD_IDS,
                "items": sorted(by_word[word_id], key=lambda item: int(item.get("round", 0))),
            }
            for word_id in expected
        ],
    }


def _ensure_verifier_student(db: Any) -> None:
    row = db.execute("SELECT id, is_test_account FROM students WHERE id = %s", (INTEGRATION_STUDENT_ID,)).fetchone()
    if row and not bool(row.get("is_test_account")):
        raise AlgorithmVerifierError(f"Reserved verifier student {INTEGRATION_STUDENT_ID} is not marked as a test account.")
    if row:
        return
    db.execute(
        "INSERT INTO students (id, name, password, is_test_account) VALUES (%s, %s, %s, TRUE)",
        (INTEGRATION_STUDENT_ID, "Algorithm Verifier Integration", "verifier-disabled-account"),
    )


def _write_run(
    db: Any,
    fixture: dict[str, Any],
    *,
    status: str,
    report: dict[str, Any],
    simulated_now: datetime,
    configuration: dict[str, Any] | None = None,
    step_position: int = 0,
) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT INTO algorithm_verifier_runs
            (id, student_id, fixture_story_id, fixture_revision, configuration,
             simulated_now, step_position, status, report, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            fixture_story_id = EXCLUDED.fixture_story_id,
            fixture_revision = EXCLUDED.fixture_revision,
            configuration = EXCLUDED.configuration,
            simulated_now = EXCLUDED.simulated_now,
            step_position = EXCLUDED.step_position,
            status = EXCLUDED.status,
            report = EXCLUDED.report,
            updated_at = EXCLUDED.updated_at
        """,
        (
            INTEGRATION_RUN_ID,
            INTEGRATION_STUDENT_ID,
            fixture["storyId"],
            fixture["revision"],
            Jsonb(configuration or {}),
            _iso(simulated_now),
            step_position,
            status,
            Jsonb(report),
            stamp,
            stamp,
        ),
    )


def _run_row(db: Any) -> dict[str, Any] | None:
    return db.execute("SELECT * FROM algorithm_verifier_runs WHERE id = %s", (INTEGRATION_RUN_ID,)).fetchone()


def _lock_run(db: Any) -> None:
    """Serialize reset/run and verifier-context writes for the reserved learner."""
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (INTEGRATION_RUN_ID,))


def _active_day_seconds() -> float:
    return settings.srs_day_seconds if settings.app_env.strip().lower() == "development" else DAY_SECONDS


def _at_day(base: datetime, day_seconds: float, days: float) -> datetime:
    return base + timedelta(seconds=day_seconds * days)


def _run_configuration() -> dict[str, Any]:
    return {
        "baseTime": _iso(BASE_TIME),
        "daySeconds": _active_day_seconds(),
        "lesson": FIXTURE_LESSON,
        "section": FIXTURE_SECTION,
        "focusWordIds": list(FOCUS_WORD_IDS),
        "supportWordIds": list(SUPPORT_WORD_IDS),
    }


def validate_verifier_context(db: Any, *, run_id: str, student_id: str, step: int) -> dict[str, Any]:
    """Validate the narrow context accepted by the two student write routes."""
    _development_only()
    if run_id != INTEGRATION_RUN_ID or student_id != INTEGRATION_STUDENT_ID:
        raise AlgorithmVerifierError("Verifier context must use the reserved integration run and student.")
    row = _run_row(db)
    if row is None or row.get("status") != "RUNNING":
        raise AlgorithmVerifierError("Verifier run is not active.")
    if int(row.get("step_position") or 0) != int(step):
        raise AlgorithmVerifierError("Verifier request step is stale or out of order.")
    return row


def lock_and_validate_verifier_context(db: Any, *, run_id: str, student_id: str, step: int) -> dict[str, Any]:
    _lock_run(db)
    return validate_verifier_context(db, run_id=run_id, student_id=student_id, step=step)


def advance_verifier_context(db: Any, *, step: int) -> None:
    db.execute(
        "UPDATE algorithm_verifier_runs SET step_position = %s, updated_at = %s WHERE id = %s AND status = 'RUNNING'",
        (int(step) + 1, datetime.now(timezone.utc).isoformat(), INTEGRATION_RUN_ID),
    )


def prepare_integration_requests(db: Any) -> dict[str, Any]:
    """Return deterministic request bodies for the published fixture.

    The Admin UI can use this payload to exercise the ordinary HTTP routes;
    the server still chooses the reserved student and validates every item.
    """
    fixture = _fixture(db)
    requests: list[dict[str, Any]] = []
    for round_number in (1, 2, 3):
        results = []
        for word in fixture["words"]:
            item = next(item for item in word["items"] if int(item["round"]) == round_number)
            results.append(_format_item(item, correct=not (word["wordId"] == "C8-8-3-W204" and round_number == 1)))
        requests.append({
            "step": len(requests),
            "mode": f"tier{round_number}",
            "attempt": _attempt(fixture, f"tier{round_number}", results, BASE_TIME, f"{INTEGRATION_RUN_ID}:tier{round_number}").model_dump(exclude_none=True),
        })
    return {
        "runId": INTEGRATION_RUN_ID,
        "studentId": INTEGRATION_STUDENT_ID,
        "headers": {
            "X-Algorithm-Verifier-Run": INTEGRATION_RUN_ID,
            "X-Algorithm-Verifier-Student": INTEGRATION_STUDENT_ID,
            "X-Algorithm-Verifier-Step": "<step>",
        },
        "requests": requests,
    }


def _format_item(item: dict[str, Any], *, correct: bool) -> dict[str, Any]:
    accepted = list(item.get("acceptedAnswers") or [])
    correct_answer = str(item.get("correctAnswer") or (accepted[0] if accepted else ""))
    options = [str(value) for value in item.get("options") or []]
    if correct:
        selected = accepted[0] if accepted else correct_answer
    elif item.get("answerFormat") == "free_text":
        selected = "verifier-invalid-answer"
    else:
        selected = next((value for value in options if value != correct_answer), "verifier-invalid-option")
    return {
        "word": item.get("targetWord"),
        "correct": bool(correct),
        "timeMs": 800,
        "itemId": item["questionId"],
        "conceptId": item["wordId"],
        "questionKind": item.get("questionType"),
        "round": item.get("round"),
        "tier": item.get("tier"),
        "level": item.get("tier"),
        "baseStoryId": None,
        "itemVersion": "verifier",
        "selectedAnswer": selected,
        "correctAnswer": correct_answer,
        "presentedOptions": options,
        "questionPrompt": item.get("prompt"),
    }


def _attempt(fixture: dict[str, Any], mode: str, results: list[dict[str, Any]], completed_at: datetime, attempt_id: str) -> VocabQuizAttemptRequest:
    return VocabQuizAttemptRequest(
        id=attempt_id,
        storyId=fixture["storyId"],
        baseStoryId=fixture["storyId"],
        vocabularyVersion=fixture.get("vocabularyVersion"),
        studentName="Algorithm Verifier Integration",
        mode=mode,
        level=mode,
        completedAt=_iso(completed_at) or "",
        totalQuestions=len(results),
        correctCount=sum(1 for result in results if result.get("correct")),
        totalTimeMs=sum(int(result.get("timeMs") or 0) for result in results),
        questionResults=results,
    )


def _snapshot(db: Any, fixture: dict[str, Any], now: datetime) -> dict[str, Any]:
    mastery = get_vocabulary_mastery(db, INTEGRATION_STUDENT_ID, story_id=fixture["storyId"])
    by_id = {row["wordId"]: row for row in mastery}
    states = load_srs_states(db, INTEGRATION_STUDENT_ID, list(by_id))
    queue = build_review_queue(db, INTEGRATION_STUDENT_ID, {"storyId": fixture["storyId"], "includeAllWeak": True}, now=now)
    queue_by_id = {row["wordId"]: row for row in queue.get("queue", [])}
    words = []
    for word in fixture["words"]:
        row = by_id.get(word["wordId"], {})
        state = states.get(word["wordId"])
        vocabulary_state = row.get("vocabularyState") or {}
        words.append({
            "wordId": word["wordId"],
            "word": word["word"],
            "focus": word["focus"],
            "pLearned": row.get("pLearned", BKT_CONFIG.initial_mastery),
            "observationCount": row.get("observationCount", 0),
            "bktStatus": (vocabulary_state.get("bkt") or {}).get("status"),
            "masteryStatus": (vocabulary_state.get("review") or {}).get("status"),
            "practice": vocabulary_state.get("practice"),
            "schedule": None if state is None else {
                "reps": state.reps,
                "intervalDays": state.interval_days,
                "ease": state.ease,
                "dueOn": _iso(state.due_on),
                "lastReviewedOn": _iso(state.last_reviewed_on),
            },
            "queueReason": (queue_by_id.get(word["wordId"]) or {}).get("reviewReason"),
        })
    return {"timestamp": _iso(now), "diagnostic": queue.get("diagnostic"), "words": words, "queue": queue.get("queue", [])}


def get_bootstrap(db: Any) -> dict[str, Any]:
    fixture_error = None
    fixture = None
    try:
        fixture = _fixture(db)
    except AlgorithmVerifierError as exc:
        fixture_error = str(exc)
    metadata = get_learning_engine_metadata()
    sm2_suite = build_sm2_baseline_report()
    bkt_suite = build_golden_report()
    integration_ready = (
        settings.app_env.strip().lower() == "development"
        and bkt_suite["summary"]["passed"] == bkt_suite["summary"]["total"]
        and sm2_suite["result"] == "PASS"
        and fixture is not None
    )
    return {
        "model": metadata.get("bkt") or {},
        "golden": bkt_suite,
        "contractStatus": golden_contract_status(),
        "sm2": metadata.get("sm2") or metadata.get("retention") or {},
        "baselineSuites": {
            "bkt": "PASS" if bkt_suite["summary"]["passed"] == bkt_suite["summary"]["total"] else "FAIL",
            "sm2": sm2_suite["result"],
        },
        "integration": {
            "enabled": integration_ready,
            "studentId": INTEGRATION_STUDENT_ID,
            "runId": INTEGRATION_RUN_ID,
            "fixture": fixture,
            "fixtureError": fixture_error,
        },
    }


def build_sm2_baseline_report() -> dict[str, Any]:
    """Run a compact independent suite before enabling integration mutations."""
    now = BASE_TIME
    checks: list[dict[str, Any]] = []
    state = enrollment_state(now, day_seconds=DAY_SECONDS)
    expected = sm2_enrollment(now=now, day_seconds=DAY_SECONDS)
    checks.append({"name": "enrollment", "passed": state.reps == expected["repetitions"] and state.interval_days == expected["intervalDays"] and state.ease == expected["ease"] and state.due_on == expected["nextDue"]})
    transition = calculate_sm2({"repetitions": 1, "intervalDays": 1, "ease": 2.5, "quality": 4, "now": _iso(now), "daySeconds": DAY_SECONDS})
    checks.append({"name": "second success", "passed": transition["result"] == "PASS" and transition["production"]["intervalDays"] == 6})
    failure = calculate_sm2({"repetitions": 2, "intervalDays": 6, "ease": 2.5, "quality": 2, "now": _iso(now), "daySeconds": DAY_SECONDS})
    checks.append({"name": "failure reset", "passed": failure["result"] == "PASS" and failure["production"]["repetitions"] == 0})
    return {"result": "PASS" if all(check["passed"] for check in checks) else "FAIL", "checks": checks, "tolerance": 1e-9}


def calculate_bkt(payload: dict[str, Any]) -> dict[str, Any]:
    prior = float(payload.get("prior", BKT_CONFIG.initial_mastery))
    correct = bool(payload.get("correct"))
    question_format = str(payload.get("questionFormat", "mcq")).lower()
    default_guess = BKT_CONFIG.guess_rate_typed if question_format == "typed" else BKT_CONFIG.guess_rate
    default_slip = BKT_CONFIG.slip_rate_typed if question_format == "typed" else BKT_CONFIG.slip_rate
    learn_rate = float(payload.get("learnRate", BKT_CONFIG.learn_rate))
    guess = float(payload.get("guess", default_guess))
    slip = float(payload.get("slip", default_slip))
    observations = payload.get("observations")
    if isinstance(observations, list) and observations:
        production_trace: list[dict[str, Any]] = []
        current = prior
        for observation in observations:
            item = observation if isinstance(observation, dict) else {}
            item_format = str(item.get("questionFormat") or item.get("questionType") or "mcq").lower()
            item_guess = float(item.get("guess", guess if item_format not in {"typed", "character_to_pinyin_typing"} else BKT_CONFIG.guess_rate_typed))
            item_slip = float(item.get("slip", slip if item_format not in {"typed", "character_to_pinyin_typing"} else BKT_CONFIG.slip_rate_typed))
            step = update_bkt_trace(current, bool(item.get("correct")), learn_rate=learn_rate, guess=item_guess, slip=item_slip)
            production_trace.append({"questionFormat": item_format, "correct": bool(item.get("correct")), **step})
            current = step["resultingMastery"]
        reference_trace = bkt_sequence(
            observations,
            initial_mastery=prior,
            learn_rate=learn_rate,
            mcq_guess=guess if question_format != "typed" else BKT_CONFIG.guess_rate,
            mcq_slip=slip if question_format != "typed" else BKT_CONFIG.slip_rate,
            typed_guess=BKT_CONFIG.guess_rate_typed,
            typed_slip=BKT_CONFIG.slip_rate_typed,
        )
        difference = abs(production_trace[-1]["resultingMastery"] - reference_trace[-1]["resultingMastery"])
        tolerance = float(payload.get("tolerance", 0.001))
        return {
            "inputs": {"prior": prior, "observations": observations, "learnRate": learn_rate, "tolerance": tolerance},
            "production": {"trace": production_trace, "resultingMastery": production_trace[-1]["resultingMastery"]},
            "reference": {"trace": reference_trace, "resultingMastery": reference_trace[-1]["resultingMastery"]},
            "difference": difference,
            "tolerance": tolerance,
            "result": "PASS" if difference <= tolerance else "FAIL",
            "formula": {"observation": "posterior = numerator / denominator for each response", "transition": f"P(L)' = posterior + (1 - posterior) * {learn_rate:.6f}"},
            "model": {"version": BKT_MODEL_VERSION, "parameterFingerprint": bkt_parameter_fingerprint(BKT_CONFIG)},
        }
    production = update_bkt_trace(prior, correct, learn_rate=learn_rate, guess=guess, slip=slip)
    reference = bkt_step(prior, correct, learn_rate=learn_rate, guess=guess, slip=slip)
    difference = abs(production["resultingMastery"] - reference["resultingMastery"])
    tolerance = float(payload.get("tolerance", 0.001))
    return {
        "inputs": {"prior": prior, "correct": correct, "questionFormat": question_format, "learnRate": learn_rate, "guess": guess, "slip": slip},
        "production": production,
        "reference": reference,
        "difference": difference,
        "tolerance": tolerance,
        "result": "PASS" if difference <= tolerance else "FAIL",
        "formula": {
            "observation": f"{prior:.6f} * {'1 - slip' if correct else 'slip'} / posterior denominator",
            "transition": f"posterior + (1 - posterior) * {learn_rate:.6f}",
        },
        "model": {"version": BKT_MODEL_VERSION, "parameterFingerprint": bkt_parameter_fingerprint(BKT_CONFIG)},
    }


def calculate_sm2(payload: dict[str, Any]) -> dict[str, Any]:
    now = _now(payload.get("now"))
    day_seconds = float(payload.get("daySeconds", _active_day_seconds()))
    if str(payload.get("operation", "review")).lower() == "enroll":
        production_state = enrollment_state(now, day_seconds=day_seconds)
        reference = sm2_enrollment(now=now, day_seconds=day_seconds)
        production = {
            "repetitions": production_state.reps,
            "intervalDays": production_state.interval_days,
            "ease": production_state.ease,
            "nextDue": _iso(production_state.due_on),
            "lastReviewedOn": _iso(production_state.last_reviewed_on),
        }
        expected = {**reference, "nextDue": _iso(reference["nextDue"]), "lastReviewedOn": _iso(reference["lastReviewedOn"])}
        differences = {
            "repetitions": production["repetitions"] - expected["repetitions"],
            "intervalDays": production["intervalDays"] - expected["intervalDays"],
            "ease": abs(production["ease"] - expected["ease"]),
            "nextDue": production["nextDue"] != expected["nextDue"],
            "lastReviewedOn": production["lastReviewedOn"] != expected["lastReviewedOn"],
        }
        passed = differences["repetitions"] == 0 and differences["intervalDays"] == 0 and differences["ease"] <= 1e-9 and not differences["nextDue"] and not differences["lastReviewedOn"]
        return {
            "inputs": {**payload, "operation": "enroll", "now": _iso(now), "daySeconds": day_seconds},
            "production": production,
            "reference": expected,
            "difference": differences,
            "rawInterval": None,
            "result": "PASS" if passed else "FAIL",
            "qualityMapping": {"correct": 4, "wrong": 2},
        }
    quality = int(payload.get("quality", 4))
    state = SrsState(
        reps=int(payload.get("repetitions", 0)),
        interval_days=int(payload.get("intervalDays", 0)),
        ease=float(payload.get("ease", 2.5)),
        due_on=_now(payload["dueOn"]) if payload.get("dueOn") else None,
        last_reviewed_on=_now(payload["lastReviewedOn"]) if payload.get("lastReviewedOn") else None,
    )
    production_state = review(state, quality, now, day_seconds=day_seconds)
    reference = sm2_transition(
        repetitions=state.reps,
        interval_days=state.interval_days,
        ease=state.ease,
        quality=quality,
        now=now,
        day_seconds=day_seconds,
    )
    production = {"repetitions": production_state.reps, "intervalDays": production_state.interval_days, "ease": production_state.ease, "nextDue": _iso(production_state.due_on)}
    expected = {**reference, "nextDue": _iso(reference["nextDue"])}
    differences = {
        "repetitions": production["repetitions"] - expected["repetitions"],
        "intervalDays": production["intervalDays"] - expected["intervalDays"],
        "ease": abs(production["ease"] - expected["ease"]),
        "nextDue": production["nextDue"] != expected["nextDue"],
    }
    passed = differences["repetitions"] == 0 and differences["intervalDays"] == 0 and differences["ease"] <= 1e-9 and not differences["nextDue"]
    return {"inputs": {**payload, "now": _iso(now), "daySeconds": day_seconds}, "production": production, "reference": expected, "difference": differences, "rawInterval": reference.get("rawInterval"), "result": "PASS" if passed else "FAIL", "qualityMapping": {"correct": 4, "wrong": 2}}


def _run_diagnostic(db: Any, fixture: dict[str, Any], round_number: int, now: datetime) -> None:
    results: list[dict[str, Any]] = []
    for word in fixture["words"]:
        item = next(item for item in word["items"] if int(item["round"]) == round_number)
        correct = not (word["wordId"] == "C8-8-3-W204" and round_number == 1)
        result = _format_item(item, correct=correct)
        result["quizId"] = f"{INTEGRATION_RUN_ID}:tier{round_number}"
        results.append(result)
    attempt = _attempt(fixture, f"tier{round_number}", results, now, f"{INTEGRATION_RUN_ID}:tier{round_number}")
    if round_number == 1:
        partial = _attempt(fixture, "tier1", results[:1], now, f"{INTEGRATION_RUN_ID}:tier1-partial")
        record_response(db, partial, INTEGRATION_STUDENT_ID, now=now, day_seconds=_active_day_seconds(), evidence_origin="synthetic")
    record_attempt(db, attempt, INTEGRATION_STUDENT_ID, now=now, day_seconds=_active_day_seconds(), evidence_origin="synthetic")


def _run_single(db: Any, fixture: dict[str, Any], *, word_id: str, round_number: int, mode: str, correct: bool, now: datetime, suffix: str) -> None:
    word = next(word for word in fixture["words"] if word["wordId"] == word_id)
    item = next(item for item in word["items"] if int(item["round"]) == round_number)
    result = _format_item(item, correct=correct)
    result["quizId"] = f"{INTEGRATION_RUN_ID}:{suffix}"
    attempt = _attempt(fixture, mode, [result], now, f"{INTEGRATION_RUN_ID}:{suffix}")
    record_attempt(db, attempt, INTEGRATION_STUDENT_ID, now=now, day_seconds=_active_day_seconds(), evidence_origin="synthetic")


def run_integration(db: Any) -> dict[str, Any]:
    _development_only()
    _lock_run(db)
    _ensure_verifier_student(db)
    fixture = _fixture(db)
    existing = _run_row(db)
    if existing and existing.get("status") == "COMPLETE":
        raise AlgorithmVerifierError("Reset verifier data before starting another integration run.")
    _write_run(db, fixture, status="RUNNING", report={}, simulated_now=BASE_TIME, configuration=_run_configuration(), step_position=0)
    day_seconds = _active_day_seconds()
    before = _snapshot(db, fixture, BASE_TIME)
    steps: list[dict[str, Any]] = []
    for round_number in (1, 2, 3):
        _run_diagnostic(db, fixture, round_number, BASE_TIME)
        steps.append({"id": f"diagnostic-tier{round_number}", "label": f"Diagnostic tier {round_number}", "state": _snapshot(db, fixture, BASE_TIME)})
    after_diagnostic = steps[-1]["state"]
    practice_old_one = BASE_TIME + timedelta(seconds=10)
    _run_single(db, fixture, word_id="C8-8-3-W204", round_number=1, mode="weak_words", correct=True, now=practice_old_one, suffix="practice-old-1")
    steps.append({"id": "practice-old-one", "label": "One corrective success for 老", "state": _snapshot(db, fixture, practice_old_one)})
    practice_old_two = BASE_TIME + timedelta(seconds=20)
    _run_single(db, fixture, word_id="C8-8-3-W204", round_number=1, mode="weak_words", correct=True, now=practice_old_two, suffix="practice-old-2")
    steps.append({"id": "practice-old-two", "label": "Second corrective success and enrollment for 老", "state": _snapshot(db, fixture, practice_old_two)})
    practice_young = BASE_TIME + timedelta(seconds=30)
    _run_single(db, fixture, word_id="C8-8-3-W203", round_number=2, mode="weak_words", correct=True, now=practice_young, suffix="practice-young-typed")
    steps.append({"id": "practice-young-typed", "label": "Practice 年輕 without advancing SM-2", "state": _snapshot(db, fixture, practice_young)})
    review_young_correct = _at_day(BASE_TIME, day_seconds, 1)
    _run_single(db, fixture, word_id="C8-8-3-W203", round_number=1, mode="maintenance_review", correct=True, now=review_young_correct, suffix="review-young-correct")
    steps.append({"id": "review-young-correct", "label": "Due review correct: 年輕", "state": _snapshot(db, fixture, review_young_correct)})
    review_young_wrong = _at_day(BASE_TIME, day_seconds, 7)
    _run_single(db, fixture, word_id="C8-8-3-W203", round_number=1, mode="maintenance_review", correct=False, now=review_young_wrong, suffix="review-young-wrong")
    after_failed_review = _at_day(BASE_TIME, day_seconds, 8)
    steps.append({"id": "review-young-wrong", "label": "Due review wrong: 年輕", "state": _snapshot(db, fixture, after_failed_review)})
    report = {
        "runId": INTEGRATION_RUN_ID,
        "studentId": INTEGRATION_STUDENT_ID,
        "fixture": fixture,
        "baseTime": _iso(BASE_TIME),
        "daySeconds": day_seconds,
        "before": before,
        "afterDiagnostic": after_diagnostic,
        "steps": steps,
        "completed": True,
        "traceability": {"studentId": INTEGRATION_STUDENT_ID, "wordIds": [word["wordId"] for word in fixture["words"]], "timestamp": _iso(datetime.now(timezone.utc))},
    }
    _write_run(db, fixture, status="COMPLETE", report=report, simulated_now=after_failed_review, configuration=_run_configuration(), step_position=len(steps))
    return report


def reset_integration(db: Any) -> dict[str, Any]:
    _development_only()
    _lock_run(db)
    fixture = _fixture(db)
    _ensure_verifier_student(db)
    for table in (*STUDENT_OWNED_TABLES,):
        db.execute(f"DELETE FROM {table} WHERE student_id = %s", (INTEGRATION_STUDENT_ID,))
    db.execute("DELETE FROM algorithm_verifier_runs WHERE id = %s", (INTEGRATION_RUN_ID,))
    _write_run(db, fixture, status="READY", report={}, simulated_now=BASE_TIME, configuration=_run_configuration(), step_position=0)
    return {"status": "READY", "studentId": INTEGRATION_STUDENT_ID, "fixture": fixture}


def get_integration(db: Any) -> dict[str, Any]:
    fixture = _fixture(db)
    row = _run_row(db)
    sm2_suite = build_sm2_baseline_report()
    bkt_suite = build_golden_report()
    return {
        "enabled": (
            settings.app_env.strip().lower() == "development"
            and fixture is not None
            and bkt_suite["summary"]["passed"] == bkt_suite["summary"]["total"]
            and sm2_suite["result"] == "PASS"
        ),
        "studentId": INTEGRATION_STUDENT_ID,
        "runId": INTEGRATION_RUN_ID,
        "fixture": fixture,
        "status": row.get("status") if row else "NOT_INITIALIZED",
        "report": row.get("report") if row else None,
        "simulatedNow": row.get("simulated_now") if row else None,
        "stepPosition": int(row.get("step_position") or 0) if row else 0,
    }
