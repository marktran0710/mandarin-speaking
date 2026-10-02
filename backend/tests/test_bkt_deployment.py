"""Fit -> activate -> serve -> deactivate, against the real registry tables."""

import random
from datetime import datetime, timedelta, timezone

import pytest

import db
from analytics.learner_model.bkt.calibration_store import run_calibration_candidate
from analytics.learner_model.bkt.core import BKT_CONFIG, bkt_parameter_fingerprint, replay_bkt_typed
from analytics.learner_model.bkt.deployment import (
    deactivate_deployment,
    load_active_deployment,
    promote_model_version,
    serving_bkt_config,
)
from analytics.learner_model.bkt.format_aware_fit import config_from_parameters
from analytics.learner_model.bkt.mastery import get_vocabulary_mastery
from services.bkt_verification_service import get_bootstrap, get_trace
from services.algorithm_verifier_service import calculate_bkt
from services.learning_engine_service import get_learning_engine_metadata


def _assert_reported_fit(conn, version, origin, student):
    expected = {"modelVersion": version, "evidenceOrigin": origin, "synthetic": origin == "SYNTHETIC"}
    bootstrap = get_bootstrap(conn)
    preview = get_bootstrap(conn, version)
    trace = get_trace(conn, student, "word-00")
    calculation = calculate_bkt({"correct": True}, conn)
    preview_calculation = calculate_bkt({"correct": True, "modelVersion": version}, conn)
    metadata = get_learning_engine_metadata(conn)
    for report in (bootstrap["model"], preview["model"], trace["model"], trace["trace"], calculation["model"], preview_calculation["model"], metadata["bkt"]):
        provenance = report["fitProvenance"]
        assert {key: provenance[key] for key in expected} == expected
        if origin == "SYNTHETIC":
            assert "not human pilot calibration" in provenance["label"]
    assert preview["model"]["activeDeployment"] is None
    assert bootstrap["model"]["activeDeployment"] == version
    assert calculation["model"]["parametersOverridden"] is False
    overridden = calculate_bkt({"correct": True, "learnRate": 0.123456789}, conn)
    assert overridden["model"]["parametersOverridden"] is True



TRUE_PARAMETERS = {
    "prior": 0.40, "learn": 0.30, "guess": 0.25, "slip": 0.06, "guess_typed": 0.02, "slip_typed": 0.22,
}
ROUNDS = (
    ("tier1", "basic_meaning_mcq"),
    ("tier2", "character_to_pinyin_typing"),
    ("tier3", "context_cloze_mcq"),
)


def _seed_ledger(conn, origin: str, *, students: int = 30, words: int = 12, seed: int = 11) -> None:
    rng = random.Random(seed)
    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    tick = 0
    for student in range(students):
        student_id = f"{origin}-student-{student:02d}"
        conn.execute(
            "INSERT INTO students (id, name, password, is_test_account) VALUES (%s, %s, 'unused-test-password', %s)",
            (student_id, student_id, origin == "synthetic"),
        )
        for word in range(words):
            known = rng.random() < TRUE_PARAMETERS["prior"]
            for position, (tier, question_type) in enumerate(ROUNDS):
                typed = question_type == "character_to_pinyin_typing"
                guess = TRUE_PARAMETERS["guess_typed" if typed else "guess"]
                slip = TRUE_PARAMETERS["slip_typed" if typed else "slip"]
                correct = rng.random() >= slip if known else rng.random() < guess
                occurred = start + timedelta(minutes=tick)
                tick += 1
                conn.execute(
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
                    VALUES (%s, %s, %s, 'story-1', %s, %s, %s, %s, 'a', 'a', '[]'::jsonb,
                            'prompt', %s, %s, 1000, %s, %s, %s, %s, TRUE, '[]'::jsonb,
                            %s, %s, 'meaning', 'diagnostic', %s, %s,
                            'authoritative-assessment-v1', %s)
                    """,
                    (
                        student_id, f"word-{word:02d}", f"詞{word:02d}",
                        f"{student_id}-{tier}", f"{student_id}-{tier}", f"item-{word}-{tier}",
                        question_type, occurred.isoformat(), correct, occurred.isoformat(), word,
                        tier, tier, f"{student_id}:{tier}:{word}", str(position + 1),
                        f"fp-{origin}-{student}-{word}-{tier}", origin, occurred,
                    ),
                )
                if not known and rng.random() < TRUE_PARAMETERS["learn"]:
                    known = True


def _expected_p_learned(conn, student_id: str, word_id: str, config) -> float:
    rows = conn.execute(
        "SELECT correct, question_type FROM vocab_quiz_responses WHERE student_id = %s AND word_id = %s "
        "ORDER BY occurred_at_utc, id",
        (student_id, word_id),
    ).fetchall()
    return replay_bkt_typed([(row["correct"], row["question_type"]) for row in rows], config)


def test_real_candidate_activates_serves_and_deactivates():
    with db.connect_db() as conn:
        _seed_ledger(conn, "real")
        result = run_calibration_candidate(conn, "real", force=True, model="format-aware")

        assert result["status"] == "completed"
        assert result["modelScope"] == "format-aware-bkt-v2"
        assert result["promotable"] is True, result["gates"]
        assert result["impact"]["students"] == 30
        assert result["impact"]["observedWords"] == 30 * 12
        version = conn.execute(
            "SELECT * FROM bkt_model_versions WHERE version = %s", (result["modelVersion"],)
        ).fetchone()
        assert version["model_scope"] == "format-aware-bkt-v2"
        assert float(version["guess_rate_typed"]) == pytest.approx(result["candidateParameters"]["guess_typed"], abs=1e-6)

        # Nothing is served until an explicit activation.
        assert serving_bkt_config(conn, BKT_CONFIG) is BKT_CONFIG
        student, word = "real-student-00", "word-00"
        default_row = next(row for row in get_vocabulary_mastery(conn, student) if row["wordId"] == word)
        assert default_row["pLearned"] == pytest.approx(_expected_p_learned(conn, student, word, BKT_CONFIG))

        promote_model_version(conn, result["modelVersion"], "integration test")
        stored = conn.execute(
            "SELECT * FROM bkt_model_versions WHERE version = %s", (result["modelVersion"],)
        ).fetchone()
        fitted = config_from_parameters({
            "prior": stored["initial_mastery"], "learn": stored["learn_rate"],
            "guess": stored["guess_rate"], "slip": stored["slip_rate"],
            "guess_typed": stored["guess_rate_typed"], "slip_typed": stored["slip_rate_typed"],
        })
        _assert_reported_fit(conn, result["modelVersion"], "REAL", student)
        assert load_active_deployment(conn)["model_version"] == result["modelVersion"]
        assert serving_bkt_config(conn, BKT_CONFIG) == fitted
        served = next(row for row in get_vocabulary_mastery(conn, student) if row["wordId"] == word)
        assert served["pLearned"] == pytest.approx(_expected_p_learned(conn, student, word, fitted))
        cache_fingerprints = {
            row["parameter_fingerprint"]
            for row in conn.execute("SELECT DISTINCT parameter_fingerprint FROM student_vocab_mastery").fetchall()
        }
        assert cache_fingerprints == {bkt_parameter_fingerprint(fitted)}
        events = conn.execute("SELECT * FROM bkt_model_deployment_events").fetchall()
        assert [event["model_version"] for event in events] == [result["modelVersion"]]

        # An explicitly passed config (research replays, tests) is never swapped.
        assert serving_bkt_config(conn, fitted) is fitted

        deactivate_deployment(conn)
        assert load_active_deployment(conn) is None
        assert serving_bkt_config(conn, BKT_CONFIG) is BKT_CONFIG
        restored = next(row for row in get_vocabulary_mastery(conn, student) if row["wordId"] == word)
        assert restored["pLearned"] == pytest.approx(default_row["pLearned"])
        cache_fingerprints = {
            row["parameter_fingerprint"]
            for row in conn.execute("SELECT DISTINCT parameter_fingerprint FROM student_vocab_mastery").fetchall()
        }
        assert cache_fingerprints == {bkt_parameter_fingerprint(BKT_CONFIG)}


def test_synthetic_candidate_requires_explicit_test_activation():
    with db.connect_db() as conn:
        _seed_ledger(conn, "synthetic")
        result = run_calibration_candidate(conn, "synthetic", force=True, model="format-aware")
    assert result["status"] == "completed"
    assert result["gatesPassed"] is True
    assert result["promotable"] is False
    assert result["impact"]["changedWords"] >= 0

    with pytest.raises(ValueError, match="allow_synthetic"):
        with db.connect_db() as conn:
            promote_model_version(conn, result["modelVersion"], "should be refused")
    with db.connect_db() as conn:
        activated = promote_model_version(
            conn,
            result["modelVersion"],
            "explicit local synthetic runtime test",
            allow_synthetic=True,
        )
        assert activated["syntheticTestDeployment"] is True
        assert load_active_deployment(conn)["evidence_origin"] == "synthetic"
        # Human-labelled replay evidence does not turn the serving fit into a human fit.
        conn.execute("UPDATE vocab_quiz_responses SET evidence_origin = 'real' WHERE student_id = 'synthetic-student-00'")
        _assert_reported_fit(conn, result["modelVersion"], "SYNTHETIC", "synthetic-student-00")
        assert get_trace(conn, "synthetic-student-00", "word-00")["trace"]["provenance"] == "REAL"
        deactivate_deployment(conn)
        assert load_active_deployment(conn) is None
        assert get_bootstrap(conn)["model"]["fitProvenance"]["evidenceOrigin"] == "ENGINEERING_DEFAULT"


def test_legacy_global_versions_cannot_serve():
    with pytest.raises(ValueError, match="not a format-aware model"):
        with db.connect_db() as conn:
            promote_model_version(conn, "standard-bkt-v1", "bootstrap row has one guess/slip pair")
