"""Pure contract checks: no live database, safe with pytest --noconftest."""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from analytics.learner_model.bkt.calibration_store import load_calibration_snapshot, refit_decision, _parameter_fingerprint
from analytics.learner_model.bkt.core import BKT_CONFIG, bkt_parameter_fingerprint, replay_bkt_typed
from analytics.learner_model.bkt.deployment import preview_bkt_config
from analytics.learner_model.bkt.format_aware_fit import baseline_parameters, config_from_parameters, registry_parameters
from services.algorithm_verifier_service import calculate_bkt
from services.vocab_quiz_attempt_service import _server_evidence_origin


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class StubDB:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return Result(next(self.results))


def test_registry_precision_and_fingerprint_match_served_values():
    params = registry_parameters({**baseline_parameters(), "prior": 0.1234565, "slip_typed": 0.17891231})
    assert params["prior"] == 0.123457
    assert params["slip_typed"] == 0.178912
    assert _parameter_fingerprint(params) == bkt_parameter_fingerprint(config_from_parameters(params))


def test_cohort_and_test_account_filters_apply_to_high_water_snapshot_and_cadence():
    now = datetime(2026, 9, 28, tzinfo=timezone.utc)
    row = {"id": 10, "student_id": "learner", "word_id": "word", "correct": True,
           "occurred_at_utc": now, "attempt_id": "a", "attempt_order": 0,
           "response_fingerprint": "fp", "resolver_version": "v1"}
    db = StubDB([[{"id": 10}], [row], [{"high_water_response_id": 9, "completed_at": now}],
                 [{"responses": 1, "students": 1}]])
    snapshot = load_calibration_snapshot(db, "real", student_ids=["learner", "learner"], story_id="story")
    refit_decision(db, "real", snapshot, now=now)
    assert snapshot.scope["student_ids"] == ["learner"]
    for index in (0, 1, 3):
        sql, params = db.calls[index]
        assert "s.is_test_account = FALSE" in sql
        assert "r.student_id = ANY(%s)" in sql
        assert ["learner"] in params
        assert "story" in params
    assert "split_spec->'dataset_scope'" in db.calls[2][0]


def test_empty_cohort_cannot_silently_fit_every_student():
    with pytest.raises(ValueError, match="student_ids"):
        load_calibration_snapshot(StubDB([]), "synthetic", student_ids=[])


def test_server_tags_test_account_responses_synthetic():
    for requested in ("real", "synthetic"):
        assert _server_evidence_origin(StubDB([[{"is_test_account": True}]]), "SIM001", requested) == "synthetic"
    assert _server_evidence_origin(StubDB([[{"is_test_account": False}]]), "learner", "real") == "real"


def test_recovery_uses_selected_typed_pair_and_reference_checks_every_step():
    config = replace(BKT_CONFIG, learn_rate=0.10, guess_rate=0.25, slip_rate=0.12,
                     guess_rate_typed=0.04, slip_rate_typed=0.18)
    observations = [{"correct": False, "questionFormat": "mcq"},
                    {"correct": True, "questionFormat": "typed"},
                    {"correct": True, "questionFormat": "mcq"}]
    result = calculate_bkt({"observations": observations}, config=config)
    expected = replay_bkt_typed([(False, "basic_meaning_mcq"), (True, "character_to_pinyin_typing"),
                                (True, "context_cloze_mcq")], config)
    assert result["production"]["resultingMastery"] == pytest.approx(expected, abs=1e-12)
    assert result["difference"] <= 1e-12
    assert result["model"]["parameterFingerprint"] == bkt_parameter_fingerprint(config)


def test_sequence_overrides_use_the_same_rates_in_independent_reference():
    result = calculate_bkt({"questionFormat": "typed", "guess": 0.07, "slip": 0.19,
                            "observations": [{"correct": False, "questionType": "basic_meaning_mcq"},
                                             {"correct": True, "questionType": "productive_recall", "guess": 0.03}]})
    assert result["difference"] <= 1e-12


def test_preview_reads_synthetic_candidate_without_changing_deployment():
    row = {"model_scope": "format-aware-bkt-v2", "initial_mastery": 0.3, "learn_rate": 0.1,
           "guess_rate": 0.25, "slip_rate": 0.12, "guess_rate_typed": 0.04, "slip_rate_typed": 0.18}
    db = StubDB([[row]])
    selected = preview_bkt_config(db, "synthetic-candidate")
    assert selected.initial_mastery == 0.3 and selected.slip_rate_typed == 0.18
    assert len(db.calls) == 1 and db.calls[0][0].startswith("SELECT")
    with pytest.raises(ValueError, match="Unknown BKT"):
        preview_bkt_config(StubDB([[]]), "missing")
