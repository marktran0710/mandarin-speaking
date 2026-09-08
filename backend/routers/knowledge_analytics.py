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
    ResponseRecord,
)
from analytics.bkt_calibration_store import CalibrationSnapshot, load_calibration_snapshot
from database import connect_db
from analytics.bkt_question_validation import analyze_response_quality, validate_bkt_diagnostic_design
from scripts.export_quiz_questions import build_question_rows


router = APIRouter(
    prefix="/api/admin/analytics",
    tags=["admin-analytics"],
    dependencies=[Depends(auth.require_admin)],
)

MODEL_VERSION = "knowledge-pilot-v2"
MIN_TRAINING_RECORDS = 100
MIN_EVALUATION_PREDICTIONS = 100
MIN_EVALUATION_CLASS_COUNT = 20
MIN_STUDENTS = 10
MIN_CONCEPTS = 10
MODEL_SELECTION_TIE_MARGIN = 0.01


def _load_records(
    student_id: Optional[str], story_id: Optional[str], level: Optional[str]
) -> tuple[list[ResponseRecord], dict[str, str], CalibrationSnapshot]:
    """Read only authoritative, provenance-complete real ledger evidence."""
    with connect_db() as db:
        snapshot = load_calibration_snapshot(
            db,
            "real",
            student_id=student_id,
            story_id=story_id,
            level=level,
        )
        ids = sorted({record.student_id for record in snapshot.records})
        rows = db.execute(
            "SELECT id, name FROM students WHERE id = ANY(%s)",
            (ids,),
        ).fetchall() if ids else []
    names = {str(row["id"]): str(row["name"]) for row in rows}
    return list(snapshot.records), names, snapshot


def _quality(records: list[ResponseRecord], snapshot: CalibrationSnapshot) -> dict[str, Any]:
    skill_count = len({(record.student_id, record.concept_id) for record in records})
    student_count = len({record.student_id for record in records})
    concept_count = len({record.concept_id for record in records})
    return {
        "totalAttempts": len({record.attempt_id for record in records}),
        "totalResponses": len(records),
        "eligibleResponses": len(records),
        "legacyConceptResponses": 0,
        "skippedResponses": 0,
        "duplicateResponses": 0,
        "attemptsWithoutId": 0,
        "invalidTimestampAttempts": 0,
        "skillCount": skill_count,
        "studentCount": student_count,
        "conceptCount": concept_count,
        "evidenceSource": "authoritative_response_ledger",
        "evidenceOrigin": snapshot.evidence_origin,
        "resolverVersions": list(snapshot.resolver_versions),
        "highWaterResponseId": snapshot.high_water_response_id,
        "sourceDigest": snapshot.source_digest,
    }


def _evaluation(result: dict[str, Any], quality: dict[str, int]) -> dict[str, Any]:
    metrics = result["metrics"]
    prediction_count = int(metrics.get("n") or 0)
    positive_count = int(metrics.get("positive_count") or 0)
    negative_count = int(metrics.get("negative_count") or 0)
    checks = [
        {"name": "training_records", "actual": int(result.get("train_n", 0)), "minimum": MIN_TRAINING_RECORDS},
        {"name": "evaluation_predictions", "actual": prediction_count, "minimum": MIN_EVALUATION_PREDICTIONS},
        {"name": "evaluation_positives", "actual": positive_count, "minimum": MIN_EVALUATION_CLASS_COUNT},
        {"name": "evaluation_negatives", "actual": negative_count, "minimum": MIN_EVALUATION_CLASS_COUNT},
        {"name": "students", "actual": quality["studentCount"], "minimum": MIN_STUDENTS},
        {"name": "concepts", "actual": quality["conceptCount"], "minimum": MIN_CONCEPTS},
    ]
    for check in checks:
        check["passed"] = check["actual"] >= check["minimum"]
    fit_diagnostics = result.get("fit_diagnostics", {})
    fit_status = fit_diagnostics.get("status", "failed")
    status = "fit_failed" if fit_status == "failed" else ("evidence_ready" if all(check["passed"] for check in checks) else "insufficient_evidence")
    return {
        "status": status,
        "responseCount": int(result.get("train_n", 0)) + prediction_count,
        "predictionCount": prediction_count,
        "positiveCount": positive_count,
        "negativeCount": negative_count,
        "logLoss": metrics.get("log_loss"),
        "brierScore": metrics.get("brier"),
        "calibrationError": metrics.get("calibration_error"),
        "auc": metrics.get("auc"),
        "evidenceChecks": checks,
        "fitDiagnostics": fit_diagnostics,
    }


def _evidence_depth(exposures: int) -> str:
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
            "evidenceDepth": _evidence_depth(exposures),
        })

    return {
        "model": model,
        "modelVersion": MODEL_VERSION,
        "implementation": "restricted_pooled_baseline" if model == "pfa" else "pooled_bkt_pilot",
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
        "evaluation": _evaluation(evaluation_result, quality),
    }


def _lower_loss_signal(pfa: dict[str, Any], bkt: dict[str, Any]) -> Optional[str]:
    pfa_eval, bkt_eval = pfa["evaluation"], bkt["evaluation"]
    if pfa_eval["status"] != "evidence_ready" or bkt_eval["status"] != "evidence_ready":
        return None
    pfa_loss, bkt_loss = pfa_eval["logLoss"], bkt_eval["logLoss"]
    if pfa_loss is None or bkt_loss is None:
        return None
    if abs(pfa_loss - bkt_loss) <= MODEL_SELECTION_TIE_MARGIN:
        return "no_material_difference"
    return "pfa" if pfa_loss < bkt_loss else "bkt"


def _compute_knowledge_state(
    model: Literal["pfa", "bkt", "compare"],
    student_id: Optional[str],
    story_id: Optional[str],
    level: Optional[str],
) -> dict[str, Any]:
    records, names, snapshot = _load_records(student_id, story_id, level)
    quality = _quality(records, snapshot)
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
        "lowerLossSignal": _lower_loss_signal(pfa, bkt),
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
