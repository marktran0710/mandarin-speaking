"""STEP 8: build the manual pilot fixture set.

    python -m assistive_feedback.build_pilot_fixtures

Six tone contexts (T1, T2, T3 full_third, T3 half_third, T3->T2 sandhi, T4)
x three policy states (ACCEPT/UNCERTAIN/NEEDS_PRACTICE) = 18 fixture rows.
Each row uses a REAL `tone_context.plan_expected_tones` result (never a
hand-typed stand-in for what the planner would decide) and the frozen
policy's REAL cutoffs (`feedback_policy_protocol.json`, read-only) --
only the synthetic F1 probability / E2 score inputs are chosen by hand, to
land deliberately in the target state, and then VERIFIED by actually
calling `assistive_feedback.policy.classify` rather than asserted by
comment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from assistive_feedback import policy as policy_module
from tone_context import han_break_flags, plan_expected_tones

FIXTURES_PATH = Path("tests/fixtures/assistive_feedback_pilot_fixtures.json")


def _plan(chars: list[str], underlying: list[int], token_indices: list[int] | None = None):
    text = "".join(chars)
    if token_indices is None:
        token_indices = [0] * len(chars)
    return plan_expected_tones(list(chars), underlying, token_indices, han_break_flags(text))


def build() -> list[dict[str, Any]]:
    pol = policy_module.load_policy()

    contexts = {
        "T1": (_plan(["他"], [1])[0], "T1"),
        "T2": (_plan(["麻"], [2])[0], "T2"),
        "T3_full_third": (_plan(["馬"], [3])[0], "A_full_third"),
        "T3_half_third": (_plan(["馬", "天"], [3, 1])[0], "B_half_third"),
        "T3_to_T2_sandhi": (_plan(["馬", "好"], [3, 3])[0], "C_t3_t3_to_t2"),
        "T4": (_plan(["罵"], [4])[0], "T4"),
    }

    fixtures: list[dict[str, Any]] = []
    for context_name, (expected, group) in contexts.items():
        e2_cutoff = pol.e2_cutoffs.get(group, 50.0)

        # ACCEPT: F1 confidently low-risk. E2 value is irrelevant here (the
        # rule short-circuits on the F1 accept band) -- kept mid-range so
        # the fixture is not accidentally testing two things at once.
        accept_f1 = min(0.99, pol.f1_accept_min + 0.1)
        # NEEDS_PRACTICE: F1 confidently high-risk AND E2 agrees (at/below
        # its group's frozen cutoff).
        needs_practice_f1 = max(0.01, pol.f1_high_risk_max - 0.1)
        needs_practice_e2 = max(0.0, e2_cutoff - 5.0)
        # UNCERTAIN: F1 sits in the middle band -- neither threshold fires,
        # regardless of E2.
        uncertain_f1 = (pol.f1_accept_min + pol.f1_high_risk_max) / 2

        for label, f1_probability, e2_score in (
            ("ACCEPT", accept_f1, e2_cutoff + 20.0),
            ("UNCERTAIN", uncertain_f1, e2_cutoff + 20.0),
            ("NEEDS_PRACTICE", needs_practice_f1, needs_practice_e2),
        ):
            actual_state = policy_module.classify(pol, f1_probability, e2_score, group)
            fixtures.append({
                "context": context_name,
                "character": expected.char,
                "underlying_tone": expected.underlying_tone,
                "accepted_surface_tones": list(expected.accepted_surface_tones),
                "realization": expected.realization,
                "context_rule": expected.rule,
                "e2_group": group,
                "input": {"f1_probability": round(f1_probability, 4), "e2_score": round(e2_score, 2)},
                "expected_state": label,
                "actual_state": actual_state,
                "student_facing_label": policy_module.STUDENT_FACING_NAME[actual_state],
                "student_facing_message": policy_module.STUDENT_FACING_MESSAGE[actual_state],
            })
            assert actual_state == label, (
                f"fixture design error: {context_name}/{label} produced {actual_state} instead"
            )

    return fixtures


def write(fixtures: list[dict[str, Any]], path: Path = FIXTURES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    fixtures = build()
    write(fixtures)
    print(f"{len(fixtures)} fixtures written to {FIXTURES_PATH} (all verified against the real frozen policy)")
