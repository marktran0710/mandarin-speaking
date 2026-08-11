"""STEP 8: re-runs the synthetic pilot dry run and checks its own
assertions hold (the dry run script asserts internally too; this test
re-invokes it under pytest so a regression here shows up in the normal
suite, and adds a few extra structural checks the script doesn't already
make).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from assistive_feedback import pilot_dry_run, research_log


def test_dry_run_completes_and_verifies(tmp_path):
    result = pilot_dry_run.run(path=tmp_path / "dry_run.jsonl")
    assert result["n_logged"] == 8
    assert result["scenario_1"]["n_attempts"] == 3
    assert result["scenario_2_no_issue_no_retry"]["retry_offered"] is False
    assert result["scenario_3_uncertain_progresses"]["progressed_without_needs_practice_ever_appearing"] is True


def test_reconstruction_never_reads_timestamp_field(tmp_path):
    """Structural guard: `reconstruct_sequence`/`join_retries` never
    reference the string "timestamp" anywhere in their source -- ordering
    and linkage come only from `attempt_number`/`attempt_id`/
    `retry_of_attempt_id`/`retry_of_syllable_index`."""
    import ast
    import inspect

    for fn in (research_log.reconstruct_sequence, research_log.join_retries):
        tree = ast.parse(inspect.getsource(fn))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "timestamp":
                raise AssertionError(f"{fn.__name__} references 'timestamp' -- reconstruction must be timestamp-free")


def test_scenario_1_progression_never_blocked(tmp_path):
    path = tmp_path / "dry_run.jsonl"
    pilot_dry_run.run(path=path)
    records = research_log.read_records(path)
    outcomes = {r["progression_outcome"] for r in records}
    assert "blocked" not in outcomes  # this policy has no such outcome at all
    assert "abandoned" not in outcomes  # nobody abandoned in this synthetic sequence


def test_no_issue_detected_scenario_has_a_single_attempt(tmp_path):
    path = tmp_path / "dry_run.jsonl"
    pilot_dry_run.run(path=path)
    records = research_log.read_records(path)
    sequence = research_log.reconstruct_sequence(records, "P002", "ITEM002", session_id="S001")
    assert len(sequence) == 1
    assert sequence[0]["attempt_type"] == "WHOLE_SENTENCE_INITIAL"


def test_uncertain_scenario_progresses_without_any_retry_machinery(tmp_path):
    path = tmp_path / "dry_run.jsonl"
    pilot_dry_run.run(path=path)
    records = research_log.read_records(path)
    sequence = research_log.reconstruct_sequence(records, "P003", "ITEM003", session_id="S001")
    assert len(sequence) == 1
    assert sequence[0]["syllables"][0]["policy_state"] == "UNCERTAIN"
    assert sequence[0]["retry_of_attempt_id"] is None
