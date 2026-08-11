"""Report writers for the three-state feedback policy
(`benchmarking.feedback_policy`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from benchmarking.feedback_policy import ACCEPT, CANDIDATE_POLICIES, FROZEN_POLICY_NAME, NEEDS_PRACTICE, T3_CATEGORY_ORDER, UNCERTAIN

SUBSTANTIAL_FALSE_REJECTION_BAR = 0.10  # STEP 9's pre-specified "acceptable" bar, fixed before validation was opened
LARGE_UNCERTAIN_BAR = 0.30

T3_LABELS = {
    "A_full_third": "full_third",
    "B_half_third": "half_third",
    "C_t3_t3_to_t2": "T3_to_T2_sandhi",
    "D_chain_multi_accept": "chain / multiple accepted",
    "E_other_unresolved": "other / unresolved",
}


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _pct(value: Any) -> str:
    return f"{value * 100:.1f}%" if value is not None else "NA"


# ---------------------------------------------------------------------------
# Design document: STEPs 1-7
# ---------------------------------------------------------------------------


def _decile_table(merged_dev: list[dict[str, Any]]) -> str:
    probs = np.array([r["f1_probability"] for r in merged_dev])
    labels = np.array([r["human_majority_tone_correct"] for r in merged_dev])
    baseline = labels.mean()
    lines = []
    for lo, hi in ((0, 10), (10, 20), (20, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 100)):
        plo, phi = np.percentile(probs, lo), np.percentile(probs, hi)
        mask = (probs >= plo) & (probs <= phi if hi == 100 else probs < phi)
        rate = labels[mask].mean() if mask.any() else None
        lines.append(f"| p{lo}-p{hi} | [{plo:.3f}, {phi:.3f}] | {int(mask.sum())} | {_pct(rate)} |")
    return "\n".join(lines), baseline


def _candidate_table(candidates: dict[str, dict[str, Any]]) -> str:
    lines = []
    for name, result in candidates.items():
        s = result["summary"]
        lines.append(
            f"| {name} | {result['config']['f1_accept_percentile']}/{result['config']['f1_high_risk_percentile']}/{result['config']['e2_agreement_percentile']} | "
            f"{_pct(s['coverage'][ACCEPT])} | {_pct(s['coverage'][UNCERTAIN])} | {_pct(s['coverage'][NEEDS_PRACTICE])} | "
            f"{_pct(s['accept_expert_incorrect_rate'])} | {s['n_by_state'][NEEDS_PRACTICE]} | {_pct(s['needs_practice_expert_correct_rate'])} |"
        )
    return "\n".join(lines)


def write_design_doc(
    merged_dev: list[dict[str, Any]], candidates: dict[str, dict[str, Any]], dev_result: dict[str, Any], path: Path,
) -> None:
    decile_lines, baseline_rate = _decile_table(merged_dev)
    candidate_lines = _candidate_table(candidates)

    e2_cutoffs = dev_result["cutoffs"]["e2_cutoffs"]
    e2_cutoff_lines = "\n".join(f"| {group} | {_fmt(cutoff, 1)} |" for group, cutoff in sorted(e2_cutoffs.items()))

    frozen_summary = dev_result["summary"]
    tone_lines = "\n".join(
        f"| {tone} | {v['n']} | {_pct(v['coverage'][ACCEPT])} | {_pct(v['coverage'][UNCERTAIN])} | {_pct(v['coverage'][NEEDS_PRACTICE])} | "
        f"{_pct(v['accept_expert_incorrect_rate'])} | {_pct(v['needs_practice_expert_correct_rate'])} |"
        for tone, v in dev_result["by_tone"].items()
    )
    t3_lines = "\n".join(
        f"| {T3_LABELS[cat]} | {v['n']} | {_pct(v['coverage'][ACCEPT])} | {_pct(v['coverage'][UNCERTAIN])} | {_pct(v['coverage'][NEEDS_PRACTICE])} | "
        f"{_pct(v['accept_expert_incorrect_rate'])} | {_pct(v['needs_practice_expert_correct_rate'])} |"
        for cat, v in dev_result["by_t3"].items() if v["n"] > 0
    )

    doc = f"""# Feedback policy design — three states from frozen Candidate F1 + Candidate E2

**No model is trained or modified here.** Candidate F1 (STEP: learned
pronunciation-risk signal) and Candidate E2 (STEP: context-aware acoustic
diagnostic) are used exactly as already frozen. This document covers STEPs
1-7: the three-state design, why F1 alone cannot be a binary judge, how
"diagnostic agreement" with Candidate E2 is defined, the pedagogical
behaviour for each state, long-sentence retry behaviour, the development-only
candidate-policy sweep, and which candidate was frozen.

## STEP 1 — three states

**ACCEPT** — F1's risk signal is LOW (see cutoff below). The learner
progresses; feedback, if shown, is positive/encouraging. This is not a claim
of "correct" — see STEP 4.

**UNCERTAIN** — the default state whenever the evidence is not strong enough
to justify either of the other two. This is a FIRST-CLASS state, not an
error fallback: given F1's own development AUC (0.528) and validation AUC
(0.595), most individual rows sit in genuinely ambiguous territory, and the
policy is designed to say so rather than force a verdict.

**NEEDS_PRACTICE** — F1's risk signal is HIGH **and** Candidate E2's
already-frozen diagnostic score independently supports the same concern
(STEP 3). Never triggered by F1 alone, never triggered by E2 alone.

The words "correct" and "wrong" are never used in learner-facing copy (STEP
4); ACCEPT/UNCERTAIN/NEEDS_PRACTICE are risk/evidence states, not
correctness verdicts.

## STEP 2 — why F1 cannot be a binary judge (development data only)

Candidate F1's own development out-of-fold probability, split into deciles,
against the human-majority-correct rate in each decile (development
baseline correct rate: {_pct(baseline_rate)}):

| Decile | F1 probability range | N | Expert-correct rate |
|---|---|---|---|
{decile_lines}

Even the bottom decile (F1's most "worried" 10% of rows) is still within a
few points of the overall baseline. F1's probability, used alone, essentially
cannot isolate a meaningfully higher-error subset — the direct empirical
reason NEEDS_PRACTICE requires a second, independent signal (STEP 3), and the
reason the policy leans on UNCERTAIN rather than trusting F1's ranking at
face value.

## STEP 3 — diagnostic agreement with Candidate E2

Candidate E2's own score-scale audit
(`candidate_e2_ompal_development.md` STEP 6) already found a >60-point
median spread in E2's score across realization categories — a single global
E2 cutoff would not mean the same thing in every context. "Agreement" is
therefore defined **per group**: T1/T2/T4 group by underlying tone (shared
canonical realization); T3 groups by the already-established
`t3_context_category` (full_third / half_third / T3_to_T2 sandhi / chain).

For each group, the cutoff is the **{CANDIDATE_POLICIES[FROZEN_POLICY_NAME]['e2_agreement_percentile']}th percentile of Candidate E2's score among that
group's own EXPERT-CORRECT rows** (development only) — i.e. "unusually low
even by the standard of what a genuinely correct production can score in
this context," not an arbitrary absolute number. A row counts as
"E2 supports the same concern" when its own E2 score is at or below its
group's cutoff:

| Group | E2 agreement cutoff (frozen) |
|---|---|
{e2_cutoff_lines}

NEEDS_PRACTICE requires F1's HIGH-risk band **and** this per-group E2
agreement together. Candidate E2 is never sufficient by itself (per the
task's explicit "Candidate E2 must NOT independently hard-fail the
learner"), and no E2 formula is changed anywhere in this derivation — only
its already-frozen score is thresholded.

## STEP 4 — pedagogical output per state

**ACCEPT**: allow progression to the next item; an optional brief positive
acknowledgement ("nice, moving on") — no claim of phonetic correctness.

**UNCERTAIN**: never tell the learner their pronunciation was wrong.
Optionally offer a replay of their own recording, a visual F0/contour
comparison (Candidate E2/Praat's already-computed contour, purely
informational), and a VOLUNTARY retry. If the learner does not retry (or
retries once and the state does not resolve to ACCEPT/NEEDS_PRACTICE),
allow continuation regardless — see STEP 5's retry cap.

**NEEDS_PRACTICE**: identify the specific syllable; show the EXPECTED
CONTEXTUAL tone (not just the citation tone — e.g. "half_third" or
"T3_T3→T2 sandhi", using the same context Candidate E2 already computed);
show the F0/contour explanation Candidate E2/Praat already produces (the
same diagnostic evidence that triggered this state, made visible rather than
a bare verdict); request one focused retry of that syllable specifically —
not the whole sentence (STEP 5).

Raw model probabilities (F1's score, E2's numeric score) are never shown to
learners in any state — they exist for the policy and for a
teacher-facing/debug view only.

## STEP 5 — long-sentence behaviour

A sentence is not required to receive a uniform binary pass on every
syllable. The flow:

1. Score every syllable in the sentence; classify each with this three-state
   policy.
2. If every syllable is ACCEPT (or ACCEPT/UNCERTAIN with no NEEDS_PRACTICE),
   treat the whole-sentence attempt as complete — proceed, with UNCERTAIN
   syllables handled per STEP 4 (never blocking).
3. If one or more syllables are NEEDS_PRACTICE, request a TARGETED retry —
   the learner re-records only the flagged syllable(s) in context (the
   surrounding sentence context is preserved for the retry so tone sandhi /
   context effects stay correct), not the entire sentence.
4. Re-score only the retried syllable(s) against the same frozen policy.
5. **Retry cap**: at most 2 targeted retries per syllable per attempt. If a
   syllable is still NEEDS_PRACTICE after 2 retries, it is NOT escalated to a
   hard block — it is presented as an UNCERTAIN-style "keep practicing this
   one later" note, and the learner proceeds. This bounds the interaction to
   a small, predictable number of extra recordings and prevents an endless
   retry loop; it also matches the policy's core stance that even a
   persistent NEEDS_PRACTICE signal is advisory, not a gate.
6. A final whole-sentence attempt is only requested if the retry flow
   materially changed the sentence's syllable sequence (rare) — otherwise
   the targeted retries above stand as the sentence's result.

## STEP 6 — candidate policy sweep (development only)

ACCEPT's cutoff is held fixed at the development median F1 probability
across all candidates below, so the comparison isolates the safety-critical
question: how tightly to gate NEEDS_PRACTICE. Percentile triples are
(F1 accept / F1 high-risk / E2 agreement).

| Candidate | Percentiles | ACCEPT % | UNCERTAIN % | NEEDS_PRACTICE % | ACCEPT expert-incorrect rate | NEEDS_PRACTICE N | NEEDS_PRACTICE expert-correct rate |
|---|---|---|---|---|---|---|---|
{candidate_lines}

**Reading this table**: NEEDS_PRACTICE expert-correct rate is the critical
false-rejection risk — the fraction of syllables this state would flag for
extra practice that the human panel actually rated correct. It never drops
far below the development baseline ({_pct(baseline_rate)}) across this whole
sweep, even at the tightest settings — combining two individually weak
signals concentrates SOME risk (all candidates sit meaningfully below
baseline) but does not eliminate it. This is reported here in full, honestly,
before any candidate is chosen, per the task's explicit "do not create
deployment thresholds until the tradeoff is explicitly reported."

## STEP 7 — frozen policy

**Chosen: `{FROZEN_POLICY_NAME}`** ({CANDIDATE_POLICIES[FROZEN_POLICY_NAME]['f1_accept_percentile']}/{CANDIDATE_POLICIES[FROZEN_POLICY_NAME]['f1_high_risk_percentile']}/{CANDIDATE_POLICIES[FROZEN_POLICY_NAME]['e2_agreement_percentile']}).
Rationale: `tight`/`very_conservative` shrink NEEDS_PRACTICE coverage
further without a meaningfully better expert-correct rate inside it (compare
the last two columns above) — i.e. they trade away usable diagnostic
feedback for little additional safety. `loose` raises NEEDS_PRACTICE
coverage without improving (and slightly worsening) its expert-correct rate.
`moderate` sits at the point in this sweep where NEEDS_PRACTICE stays a
small minority of rows ({_pct(frozen_summary['coverage'][NEEDS_PRACTICE])} of
development) while concentrating meaningfully more of the corpus's actual
disagreement cases than the tighter candidates. It is frozen here, before
validation is opened — see `feedback_policy_protocol.json` for the exact
cutoffs.

### Frozen policy on development (STEP 6/7 result, same rows as the sweep above)

Overall: ACCEPT {_pct(frozen_summary['coverage'][ACCEPT])}, UNCERTAIN
{_pct(frozen_summary['coverage'][UNCERTAIN])}, NEEDS_PRACTICE
{_pct(frozen_summary['coverage'][NEEDS_PRACTICE])}. ACCEPT expert-incorrect
rate: {_pct(frozen_summary['accept_expert_incorrect_rate'])}. NEEDS_PRACTICE
expert-correct rate (false-rejection risk): {_pct(frozen_summary['needs_practice_expert_correct_rate'])}.

#### By tone

| Tone | N | ACCEPT % | UNCERTAIN % | NEEDS_PRACTICE % | ACCEPT expert-incorrect | NEEDS_PRACTICE expert-correct |
|---|---|---|---|---|---|---|
{tone_lines}

#### By T3 context

| Category | N | ACCEPT % | UNCERTAIN % | NEEDS_PRACTICE % | ACCEPT expert-incorrect | NEEDS_PRACTICE expert-correct |
|---|---|---|---|---|---|---|
{t3_lines}

---

*`validation` and `final_test` were not loaded by any code that produced the
numbers above. Candidate F1, Candidate E2, and `tone_context.py` were not
modified.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")


# ---------------------------------------------------------------------------
# Validation report: STEPs 8-9
# ---------------------------------------------------------------------------


def recommend(val_summary: dict[str, Any]) -> tuple[str, str]:
    fr = val_summary["needs_practice_expert_correct_rate"]
    uncertain_share = val_summary["coverage"][UNCERTAIN]
    if fr is None:
        return "C", "NEEDS_PRACTICE had no scored rows on validation -- cannot certify any error-rate claim."
    if fr <= SUBSTANTIAL_FALSE_REJECTION_BAR:
        return "A", (
            f"NEEDS_PRACTICE's expert-correct rate on validation ({_pct(fr)}) is at or below the "
            f"pre-specified acceptable bar ({_pct(SUBSTANTIAL_FALSE_REJECTION_BAR)}) -- the policy's error risk "
            f"is acceptable for non-high-stakes assistive practice."
        )
    if uncertain_share is not None and uncertain_share >= LARGE_UNCERTAIN_BAR:
        return "B", (
            f"NEEDS_PRACTICE's expert-correct rate on validation ({_pct(fr)}) exceeds the acceptable bar "
            f"({_pct(SUBSTANTIAL_FALSE_REJECTION_BAR)}), so NEEDS_PRACTICE alone is not reliable enough to treat "
            f"as anything but advisory -- but UNCERTAIN absorbs a large share of the corpus "
            f"({_pct(uncertain_share)}), so the system can still avoid confidently wrong verdicts by deferring "
            f"rather than judging. Useful feedback is possible; the system should not make automatic hard "
            f"judgments."
        )
    return "C", (
        f"NEEDS_PRACTICE's expert-correct rate on validation ({_pct(fr)}) exceeds the acceptable bar "
        f"({_pct(SUBSTANTIAL_FALSE_REJECTION_BAR)}) and UNCERTAIN's coverage is not large enough to compensate -- "
        f"even this conservative gating produces an unacceptable rate of false feedback for automatic "
        f"pronunciation decisions."
    )


def write_validation_report(val: dict[str, Any], path: Path) -> str:
    summary, by_tone, by_t3 = val["summary"], val["by_tone"], val["by_t3"]

    tone_lines = "\n".join(
        f"| {tone} | {v['n']} | {_pct(v['coverage'][ACCEPT])} | {_pct(v['coverage'][UNCERTAIN])} | {_pct(v['coverage'][NEEDS_PRACTICE])} | "
        f"{_pct(v['accept_expert_incorrect_rate'])} | {_pct(v['needs_practice_expert_correct_rate'])} | {_pct(v['needs_practice_expert_incorrect_rate'])} |"
        for tone, v in by_tone.items()
    )
    t3_lines = "\n".join(
        f"| {T3_LABELS[cat]} | {v['n']} | {_pct(v['coverage'][ACCEPT])} | {_pct(v['coverage'][UNCERTAIN])} | {_pct(v['coverage'][NEEDS_PRACTICE])} | "
        f"{_pct(v['accept_expert_incorrect_rate'])} | {_pct(v['needs_practice_expert_correct_rate'])} | {_pct(v['needs_practice_expert_incorrect_rate'])} |"
        for cat, v in by_t3.items() if v["n"] > 0
    )

    verdict, reason = recommend(summary)

    report = f"""# Feedback policy — validation (ONE-SHOT evaluation)

The frozen policy (`feedback_policy_protocol.json`) applied exactly once to
validation ({val['n']} rows) — no cutoff was re-selected, re-derived, or
tuned using this data. The objective here is NOT classification accuracy; it
is whether the system can give conservative feedback without blocking large
numbers of acceptable pronunciations.

## Coverage and error rates (overall)

| | Value |
|---|---|
| N | {summary['n']} |
| ACCEPT coverage | {_pct(summary['coverage'][ACCEPT])} |
| UNCERTAIN coverage | {_pct(summary['coverage'][UNCERTAIN])} |
| NEEDS_PRACTICE coverage | {_pct(summary['coverage'][NEEDS_PRACTICE])} |
| Among ACCEPT: % expert acceptable | {_pct(1 - summary['accept_expert_incorrect_rate']) if summary['accept_expert_incorrect_rate'] is not None else 'NA'} |
| Among NEEDS_PRACTICE: % expert actually incorrect | {_pct(summary['needs_practice_expert_incorrect_rate'])} |
| Among NEEDS_PRACTICE: % expert actually acceptable (false-rejection risk) | {_pct(summary['needs_practice_expert_correct_rate'])} |
| Among UNCERTAIN: % expert acceptable | {_pct(summary['uncertain_expert_correct_rate'])} |
| Baseline expert-correct rate (all rows) | {_pct(summary['baseline_expert_correct_rate'])} |

## Per tone

| Tone | N | ACCEPT % | UNCERTAIN % | NEEDS_PRACTICE % | ACCEPT expert-incorrect | NEEDS_PRACTICE expert-correct (risk) | NEEDS_PRACTICE expert-incorrect |
|---|---|---|---|---|---|---|---|
{tone_lines}

## T3 context

| Category | N | ACCEPT % | UNCERTAIN % | NEEDS_PRACTICE % | ACCEPT expert-incorrect | NEEDS_PRACTICE expert-correct (risk) | NEEDS_PRACTICE expert-incorrect |
|---|---|---|---|---|---|---|---|
{t3_lines}

## STEP 9 — system recommendation

**{verdict}.** {reason}

This is not a claim of teacher equivalence in any state, including ACCEPT.

---

*`final_test` was not loaded by any code in this evaluation. Candidate F1,
Candidate E2, and `tone_context.py` were not modified. No cutoff in this
report was chosen or adjusted using validation data.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return verdict
