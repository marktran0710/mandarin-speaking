"""The frozen three-state policy, loaded from `feedback_policy_protocol.json`
(never re-derived, never re-thresholded here). Internal state names match
that protocol file exactly, for direct comparability with the offline
validation numbers; student-facing names are a presentation-layer mapping
only (STEP 1 of `assistive_feedback_design.md`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tone_context import ExpectedTone, HALF_THIRD, THIRD_CHAIN, THIRD_SANDHI

PROTOCOL_PATH = Path("benchmarking/results/feedback_policy_protocol.json")

ACCEPT = "ACCEPT"
UNCERTAIN = "UNCERTAIN"
NEEDS_PRACTICE = "NEEDS_PRACTICE"

#: STEP 1 of `assistive_feedback_design.md` / this task's STEP 4 wording.
STUDENT_FACING_NAME = {
    ACCEPT: "NO_ISSUE_DETECTED",
    UNCERTAIN: "NO_AUTOMATIC_JUDGMENT",
    NEEDS_PRACTICE: "CHECK_THIS_TONE",
}
STUDENT_FACING_MESSAGE = {
    ACCEPT: "No pronunciation issue was detected.",
    UNCERTAIN: "The system is not confident enough to judge this tone automatically.",
    NEEDS_PRACTICE: "This tone may be worth checking.",
}


#: Reproduces `e2_ompal_development._t3_context_category` /
#: `benchmarking.feedback_policy.e2_group` exactly, without importing either
#: module's heavier OMPAL-corpus dependencies into the live request path.
#: This is a LABEL used only to select which frozen E2 cutoff applies -- it
#: does not decide any linguistic rule; `tone_context.ExpectedTone` (imported
#: read-only) already made that decision.
def e2_group(expected: ExpectedTone) -> str:
    tone = expected.underlying_tone
    if tone in (1, 2, 4):
        return f"T{tone}"
    if tone != 3:
        return "E_other_unresolved"
    if expected.realization == "full_third":
        return "A_full_third"
    if expected.realization == HALF_THIRD:
        return "B_half_third"
    if expected.realization == THIRD_SANDHI and expected.accepted_surface_tones == (2,):
        return "C_t3_t3_to_t2"
    if expected.realization == THIRD_CHAIN or len(expected.accepted_surface_tones) > 1:
        return "D_chain_multi_accept"
    return "E_other_unresolved"


@dataclass(frozen=True)
class Policy:
    f1_accept_min: float
    f1_high_risk_max: float
    e2_cutoffs: dict[str, float]
    metadata: dict[str, Any]


def load_policy(path: Path = PROTOCOL_PATH) -> Policy:
    protocol = json.loads(path.read_text(encoding="utf-8"))
    rule = protocol["rule"]
    return Policy(
        f1_accept_min=rule["f1_accept_min"],
        f1_high_risk_max=rule["f1_high_risk_max"],
        e2_cutoffs=dict(rule["e2_agreement_cutoffs_by_group"]),
        metadata=protocol,
    )


def classify(policy: Policy, f1_probability: float | None, e2_score: float | None, group: str) -> str:
    """The frozen rule, verbatim from `benchmarking.feedback_policy.classify_row`:
    ACCEPT if F1 risk is low; else NEEDS_PRACTICE only if F1 risk is high
    AND Candidate E2 independently agrees for this group; else UNCERTAIN.
    Missing inputs (F1 or E2 unavailable) always fall through to UNCERTAIN --
    the safe default -- never to NEEDS_PRACTICE."""
    if f1_probability is None or e2_score is None:
        return UNCERTAIN
    if f1_probability >= policy.f1_accept_min:
        return ACCEPT
    if f1_probability <= policy.f1_high_risk_max:
        cutoff = policy.e2_cutoffs.get(group)
        if cutoff is not None and e2_score <= cutoff:
            return NEEDS_PRACTICE
    return UNCERTAIN
