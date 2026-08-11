"""STEP 6/7: the per-attempt research log schema, write/read round-trip, and
the aggregation functions Step 7's metrics require -- proven against
synthetic records, never against any student's real data.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from assistive_feedback import research_log as rl


@pytest.fixture()
def log_path(tmp_path):
    return tmp_path / "test_research_log.jsonl"


def _record(**overrides) -> rl.AttemptLogRecord:
    defaults = dict(
        attempt_id="a1", participant_id="student-1", item_id="scene-1",
        syllable_index=0, character="媽", policy_state="NEEDS_PRACTICE",
        f1_risk_score=0.2, e2_diagnostic_category="T1", e2_score=10.0,
        expected_tone=1, accepted_surface_tones=[1],
    )
    defaults.update(overrides)
    return rl.AttemptLogRecord(**defaults)


def test_write_read_round_trip_preserves_every_field(log_path):
    record = _record()
    rl.log_attempt(record, path=log_path)
    read_back = rl.read_records(log_path)
    assert len(read_back) == 1
    assert read_back[0]["character"] == "媽"
    assert read_back[0]["policy_state"] == "NEEDS_PRACTICE"
    assert read_back[0]["accepted_surface_tones"] == [1]


def test_log_is_append_only(log_path):
    rl.log_attempt(_record(attempt_id="a1"), path=log_path)
    rl.log_attempt(_record(attempt_id="a2"), path=log_path)
    records = rl.read_records(log_path)
    assert [r["attempt_id"] for r in records] == ["a1", "a2"]


def test_read_records_on_missing_file_returns_empty_list(tmp_path):
    assert rl.read_records(tmp_path / "does_not_exist.jsonl") == []


def test_retry_rate_only_counts_needs_practice_rows(log_path):
    records = [
        _record(attempt_id="a1", policy_state="NEEDS_PRACTICE", retry_chosen=True).to_dict(),
        _record(attempt_id="a2", policy_state="NEEDS_PRACTICE", retry_chosen=False).to_dict(),
        _record(attempt_id="a3", policy_state="ACCEPT", retry_chosen=True).to_dict(),  # should not count -- retry wasn't even offered
    ]
    assert rl.retry_rate(records) == pytest.approx(0.5)


def test_flagged_and_uncertain_counts(log_path):
    records = [
        _record(policy_state="NEEDS_PRACTICE").to_dict(),
        _record(policy_state="NEEDS_PRACTICE").to_dict(),
        _record(policy_state="UNCERTAIN").to_dict(),
        _record(policy_state="ACCEPT").to_dict(),
    ]
    assert rl.flagged_syllable_count(records) == 2
    assert rl.uncertain_case_count(records) == 1


def test_completion_rate_excludes_abandoned(log_path):
    records = [
        _record(progression_outcome="continued_immediately").to_dict(),
        _record(progression_outcome="continued_after_retry").to_dict(),
        _record(progression_outcome="abandoned").to_dict(),
    ]
    assert rl.completion_rate(records) == pytest.approx(2 / 3)


def test_abandonment_rate_by_state_never_treats_needs_practice_as_blocked(log_path):
    """The abandonment metric is descriptive only -- it must not assume
    NEEDS_PRACTICE causes abandonment; that is exactly the empirical
    question STEP 7 exists to let research answer, not something baked in."""
    records = [
        _record(policy_state="NEEDS_PRACTICE", progression_outcome="continued_after_cap").to_dict(),
        _record(policy_state="NEEDS_PRACTICE", progression_outcome="abandoned").to_dict(),
    ]
    rates = rl.abandonment_rate_by_state(records)
    assert rates["NEEDS_PRACTICE"] == pytest.approx(0.5)
    assert rates["ACCEPT"] is None  # no ACCEPT rows in this sample -- None, not 0


def test_attempt1_to_attempt2_transition_counts(log_path):
    records = [
        _record(retry_chosen=True, policy_state="NEEDS_PRACTICE", second_attempt_policy_state="ACCEPT").to_dict(),
        _record(retry_chosen=True, policy_state="NEEDS_PRACTICE", second_attempt_policy_state="NEEDS_PRACTICE").to_dict(),
        _record(retry_chosen=False, policy_state="NEEDS_PRACTICE").to_dict(),  # no retry -- excluded
    ]
    counts = rl.attempt1_to_attempt2_transition_counts(records)
    assert counts[("NEEDS_PRACTICE", "ACCEPT")] == 1
    assert counts[("NEEDS_PRACTICE", "NEEDS_PRACTICE")] == 1


def test_no_field_ever_labelled_correct_or_incorrect_as_a_verdict():
    """Structural guard: the schema itself never claims a factual
    correctness verdict -- `policy_state` is a risk/evidence label
    (ACCEPT/UNCERTAIN/NEEDS_PRACTICE), not "correct"/"incorrect"."""
    record = _record()
    values = [str(v) for v in record.to_dict().values()]
    assert not any(v in ("correct", "incorrect", "wrong") for v in values)
