"""Read-only BKT contract and live-replay verification for administrators.

The golden side deliberately uses versioned constants and a small reference
implementation rather than calling the production BKT updater. This keeps a
regression in production replay observable instead of making both sides fail
or pass together.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from analytics.learner_model.bkt.core import (
    BKT_CONFIG,
    BKT_MODEL_VERSION,
    bkt_parameter_fingerprint,
    guess_slip_for,
)
from analytics.learner_model.bkt.mastery import (
    get_vocabulary_mastery,
    mastery_trace_for_word,
)
from analytics.learner_model.bkt.placement_prior import (
    PLACEMENT_PRIOR_SHRINKAGE_K,
    compute_chapter_placement_priors,
    get_published_word_chapters,
    initial_priors_by_word,
    is_placement_response,
)
from repositories import bkt_verification_repository as repo
from services.bkt_verification_golden import (
    GOLDEN_FIXTURE_VERSION,
    GOLDEN_TOLERANCE,
    build_golden_report,
    golden_contract_status,
)


class BktVerificationNotFound(Exception):
    """Raised when an admin asks for a student or word that is not available."""


def _model_metadata() -> dict[str, Any]:
    return {
        "version": BKT_MODEL_VERSION,
        "parameterFingerprint": bkt_parameter_fingerprint(BKT_CONFIG),
        "parameters": {
            "pL0": BKT_CONFIG.initial_mastery,
            "pT": BKT_CONFIG.learn_rate,
            "mcqGuess": BKT_CONFIG.guess_rate,
            "mcqSlip": BKT_CONFIG.slip_rate,
            "typedGuess": BKT_CONFIG.guess_rate_typed,
            "typedSlip": BKT_CONFIG.slip_rate_typed,
            "masteryThreshold": BKT_CONFIG.mastery_threshold,
            "minimumObservations": BKT_CONFIG.minimum_observations,
        },
        "contractStatus": golden_contract_status(),
        "goldenFixtureVersion": GOLDEN_FIXTURE_VERSION,
    }

def get_bootstrap(db: Any) -> dict[str, Any]:
    return {
        "model": _model_metadata(),
        "golden": build_golden_report(),
        "students": [
            {
                "studentId": row["id"],
                "name": row["name"],
                "status": row.get("status") or "active",
                "isTestAccount": bool(row.get("is_test_account")),
            }
            for row in repo.list_students(db)
        ],
    }


def _dedupe_history(rows: Iterable[dict[str, Any]], word_id: str) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    seen_exposures: set[tuple[str, str]] = set()
    for row in rows:
        if row["word_id"] != word_id:
            continue
        exposure_id = row.get("diagnostic_exposure_id")
        if row.get("bkt_eligible") and exposure_id:
            key = (str(row["item_id"]), str(exposure_id))
            if key in seen_exposures:
                continue
            seen_exposures.add(key)
        history.append(row)
    return history


def _provenance(rows: Iterable[dict[str, Any]]) -> str:
    origins = {str(row.get("evidence_origin") or "UNKNOWN").upper() for row in rows}
    if not origins:
        return "NONE"
    if len(origins) == 1:
        return next(iter(origins))
    return "MIXED"


def _activity_label(row: dict[str, Any]) -> str:
    return {
        "diagnostic": "Placement" if str(row.get("diagnostic_exposure_id") or "").startswith("placement:") else "Diagnostic",
        "personalized_practice": "Personalized Practice",
        "scheduled_maintenance": "Maintenance Review",
    }.get(str(row.get("activity_type") or ""), str(row.get("activity_type") or "Practice"))


def _placement_prior_detail(
    db: Any,
    student_id: str,
    word_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    word_chapters = get_published_word_chapters(db, [word_id])
    chapter = word_chapters.get(word_id)
    chapter_priors = compute_chapter_placement_priors(rows, BKT_CONFIG)
    applied = initial_priors_by_word(db, student_id, word_chapters, BKT_CONFIG).get(word_id)
    if applied is None or chapter is None or chapter not in chapter_priors:
        return {
            "source": "Global BKT prior",
            "pL0": BKT_CONFIG.initial_mastery,
        }
    chapter_rows = [row for row in rows if is_placement_response(row) and row.get("chapter") == chapter]
    correct_count = sum(1 for row in chapter_rows if row.get("correct"))
    count = len(chapter_rows)
    raw_score = correct_count / count if count else None
    weight = count / (count + PLACEMENT_PRIOR_SHRINKAGE_K) if count else None
    return {
        "source": "Placement Chapter Prior",
        "chapter": chapter,
        "placementResult": f"{correct_count} / {count}",
        "rawScore": raw_score,
        "shrinkageWeight": weight,
        "globalPrior": BKT_CONFIG.initial_mastery,
        "pL0": applied,
    }


def _format_evidence(row: dict[str, Any], order: int) -> dict[str, Any]:
    timestamp = row.get("occurred_at") or row.get("occurred_at_utc")
    return {
        "order": order,
        "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp,
        "activityType": _activity_label(row),
        "quizMode": row.get("quiz_mode"),
        "questionType": row.get("question_type"),
        "correct": bool(row.get("correct")),
        "selectedAnswer": row.get("selected_answer"),
        "correctAnswer": row.get("correct_answer"),
        "word": row.get("word"),
        "evidenceOrigin": str(row.get("evidence_origin") or "UNKNOWN").upper(),
        "resolver": row.get("resolver_version"),
        "itemId": row.get("item_id"),
        "technical": {
            "responseId": row.get("id"),
            "quizId": row.get("quiz_id"),
            "attemptId": row.get("attempt_id"),
            "diagnosticExposureId": row.get("diagnostic_exposure_id"),
            "bktEligible": bool(row.get("bkt_eligible")),
            "lessonId": row.get("lesson_id"),
            "chapter": row.get("chapter"),
        },
    }


def _build_presets(words: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_word: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_word[str(row["word_id"])].append(row)
    presets: list[dict[str, Any]] = []
    for preset_id, label, wanted in (
        ("placement-correct", "Placement correct word", True),
        ("placement-incorrect", "Placement incorrect word", False),
    ):
        match = next(
            (
                word for word in words
                if any(is_placement_response(row) and bool(row.get("correct")) is wanted for row in by_word.get(word["wordId"], []))
            ),
            None,
        )
        if match:
            presets.append({"id": preset_id, "label": label, "wordId": match["wordId"]})
    unseen = next((word for word in words if not by_word.get(word["wordId"])), None)
    if unseen:
        presets.append({"id": "unseen-word", "label": "Unseen word", "wordId": unseen["wordId"]})
    return presets


def get_trace(db: Any, student_id: str, word_id: str | None = None) -> dict[str, Any]:
    student = repo.get_student(db, student_id)
    if not student:
        raise BktVerificationNotFound("Student was not found.")
    rows = repo.list_bkt_response_rows(db, student_id)
    mastery = get_vocabulary_mastery(db, student_id, BKT_CONFIG)
    words = [
        {
            "wordId": row["wordId"],
            "word": row["word"],
            "meaning": row.get("meaning"),
            "lessonId": row.get("lessonId"),
            "pLearned": row["pLearned"],
            "observationCount": row["observationCount"],
            "status": row["vocabularyState"]["bkt"]["status"],
            "reviewStatus": row["vocabularyState"]["review"]["status"],
        }
        for row in mastery
    ]
    if not words:
        return {
            "student": {"studentId": student["id"], "name": student["name"], "isTestAccount": bool(student.get("is_test_account"))},
            "words": [],
            "presets": [],
            "selectedWordId": None,
            "trace": None,
            "model": _model_metadata(),
        }
    selected_id = word_id or words[0]["wordId"]
    selected_word = next((word for word in words if word["wordId"] == selected_id), None)
    if not selected_word:
        raise BktVerificationNotFound("Word was not found in the selected student's vocabulary pool.")
    history = _dedupe_history(rows, selected_id)
    current = next(row for row in mastery if row["wordId"] == selected_id)
    word_chapters = get_published_word_chapters(db, [selected_id])
    initial_priors = initial_priors_by_word(db, student_id, word_chapters, BKT_CONFIG)
    initial_mastery = (
        BKT_CONFIG.initial_mastery
        if any(is_placement_response(row) for row in history)
        else initial_priors.get(selected_id, BKT_CONFIG.initial_mastery)
    )
    reference_observations = [
        {"correct": bool(row["correct"]), "questionType": row.get("question_type")}
        for row in history
    ]
    expected_trace = _reference_trace(reference_observations, initial_mastery)
    production_trace = mastery_trace_for_word(db, student_id, selected_id, BKT_CONFIG)
    actual_trace = _production_trace_with_rows(history, production_trace, initial_mastery)
    expected_final = expected_trace[-1]["resultingMastery"] if expected_trace else initial_mastery
    actual_final = float(current["pLearned"])
    expected_status = _reference_status(len(history), expected_final)
    actual_status = current["vocabularyState"]["bkt"]["status"]
    comparison = {
        "observationCount": {"expected": len(history), "actual": int(current["observationCount"])},
        "pLearned": {"expected": expected_final, "actual": actual_final},
        "status": {"expected": expected_status, "actual": actual_status},
    }
    verification = (
        "PASS"
        if comparison["observationCount"]["expected"] == comparison["observationCount"]["actual"]
        and abs(comparison["pLearned"]["expected"] - comparison["pLearned"]["actual"]) <= GOLDEN_TOLERANCE
        and comparison["status"]["expected"] == comparison["status"]["actual"]
        else "FAIL"
    )
    return {
        "student": {
            "studentId": student["id"],
            "name": student["name"],
            "isTestAccount": bool(student.get("is_test_account")),
        },
        "words": words,
        "presets": _build_presets(words, rows),
        "selectedWordId": selected_id,
        "model": _model_metadata(),
        "trace": {
            "word": selected_word,
            "evidence": [_format_evidence(row, index) for index, row in enumerate(history, start=1)],
            "evidenceCount": len(history),
            "provenance": _provenance(history),
            "syntheticTestData": bool(student.get("is_test_account")) or _provenance(history) == "SYNTHETIC",
            "coldStart": _placement_prior_detail(db, student_id, selected_id, rows),
            "expectedTrace": expected_trace,
            "actualTrace": actual_trace,
            "comparison": comparison,
            "verification": verification,
            "reviewStatus": current["vocabularyState"]["review"]["status"],
        },
    }


def _production_trace_with_rows(
    rows: list[dict[str, Any]],
    production_trace: list[dict[str, Any]],
    initial_mastery: float,
) -> list[dict[str, Any]]:
    actual: list[dict[str, Any]] = []
    prior = initial_mastery
    for index, (row, production_step) in enumerate(zip(rows, production_trace), start=1):
        guess, slip = guess_slip_for(row.get("question_type"), BKT_CONFIG)
        if row["correct"]:
            numerator = prior * (1.0 - slip)
            denominator = numerator + (1.0 - prior) * guess
        else:
            numerator = prior * slip
            denominator = numerator + (1.0 - prior) * (1.0 - guess)
        posterior = numerator / denominator if denominator else prior
        actual.append({
            "step": index,
            "prior": prior,
            "observation": "Correct" if row["correct"] else "Incorrect",
            "correct": bool(row["correct"]),
            "questionType": row.get("question_type"),
            "guess": guess,
            "slip": slip,
            "posterior": posterior,
            "learningTransition": BKT_CONFIG.learn_rate,
            "resultingMastery": float(production_step["pLearned"]),
        })
        prior = float(production_step["pLearned"])
    return actual
