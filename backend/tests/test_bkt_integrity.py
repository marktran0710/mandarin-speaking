from types import SimpleNamespace
from uuid import uuid4

import pytest

from analytics.bkt import BKT_CONFIG, bkt_parameter_fingerprint, replay_bkt
from analytics.bkt_assessment_resolver import ASSESSMENT_RESOLVER_VERSION, resolve_assessment_response
from analytics.bkt_mastery import (
    _lock_student_bkt,
    _response_fingerprint,
    bottom_k_review_key,
    rank_review_candidates,
    response_rows_for_attempt,
    response_slot_key,
    upsert_raw_responses,
)


class _Db:
    def __init__(self, assessment):
        self.assessment = assessment

    def execute(self, _query, _params):
        return self

    def fetchone(self):
        return {"id": "lesson-1", "vocab_assessment": self.assessment}


@pytest.fixture
def assessment():
    return [{
        "questionId": "WORD_EASY", "wordId": "word-1", "targetWord": "詞",
        "level": "easy", "questionType": "basic_meaning_mcq", "answerFormat": "single_choice",
        "options": ["right", "wrong"], "correctAnswer": "right", "acceptedAnswers": ["right"], "prompt": "詞 means?",
    }]


def _attempt(mode="tier1"):
    return SimpleNamespace(mode=mode, storyId="lesson-1", baseStoryId=None)


def test_authoritative_resolver_ignores_client_correctness_and_metadata(assessment):
    resolved = resolve_assessment_response(_Db(assessment), _attempt(), {
        "itemId": "WORD_EASY", "selectedAnswer": "wrong", "correct": True,
        "conceptId": "forged", "questionKind": "forged", "correctAnswer": "wrong", "isBktEligible": True,
    })
    assert resolved["correct"] is False
    assert resolved["conceptId"] == "word-1"
    assert resolved["questionKind"] == "basic_meaning_mcq"
    assert resolved["isBktEligible"] is True
    assert resolved["resolverVersion"] == ASSESSMENT_RESOLVER_VERSION


@pytest.mark.parametrize("submitted", [
    {"itemId": "GONE", "selectedAnswer": "right"},
    {"itemId": "WORD_EASY", "selectedAnswer": "right"},
])
def test_diagnostic_keeps_unknown_or_mismatched_question_out_of_bkt(assessment, submitted):
    attempt = _attempt("tier1" if submitted["itemId"] == "GONE" else "tier2")
    resolved = resolve_assessment_response(_Db(assessment), attempt, submitted)
    assert resolved["authoritativeResolved"] is False
    assert resolved["isBktEligible"] is False
    assert "UNKNOWN_OR_STALE_DIAGNOSTIC_ITEM" in resolved["bktEligibilityErrors"]


def test_unresolved_weak_word_is_not_authoritative(assessment):
    resolved = resolve_assessment_response(_Db(assessment), _attempt("weak_words"), {"itemId": "GONE", "selectedAnswer": "right", "correct": True})
    assert resolved["authoritativeResolved"] is False
    assert resolved["isBktEligible"] is False


def test_bottom_k_order_contract():
    rows = [
        {"wordId": "c", "pLearned": .2, "observationCount": 3, "lastResponseAt": "2026-01-03"},
        {"wordId": "b", "pLearned": .2, "observationCount": 3, "lastResponseAt": "2026-01-02"},
        {"wordId": "a", "pLearned": .2, "observationCount": 2, "lastResponseAt": "2026-01-04"},
        {"wordId": "d", "pLearned": .1, "observationCount": 9, "lastResponseAt": None},
    ]
    ranked = rank_review_candidates(rows, review_count=3, include_all=False)
    assert [row["wordId"] for row in ranked] == ["d", "a", "b"]
    assert [row["reviewRank"] for row in ranked] == [1, 2, 3]


def test_response_replay_is_idempotent_only_for_the_same_student_slot_and_facts():
    row = {"student_id": "student-a", "quiz_id": "quiz", "attempt_order": 0, "correct": True}
    assert response_slot_key(row) == response_slot_key(dict(row))
    assert _response_fingerprint(row) == _response_fingerprint(dict(row))
    assert _response_fingerprint(row) != _response_fingerprint({**row, "correct": False})
    assert response_slot_key(row) != response_slot_key({**row, "student_id": "student-b"})


def test_rebuild_lock_is_transaction_scoped_per_student():
    calls = []

    class LockDb:
        def execute(self, query, params):
            calls.append((query, params))

    _lock_student_bkt(LockDb(), "student-a")
    assert "pg_advisory_xact_lock" in calls[0][0]
    assert calls[0][1] == ("student-a",)


def test_bkt_golden_vector_and_stable_parameter_provenance():
    assert replay_bkt([False, True, True]) == pytest.approx(0.8763480777700875)
    assert bkt_parameter_fingerprint() == bkt_parameter_fingerprint(BKT_CONFIG)
    assert len(bkt_parameter_fingerprint()) == 64


def _ledger_row():
    return {
        "student_id": "provenance-student", "word_id": "word-1", "word": "詞",
        "lesson_id": "lesson-1", "quiz_id": "provenance-quiz", "attempt_id": "attempt-1",
        "item_id": "WORD_EASY", "question_type": "basic_meaning_mcq", "round_type": "know_it",
        "knowledge_dimension": "meaning", "activity_type": "diagnostic",
        "diagnostic_exposure_id": "lesson-1:tier1:WORD_EASY", "bkt_eligible": True,
        "bkt_eligibility_errors": [], "selected_answer": "right", "correct_answer": "right",
        "presented_options": ["right", "wrong"], "question_prompt": "詞 means?",
        "answered_at": "2026-09-06T10:00:00Z", "correct": True, "response_time_ms": 1200,
        "occurred_at": "2026-09-06T10:00:00Z", "occurred_at_utc": None,
        "evidence_origin": "real", "resolver_version": ASSESSMENT_RESOLVER_VERSION,
        "attempt_order": 0, "quiz_level": "easy", "quiz_mode": "tier1",
    }


def test_legacy_null_fingerprint_accepts_only_an_exact_replay(clean_database):
    import database

    row = _ledger_row()
    with database.connect_db() as db:
        upsert_raw_responses(db, [row])
        db.execute(
            "UPDATE vocab_quiz_responses SET response_fingerprint = NULL "
            "WHERE student_id = %s AND quiz_id = %s AND attempt_order = %s",
            (row["student_id"], row["quiz_id"], row["attempt_order"]),
        )
        upsert_raw_responses(db, [row])
        stored = db.execute(
            "SELECT response_fingerprint FROM vocab_quiz_responses WHERE student_id = %s AND quiz_id = %s AND attempt_order = %s",
            (row["student_id"], row["quiz_id"], row["attempt_order"]),
        ).fetchone()
        assert stored["response_fingerprint"] == _response_fingerprint(row)
        with pytest.raises(ValueError, match="immutable ledger"):
            upsert_raw_responses(db, [{**row, "correct": False}])


def test_calibration_provenance_schema_seeds_defaults_and_rejects_synthetic_deployment(clean_database):
    import database

    with database.connect_db() as db:
        bootstrap = db.execute(
            "SELECT evidence_origin, initial_mastery, learn_rate, guess_rate, slip_rate "
            "FROM bkt_model_versions WHERE version = 'standard-bkt-v1'"
        ).fetchone()
        assert bootstrap["evidence_origin"] == "legacy_unknown"
        assert float(bootstrap["initial_mastery"]) == pytest.approx(.2)
        assert float(bootstrap["learn_rate"]) == pytest.approx(.15)
        assert float(bootstrap["guess_rate"]) == pytest.approx(.2)
        assert float(bootstrap["slip_rate"]) == pytest.approx(.1)
        suffix = uuid4().hex
        fit_run_id = f"synthetic-fit-{suffix}"
        model_version = f"synthetic-bkt-{suffix}"
        db.execute(
            """INSERT INTO bkt_model_fit_runs
               (id, evidence_origin, source_digest, response_count, student_count, concept_count)
               VALUES (%s, 'synthetic', 'synthetic-fixture', 0, 0, 0)""",
            (fit_run_id,),
        )
        db.execute(
            """INSERT INTO bkt_model_versions
               (version, fit_run_id, evidence_origin, initial_mastery, learn_rate, guess_rate, slip_rate, parameter_fingerprint)
               VALUES (%s, %s, 'synthetic', .2, .15, .2, .1, 'synthetic')""",
            (model_version, fit_run_id),
        )
        with pytest.raises(Exception, match="Only real-evidence"):
            db.execute("INSERT INTO bkt_model_active_deployment (model_version) VALUES (%s)", (model_version,))


def test_route_resolved_rows_record_real_provenance_and_safe_utc_timestamp(assessment):
    resolved = resolve_assessment_response(
        _Db(assessment), _attempt(), {"itemId": "WORD_EASY", "selectedAnswer": "right", "timeMs": 50, "answeredAt": "2026-09-06T10:00:00Z"},
    )
    rows = response_rows_for_attempt({"id": "attempt", "storyId": "lesson-1", "mode": "tier1", "completedAt": "not-a-time"}, "student", [resolved])
    assert rows[0]["evidence_origin"] == "real"
    assert rows[0]["resolver_version"] == ASSESSMENT_RESOLVER_VERSION
    assert rows[0]["occurred_at_utc"].isoformat() == "2026-09-06T10:00:00+00:00"
    malformed = response_rows_for_attempt(
        {"id": "attempt-2", "storyId": "lesson-1", "mode": "tier1", "completedAt": "not-a-time"},
        "student",
        [{**resolved, "answeredAt": "not-a-time"}],
    )
    assert malformed[0]["occurred_at_utc"] is None
