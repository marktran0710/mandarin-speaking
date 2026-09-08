from datetime import datetime, timedelta, timezone

import pytest

import database
from analytics.bkt_calibration_store import (
    load_calibration_snapshot,
    refit_decision,
    run_calibration_candidate,
)


def _insert_response(
    db,
    index: int,
    *,
    origin: str = "real",
    student_id: str = "student-1",
    eligible: bool = True,
    resolver_version: str | None = "authoritative-assessment-v1",
    fingerprint: str | None = None,
    occurred_at: datetime | None = None,
    activity_type: str = "diagnostic",
) -> None:
    occurred_at = occurred_at or datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)
    db.execute(
        """
        INSERT INTO vocab_quiz_responses
            (student_id, word_id, word, lesson_id, quiz_id, attempt_id,
             item_id, question_type, selected_answer, correct_answer,
             presented_options, question_prompt, answered_at, correct,
             response_time_ms, occurred_at, attempt_order, quiz_level,
             quiz_mode, bkt_eligible, bkt_eligibility_errors,
             diagnostic_exposure_id, round_type, knowledge_dimension,
             activity_type, response_fingerprint, evidence_origin,
             resolver_version, occurred_at_utc)
        VALUES (%s, %s, %s, 'story-1', %s, %s, %s,
                'basic_meaning_mcq', 'answer', 'answer', '[]'::jsonb,
                'prompt', %s, %s, 1000, %s, 0, 'easy', 'tier1', %s,
                '[]'::jsonb, %s, 'know_it', 'meaning', %s, %s, %s, %s, %s)
        """,
        (
            student_id,
            f"concept-{index % 10}",
            f"word-{index % 10}",
            f"quiz-{index}",
            f"attempt-{index}",
            f"item-{index}",
            occurred_at.isoformat(),
            index % 2 == 0,
            occurred_at.isoformat(),
            eligible,
            f"exposure-{index}",
            activity_type,
            fingerprint if fingerprint is not None else f"fingerprint-{index}",
            origin,
            resolver_version,
            occurred_at,
        ),
    )


def _successful_synthetic_report(records):
    students = sorted({record.student_id for record in records})
    return {
        "promotable": False,
        "candidate_parameters": {"prior": .24, "learn": .17, "guess": .18, "slip": .09},
        "production_parameters": {"prior": .2, "learn": .15, "guess": .2, "slip": .1},
        "counts": {
            "records": len(records),
            "students": len(students),
            "qualifying_students": len(students),
            "concepts": len({record.concept_id for record in records}),
            "correct": sum(record.correct for record in records),
            "incorrect": sum(not record.correct for record in records),
        },
        "split_spec": {"strategy": "deterministic_student_grouped", "fold_count": 5},
        "gates": {"synthetic_never_promotable": True},
        "diagnostics": {"final": {"status": "success"}, "folds": []},
        "parameter_constraints": {"all": True},
        "metrics": {"candidate": {"log_loss": .5}, "production": {"log_loss": .6}},
        "fold_assignments": {student: index % 5 for index, student in enumerate(students)},
    }


def test_snapshot_uses_only_provenance_complete_authoritative_rows():
    with database.connect_db() as db:
        _insert_response(db, 1)
        _insert_response(db, 2)
        _insert_response(db, 3, origin="synthetic", resolver_version="synthetic-fixture-v1")
        _insert_response(db, 4, eligible=False)
        _insert_response(db, 5, resolver_version=None)
        _insert_response(db, 6, fingerprint="")
        _insert_response(db, 7, activity_type="personalized_practice")
        real = load_calibration_snapshot(db, "real")
        synthetic = load_calibration_snapshot(db, "synthetic")

    assert [record.attempt_id for record in real.records] == ["attempt-1", "attempt-2"]
    assert real.high_water_response_id is not None
    assert real.resolver_versions == ("authoritative-assessment-v1",)
    assert len(real.source_digest) == 64
    assert [record.attempt_id for record in synthetic.records] == ["attempt-3"]


def test_synthetic_candidate_is_stored_but_cannot_be_deployed(monkeypatch):
    with database.connect_db() as db:
        for student in range(25):
            for response in range(5):
                index = student * 5 + response
                _insert_response(
                    db,
                    index,
                    origin="synthetic",
                    student_id=f"synthetic-{student:02d}",
                    resolver_version="synthetic-fixture-v1",
                )
        monkeypatch.setattr(
            "analytics.bkt_calibration_store.calibrate_bkt",
            lambda records, **_kwargs: _successful_synthetic_report(records),
        )
        result = run_calibration_candidate(db, "synthetic", force=True)
        fit = db.execute(
            "SELECT evidence_origin, promotable, source_digest FROM bkt_model_fit_runs WHERE id = %s",
            (result["fitRunId"],),
        ).fetchone()
        model = db.execute(
            "SELECT evidence_origin, fit_run_id FROM bkt_model_versions WHERE version = %s",
            (result["modelVersion"],),
        ).fetchone()

    assert result["promotable"] is False
    assert fit["evidence_origin"] == "synthetic"
    assert fit["promotable"] is False
    assert fit["source_digest"] == result["sourceDigest"]
    assert model["evidence_origin"] == "synthetic"
    assert model["fit_run_id"] == result["fitRunId"]
    with pytest.raises(Exception, match="Only real-evidence"):
        with database.connect_db() as db:
            db.execute(
                "INSERT INTO bkt_model_active_deployment (model_version) VALUES (%s)",
                (result["modelVersion"],),
            )


def test_scheduled_refit_waits_for_interval_and_enough_new_evidence():
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with database.connect_db() as db:
        _insert_response(db, 1, occurred_at=started)
        first = load_calibration_snapshot(db, "real")
        assert refit_decision(db, "real", first, now=started)["reason"] == "first_candidate"
        db.execute(
            """
            INSERT INTO bkt_model_fit_runs
                (id, evidence_origin, source_digest, high_water_response_id,
                 response_count, student_count, concept_count, completed_at)
            VALUES ('real-fit-1', 'real', %s, %s, 1, 1, 1, %s)
            """,
            (first.source_digest, first.high_water_response_id, started),
        )
        for offset in range(2, 252):
            _insert_response(
                db,
                offset,
                student_id=f"student-{offset % 7}",
                occurred_at=started + timedelta(minutes=offset),
            )
        current = load_calibration_snapshot(db, "real")
        cooling_down = refit_decision(db, "real", current, now=started + timedelta(days=1))
        ready = refit_decision(db, "real", current, now=started + timedelta(days=8))

    assert cooling_down["due"] is False
    assert cooling_down["reason"] == "cooldown"
    assert ready["due"] is True
    assert ready["reason"] == "new_evidence_ready"
    assert ready["newResponses"] == 250


def test_force_does_not_create_a_candidate_without_evidence():
    with database.connect_db() as db:
        result = run_calibration_candidate(db, "real", force=True)
        count = db.execute(
            "SELECT COUNT(*) AS count FROM bkt_model_fit_runs WHERE evidence_origin = 'real'"
        ).fetchone()["count"]

    assert result["status"] == "skipped"
    assert result["decision"]["reason"] == "no_eligible_evidence"
    assert count == 0
