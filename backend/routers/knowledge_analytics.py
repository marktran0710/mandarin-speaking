"""Admin-only PFA/BKT pilot analytics for vocabulary quiz responses."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

import auth
from analytics.knowledge_tracing import (
    BKT,
    BKTParameters,
    PFA,
    PFAParameters,
    evaluate_prequential,
    normalize_vocab_attempts,
    ResponseRecord,
)
from database import connect_db
from analytics.bkt_question_validation import analyze_response_quality, validate_bkt_diagnostic_design
from scripts.export_quiz_questions import build_question_rows


router = APIRouter(
    prefix="/api/admin/analytics",
    tags=["admin-analytics"],
    dependencies=[Depends(auth.require_admin)],
)

MODEL_VERSION = "knowledge-pilot-v1"
MIN_PREDICTIONS_FOR_WINNER = 10
MODEL_SELECTION_TIE_MARGIN = 0.01


def _attempt_row_to_dict(row: Any) -> dict[str, Any]:
    """Keep the analytics input compatible with the shared normalizer."""
    return {
        "id": row.get("id"),
        "storyId": row.get("story_id"),
        "studentId": row.get("student_id"),
        "studentName": row.get("student_name"),
        "mode": row.get("mode"),
        "completedAt": row.get("completed_at"),
        "questionResults": row.get("question_results") or [],
    }


def _load_attempts(
    student_id: Optional[str], story_id: Optional[str], level: Optional[str]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    query = (
        "SELECT id, story_id, student_id, student_name, mode, completed_at, question_results "
        "FROM vocab_quiz_attempts WHERE 1=1"
    )
    params: list[Any] = []
    if student_id:
        query += " AND student_id = %s"
        params.append(student_id)
    if story_id:
        query += " AND story_id = %s"
        params.append(story_id)
    query += " ORDER BY completed_at ASC, id ASC"

    with connect_db() as db:
        rows = db.execute(query, params).fetchall()

    attempts: list[dict[str, Any]] = []
    names: dict[str, str] = {}
    for row in rows:
        attempt = _attempt_row_to_dict(row)
        results = attempt["questionResults"]
        if level:
            results = [
                result for result in results
                if isinstance(result, dict) and result.get("level") == level
            ]
            attempt["questionResults"] = results
        attempts.append(attempt)
        row_student_id = row.get("student_id")
        if row_student_id and row.get("student_name"):
            names[str(row_student_id).strip().casefold()] = str(row["student_name"])
    return attempts, names


def _quality(normalized: Any) -> dict[str, int]:
    counters = normalized.counters
    skill_count = len({(record.student_id, record.concept_id) for record in normalized.records})
    items_seen = counters["items_seen"]
    eligible = counters["records_emitted"]
    return {
        "totalAttempts": counters["attempts_seen"],
        "totalResponses": items_seen,
        "eligibleResponses": eligible,
        "legacyConceptResponses": counters["legacy_word_fallback"],
        "skippedResponses": max(0, items_seen - eligible),
        "duplicateResponses": counters.get("duplicate_responses", 0),
        "attemptsWithoutId": counters.get("attempts_without_id", 0),
        "invalidTimestampAttempts": counters.get("invalid_timestamp", 0),
        "skillCount": skill_count,
    }


def _evaluation(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result["metrics"]
    prediction_count = int(metrics.get("n") or 0)
    positive_count = int(metrics.get("positive_count") or 0)
    negative_count = int(metrics.get("negative_count") or 0)
    return {
        "status": (
            "ready"
            if prediction_count >= MIN_PREDICTIONS_FOR_WINNER and positive_count > 0 and negative_count > 0
            else "insufficient_data"
        ),
        "responseCount": int(result.get("train_n", 0)) + prediction_count,
        "predictionCount": prediction_count,
        "positiveCount": positive_count,
        "negativeCount": negative_count,
        "logLoss": metrics.get("log_loss"),
        "brierScore": metrics.get("brier"),
        "calibrationError": metrics.get("calibration_error"),
        "auc": metrics.get("auc"),
    }


def _confidence(exposures: int) -> str:
    if exposures >= 8:
        return "high"
    if exposures >= 3:
        return "medium"
    return "low"


def _states_for_model(
    records: list[ResponseRecord], model: Literal["pfa", "bkt"], evaluation: dict[str, Any]
) -> dict[tuple[str, str], dict[str, Any]]:
    if model == "pfa":
        params = PFAParameters(**evaluation["parameters"])
        tracer = PFA(params)
        for record in records:
            tracer.update(record)
        states: dict[tuple[str, str], dict[str, Any]] = {}
        for record in records:
            key = (record.student_id, record.concept_id)
            state = tracer.state_for(*key)
            states[key] = {
                "mastery": tracer.predict(*key),
                "predictedCorrect": tracer.predict(*key),
                "successes": state.successes,
                "failures": state.failures,
            }
        return states

    tracer = BKT(BKTParameters(**evaluation["parameters"]))
    for record in records:
        tracer.update(record)
    states = {}
    counts: defaultdict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"successes": 0, "failures": 0})
    for record in records:
        key = (record.student_id, record.concept_id)
        counts[key]["successes" if record.correct else "failures"] += 1
    for key, count in counts.items():
        mastery = tracer.mastery_for(*key)
        states[key] = {
            "mastery": mastery,
            "predictedCorrect": tracer.predict(*key),
            **count,
        }
    return states


def _build_model_result(
    records: list[ResponseRecord], names: dict[str, str], model: Literal["pfa", "bkt"], quality: dict[str, int], scope: dict[str, Optional[str]]
) -> dict[str, Any]:
    evaluation_result = evaluate_prequential(records, model=model)
    final_states = _states_for_model(records, model, evaluation_result)
    last_seen: dict[tuple[str, str], Optional[str]] = {}
    for record in records:
        last_seen[(record.student_id, record.concept_id)] = record.occurred_at.isoformat() if record.occurred_at else None

    skills_by_student: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for (student_id, concept_id), values in sorted(final_states.items()):
        exposures = values["successes"] + values["failures"]
        skills_by_student[student_id].append({
            "conceptId": concept_id,
            "mastery": round(float(values["mastery"]), 6),
            "predictedCorrect": round(float(values["predictedCorrect"]), 6),
            "exposures": exposures,
            "successes": values["successes"],
            "failures": values["failures"],
            "lastSeenAt": last_seen.get((student_id, concept_id)),
            "confidence": _confidence(exposures),
        })

    return {
        "model": model,
        "modelVersion": MODEL_VERSION,
        "parameters": evaluation_result.get("parameters", {}),
        "masteryInterpretation": (
            "predicted_correct_probability"
            if model == "pfa"
            else "latent_mastery_probability"
        ),
        "scope": scope,
        "dataQuality": quality,
        "students": [
            {"studentId": student_id, "studentName": names.get(student_id), "skills": skills}
            for student_id, skills in sorted(skills_by_student.items())
        ],
        "evaluation": _evaluation(evaluation_result),
    }


def _winner(pfa: dict[str, Any], bkt: dict[str, Any]) -> Optional[str]:
    pfa_eval, bkt_eval = pfa["evaluation"], bkt["evaluation"]
    if pfa_eval["status"] != "ready" or bkt_eval["status"] != "ready":
        return None
    pfa_loss, bkt_loss = pfa_eval["logLoss"], bkt_eval["logLoss"]
    if pfa_loss is None or bkt_loss is None:
        return None
    if abs(pfa_loss - bkt_loss) < MODEL_SELECTION_TIE_MARGIN:
        return "pfa"
    return "pfa" if pfa_loss < bkt_loss else "bkt"


def _compute_knowledge_state(
    model: Literal["pfa", "bkt", "compare"],
    student_id: Optional[str],
    story_id: Optional[str],
    level: Optional[str],
) -> dict[str, Any]:
    attempts, names = _load_attempts(student_id, story_id, level)
    normalized = normalize_vocab_attempts(
        attempts,
        eligible_only=True,
        deduplicate_diagnostic_exposures=True,
    )
    records = normalized.records
    quality = _quality(normalized)
    scope = {"studentId": student_id, "storyId": story_id, "level": level}
    pfa = _build_model_result(records, names, "pfa", quality, scope)
    if model == "pfa":
        return pfa
    bkt = _build_model_result(records, names, "bkt", quality, scope)
    if model == "bkt":
        return bkt
    return {
        "model": "compare",
        "modelVersion": MODEL_VERSION,
        "scope": scope,
        "dataQuality": quality,
        "models": {"pfa": pfa, "bkt": bkt},
        "recommendedModel": _winner(pfa, bkt),
    }


def _compute_bkt_question_audit(all_tiers: bool = False) -> dict[str, Any]:
    """Read-only admin audit of the material and response-quality evidence."""
    query = "SELECT id, title, published, lesson_number, frames, quiz_approved_snapshot FROM custom_stories WHERE published = TRUE ORDER BY lesson_number NULLS LAST, created_at, id"
    with connect_db() as db:
        stories = [dict(row) for row in db.execute(query).fetchall()]
        attempts = [dict(row) for row in db.execute("SELECT id, student_id, student_name, mode, completed_at, question_results FROM vocab_quiz_attempts").fetchall()]
    rows = build_question_rows(stories, tiers=("easy", "medium", "hard") if all_tiers else ("easy",))
    # When a teacher-approved snapshot exists for a story/level it is the
    # student-serving source of truth. Otherwise retain live rows as DRAFT so
    # the report clearly shows why they cannot enter research BKT.
    approved_keys = {(row.get("story_id"), row.get("tier")) for row in rows if row.get("source") == "approved"}
    questions = [
        row
        for row in rows
        if (
            row.get("source") == "approved"
            if (row.get("story_id"), row.get("tier")) in approved_keys
            else True
        )
    ]
    report = validate_bkt_diagnostic_design(questions)
    report["responseQuality"] = analyze_response_quality(attempts)
    return report


@router.get("/knowledge-state")
async def get_knowledge_state(
    model: Literal["pfa", "bkt", "compare"] = Query(default="compare"),
    student_id: Optional[str] = Query(default=None),
    story_id: Optional[str] = Query(default=None),
    level: Optional[Literal["easy", "medium", "hard"]] = Query(default=None),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    return await run_in_threadpool(_compute_knowledge_state, model, student_id, story_id, level)


@router.get("/bkt-question-audit")
async def get_bkt_question_audit(
    all_tiers: bool = Query(default=False),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    return await run_in_threadpool(_compute_bkt_question_audit, all_tiers)
