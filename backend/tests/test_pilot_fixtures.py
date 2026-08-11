"""STEP 8: the manual pilot fixture set stays correct against the live
frozen policy -- re-verifies every row of
`tests/fixtures/assistive_feedback_pilot_fixtures.json` (built by
`assistive_feedback.build_pilot_fixtures`) rather than trusting the
on-disk file was generated correctly and never re-checking it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from assistive_feedback import policy as policy_module

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "assistive_feedback_pilot_fixtures.json"

pytestmark = pytest.mark.skipif(
    not FIXTURES_PATH.exists(),
    reason="pilot fixtures not built -- run `python -m assistive_feedback.build_pilot_fixtures` first",
)


@pytest.fixture(scope="module")
def fixtures():
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def test_covers_all_six_tone_contexts(fixtures):
    contexts = {row["context"] for row in fixtures}
    assert contexts == {"T1", "T2", "T3_full_third", "T3_half_third", "T3_to_T2_sandhi", "T4"}


def test_covers_all_three_policy_states_per_context(fixtures):
    by_context: dict[str, set[str]] = {}
    for row in fixtures:
        by_context.setdefault(row["context"], set()).add(row["expected_state"])
    for context, states in by_context.items():
        assert states == {"ACCEPT", "UNCERTAIN", "NEEDS_PRACTICE"}, context


def test_every_fixture_reproduces_against_the_live_policy(fixtures):
    pol = policy_module.load_policy()
    for row in fixtures:
        actual = policy_module.classify(pol, row["input"]["f1_probability"], row["input"]["e2_score"], row["e2_group"])
        assert actual == row["expected_state"] == row["actual_state"], (
            f"{row['context']}/{row['expected_state']}: live policy now produces {actual}"
        )


def test_no_fixture_message_uses_forbidden_wording(fixtures):
    forbidden = ("wrong", "fail", "incorrect")
    for row in fixtures:
        message = row["student_facing_message"].lower()
        assert not any(word in message for word in forbidden), row


def test_t3_to_t2_sandhi_fixture_carries_the_sandhi_rule(fixtures):
    sandhi_rows = [row for row in fixtures if row["context"] == "T3_to_T2_sandhi"]
    assert sandhi_rows
    for row in sandhi_rows:
        assert row["context_rule"] == "T3_T3"
        assert row["accepted_surface_tones"] == [2]
