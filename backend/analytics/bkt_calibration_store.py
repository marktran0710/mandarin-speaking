"""Authoritative BKT calibration snapshots and immutable candidate storage.

This module is intentionally outside the learner-serving path.  It reads a
high-water-marked snapshot of the normalized response ledger, runs the
offline grouped evaluation, and records a candidate.  It never changes the
active deployment pointer or the runtime defaults in :mod:`analytics.bkt`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Any, Literal
from uuid import uuid4

from psycopg.types.json import Jsonb

from analytics.bkt_calibration import calibrate_bkt
from analytics.knowledge_tracing import BKTParameters, ResponseRecord


CalibrationOrigin = Literal["real", "synthetic"]

# Operational cadence defaults, not model parameters.  A scheduler may invoke
# the CLI daily; these gates prevent fitting on every learner response.
DEFAULT_MIN_REFIT_INTERVAL = timedelta(days=7)
DEFAULT_MIN_NEW_RESPONSES = 250
DEFAULT_MIN_NEW_STUDENTS = 5
CALIBRATION_LOCK_NAMESPACE = "mandarin-speaking:bkt-calibration:v1"


@dataclass(frozen=True)
class CalibrationSnapshot:
    evidence_origin: CalibrationOrigin
    high_water_response_id: int | None
    records: tuple[ResponseRecord, ...]
    source_digest: str
    resolver_versions: tuple[str, ...]
    training_window_start: datetime | None
    training_window_end: datetime | None


def _validate_origin(value: str) -> CalibrationOrigin:
    if value not in {"real", "synthetic"}:
        raise ValueError("Calibration evidence origin must be 'real' or 'synthetic'.")
    return value  # type: ignore[return-value]


def _qualified_evidence_sql(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return (
        f"{prefix}bkt_eligible = TRUE "
        f"AND NULLIF({prefix}resolver_version, '') IS NOT NULL "
        f"AND NULLIF({prefix}response_fingerprint, '') IS NOT NULL "
        f"AND {prefix}occurred_at_utc IS NOT NULL "
        f"AND {prefix}activity_type = 'diagnostic'"
    )


def _source_digest(rows: list[dict[str, Any]]) -> str:
    facts = [
        {
            "id": int(row["id"]),
            "response_fingerprint": row["response_fingerprint"],
            "resolver_version": row["resolver_version"],
        }
        for row in rows
    ]
    encoded = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


def load_calibration_snapshot(
    db: Any,
    evidence_origin: str,
    *,
    student_id: str | None = None,
    story_id: str | None = None,
    level: str | None = None,
) -> CalibrationSnapshot:
    """Load one deterministic, provenance-complete ledger snapshot.

    The high-water id is captured first and included in the row query.  New
    answers arriving while an offline run is fitting therefore belong to the
    next candidate rather than silently changing this run's training set.
    """
    origin = _validate_origin(evidence_origin)
    maximum = db.execute(
        "SELECT MAX(id) AS id FROM vocab_quiz_responses WHERE evidence_origin = %s",
        (origin,),
    ).fetchone()
    high_water = int(maximum["id"]) if maximum and maximum.get("id") is not None else None
    if high_water is None:
        return CalibrationSnapshot(origin, None, (), sha256(b"[]").hexdigest(), (), None, None)

    filters = ["evidence_origin = %s", "id <= %s", _qualified_evidence_sql()]
    params: list[Any] = [origin, high_water]
    if student_id:
        filters.append("student_id = %s")
        params.append(student_id)
    if story_id:
        filters.append("lesson_id = %s")
        params.append(story_id)
    if level:
        filters.append("quiz_level = %s")
        params.append(level)
    rows = [dict(row) for row in db.execute(
        f"""
        SELECT id, student_id, word_id, correct, occurred_at_utc, attempt_id,
               attempt_order, lesson_id, item_id, question_type, quiz_level,
               quiz_mode, resolver_version, response_fingerprint
        FROM vocab_quiz_responses
        WHERE {' AND '.join(filters)}
        ORDER BY occurred_at_utc ASC, id ASC
        """,
        params,
    ).fetchall()]
    records = tuple(
        ResponseRecord(
            student_id=str(row["student_id"]),
            concept_id=str(row["word_id"]),
            correct=bool(row["correct"]),
            occurred_at=row["occurred_at_utc"],
            attempt_id=str(row["attempt_id"]),
            question_index=int(row["attempt_order"]),
            story_id=row.get("lesson_id"),
            item_id=row.get("item_id"),
            question_kind=row.get("question_type"),
            level=row.get("quiz_level"),
            mode=row.get("quiz_mode"),
        )
        for row in rows
    )
    timestamps = [record.occurred_at for record in records if record.occurred_at is not None]
    return CalibrationSnapshot(
        evidence_origin=origin,
        high_water_response_id=high_water,
        records=records,
        source_digest=_source_digest(rows),
        resolver_versions=tuple(sorted({str(row["resolver_version"]) for row in rows})),
        training_window_start=min(timestamps) if timestamps else None,
        training_window_end=max(timestamps) if timestamps else None,
    )


def refit_decision(
    db: Any,
    evidence_origin: str,
    snapshot: CalibrationSnapshot,
    *,
    now: datetime | None = None,
    min_interval: timedelta = DEFAULT_MIN_REFIT_INTERVAL,
    min_new_responses: int = DEFAULT_MIN_NEW_RESPONSES,
    min_new_students: int = DEFAULT_MIN_NEW_STUDENTS,
) -> dict[str, Any]:
    """Return whether a scheduled invocation has enough new evidence to fit."""
    origin = _validate_origin(evidence_origin)
    now = now or datetime.now(timezone.utc)
    latest = db.execute(
        """
        SELECT high_water_response_id, completed_at
        FROM bkt_model_fit_runs
        WHERE evidence_origin = %s
        ORDER BY completed_at DESC NULLS LAST, requested_at DESC, id DESC
        LIMIT 1
        """,
        (origin,),
    ).fetchone()
    if not snapshot.records:
        return {"due": False, "reason": "no_eligible_evidence", "newResponses": 0, "newStudents": 0}
    if latest is None:
        return {
            "due": True,
            "reason": "first_candidate",
            "newResponses": len(snapshot.records),
            "newStudents": len({record.student_id for record in snapshot.records}),
        }

    previous_high_water = int(latest.get("high_water_response_id") or 0)
    new_counts = db.execute(
        f"""
        SELECT COUNT(*) AS responses, COUNT(DISTINCT student_id) AS students
        FROM vocab_quiz_responses
        WHERE evidence_origin = %s AND id > %s AND id <= %s
          AND {_qualified_evidence_sql()}
        """,
        (origin, previous_high_water, snapshot.high_water_response_id or 0),
    ).fetchone()
    new_responses = int(new_counts["responses"] or 0)
    new_students = int(new_counts["students"] or 0)
    completed_at = latest.get("completed_at")
    if completed_at is not None and completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    interval_ready = completed_at is None or now - completed_at >= min_interval
    evidence_ready = new_responses >= min_new_responses or new_students >= min_new_students
    if not interval_ready:
        reason = "cooldown"
    elif not evidence_ready:
        reason = "insufficient_new_evidence"
    else:
        reason = "new_evidence_ready"
    return {
        "due": interval_ready and evidence_ready,
        "reason": reason,
        "newResponses": new_responses,
        "newStudents": new_students,
        "previousHighWaterResponseId": previous_high_water or None,
    }


def _parameter_fingerprint(parameters: dict[str, float]) -> str:
    payload = json.dumps(parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def persist_calibration_candidate(
    db: Any,
    snapshot: CalibrationSnapshot,
    report: dict[str, Any],
    *,
    requested_at: datetime,
    completed_at: datetime,
) -> tuple[str, str]:
    """Atomically append an immutable fit run and its candidate version."""
    suffix = uuid4().hex[:8]
    stamp = completed_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"bkt-fit-{snapshot.evidence_origin}-{stamp}-{suffix}"
    model_version = f"bkt-{snapshot.evidence_origin}-candidate-{stamp}-{suffix}"
    candidate = report["candidate_parameters"]
    diagnostics = report.get("diagnostics") or {}
    failed = diagnostics.get("final", {}).get("status") == "failed" or any(
        fold.get("status") == "failed" for fold in diagnostics.get("folds", [])
    )
    status = "failed" if failed else "completed"
    resolver_version = ",".join(snapshot.resolver_versions) or None
    counts = report["counts"]
    db.execute(
        """
        INSERT INTO bkt_model_fit_runs
            (id, evidence_origin, resolver_version, source_digest,
             high_water_response_id, response_count, student_count,
             concept_count, split_spec, promotion_gates, diagnostics, status,
             promotable, requested_at, completed_at, training_window_start,
             training_window_end, parameters, metrics)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s)
        """,
        (
            run_id,
            snapshot.evidence_origin,
            resolver_version,
            snapshot.source_digest,
            snapshot.high_water_response_id,
            counts["records"],
            counts["students"],
            counts["concepts"],
            Jsonb(report["split_spec"]),
            Jsonb(report["gates"]),
            Jsonb(diagnostics),
            status,
            bool(report["promotable"]),
            requested_at,
            completed_at,
            snapshot.training_window_start,
            snapshot.training_window_end,
            Jsonb({
                "candidate": candidate,
                "production": report["production_parameters"],
                "constraints": report["parameter_constraints"],
            }),
            Jsonb(report["metrics"]),
        ),
    )
    for student_id, fold_index in report["fold_assignments"].items():
        db.execute(
            "INSERT INTO bkt_model_student_folds (fit_run_id, student_id, fold_index) VALUES (%s, %s, %s)",
            (run_id, student_id, fold_index),
        )
    db.execute(
        """
        INSERT INTO bkt_model_versions
            (version, fit_run_id, evidence_origin, initial_mastery, learn_rate,
             guess_rate, slip_rate, parameter_fingerprint)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            model_version,
            run_id,
            snapshot.evidence_origin,
            candidate["prior"],
            candidate["learn"],
            candidate["guess"],
            candidate["slip"],
            _parameter_fingerprint(candidate),
        ),
    )
    return run_id, model_version


def run_calibration_candidate(
    db: Any,
    evidence_origin: str,
    *,
    force: bool = False,
    iterations: int = 80,
    production_parameters: BKTParameters = BKTParameters(),
) -> dict[str, Any]:
    """Run one locked offline fit and persist a candidate, never a deployment."""
    origin = _validate_origin(evidence_origin)
    lock = db.execute(
        "SELECT pg_try_advisory_xact_lock(hashtext(%s)) AS acquired",
        (f"{CALIBRATION_LOCK_NAMESPACE}:{origin}",),
    ).fetchone()
    if not lock or not lock["acquired"]:
        raise RuntimeError(f"A {origin} BKT calibration run is already in progress.")

    snapshot = load_calibration_snapshot(db, origin)
    decision = refit_decision(db, origin, snapshot)
    # ``--force`` bypasses cadence only; it must never manufacture a model
    # version from an empty evidence set.
    if not snapshot.records or (not force and not decision["due"]):
        return {
            "status": "skipped",
            "evidenceOrigin": origin,
            "decision": decision,
            "highWaterResponseId": snapshot.high_water_response_id,
        }

    requested_at = datetime.now(timezone.utc)
    report = calibrate_bkt(
        snapshot.records,
        synthetic=origin == "synthetic",
        iterations=iterations,
        production_parameters=production_parameters,
    )
    completed_at = datetime.now(timezone.utc)
    run_id, model_version = persist_calibration_candidate(
        db,
        snapshot,
        report,
        requested_at=requested_at,
        completed_at=completed_at,
    )
    return {
        "status": "completed",
        "fitRunId": run_id,
        "modelVersion": model_version,
        "evidenceOrigin": origin,
        "promotable": bool(report["promotable"]),
        "highWaterResponseId": snapshot.high_water_response_id,
        "sourceDigest": snapshot.source_digest,
        "counts": report["counts"],
        "candidateParameters": report["candidate_parameters"],
        "productionParameters": report["production_parameters"],
        "metrics": report["metrics"],
        "gates": report["gates"],
        "decision": decision,
    }
