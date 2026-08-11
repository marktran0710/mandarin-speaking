"""A safe THREE-STATE feedback policy combining Candidate F1's risk signal
with Candidate E2's context-aware diagnostic (frozen, unmodified components).

    python -m benchmarking.feedback_policy

**No new model is trained here.** `Candidate F1` and `Candidate E2` are
imported and called exactly as already frozen
(`benchmarking.candidates.f1_context_wav2vec`,
`benchmarking.candidates.e2_ompal_development.run_e1_e2_on_development`) --
this module only COMBINES their existing outputs into three coarser states
and chooses (development-only) the cutoffs that combination uses.
`tone_context.py` and every candidate scorer remain untouched.

## Why F1 alone cannot be the judge

Candidate F1's own development out-of-fold AUC was 0.528 and validation AUC
0.595 -- barely better than chance. A quick per-decile check of F1's
development probabilities makes the practical consequence concrete: even
the BOTTOM decile of F1 scores (the rows F1 is most "worried" about) is
still ~87% expert-correct, against an ~88% baseline rate. F1's probability
alone essentially cannot pick out a genuinely low-risk-of-error subset by
itself -- which is exactly why this policy never lets F1 alone produce a
NEEDS_PRACTICE verdict (STEP 3's explicit requirement) and why UNCERTAIN is
a large, first-class state rather than a rare fallback.

## Data provenance

- **Development**: Candidate F1's own 5-fold speaker-grouped out-of-fold
  CV probabilities (`f1_context_wav2vec.prepare_rows` +
  `run_grouped_cv(..., use_praat=False)`, i.e. the frozen F1a variant --
  re-run here read-only; deterministic, so the pooled AUC this reproduces
  (0.5276) matches `candidate_f1_development.md` to 4 decimal places).
  This is the honest, non-leaky "development" signal -- never the
  all-of-development-fitted model applied back onto its own training rows.
- **Validation**: Candidate F1 fit on ALL of development (`fit_frozen`,
  the SAME frozen procedure `f1_context_wav2vec.run()` already used) and
  applied ONCE to validation (`apply_frozen`) -- reproduces
  `candidate_f1_validation_predictions.csv`'s probabilities exactly; this
  module recomputes them (rather than reading that CSV) only because the
  CSV does not carry `syllable_index`, needed here to join against
  Candidate E2's output on the correct key.
- **Candidate E2**: `run_e1_e2_on_development` (misleadingly named for a
  module that also runs on validation -- the same function all of this
  project's prior "run E2 on split X" work already used) gives `e2_score`,
  `realization_category`, `t3_context_category`, `underlying_tone`, and the
  human label for every judged character. Never re-derived, never
  recalibrated in a way that changes an E2 SCORE -- only its ALREADY
  frozen score is thresholded here, per STEP 3's "do not change E2
  formulas."
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from benchmarking.candidates import f1_context_wav2vec as f1
from benchmarking.candidates.e2_ompal_development import run_e1_e2_on_development
from benchmarking.candidates.praat_logistic import load_split_rows, _usable

DESIGN_MD = Path("benchmarking/results/feedback_policy_design.md")
DEV_CSV = Path("benchmarking/results/feedback_policy_development.csv")
VAL_MD = Path("benchmarking/results/feedback_policy_validation.md")
VAL_CSV = Path("benchmarking/results/feedback_policy_validation.csv")
PROTOCOL_JSON = Path("benchmarking/results/feedback_policy_protocol.json")

ACCEPT = "ACCEPT"
UNCERTAIN = "UNCERTAIN"
NEEDS_PRACTICE = "NEEDS_PRACTICE"

#: E2's own score-scale audit (`candidate_e2_ompal_development.md` STEP 6)
#: already found a >60-point median spread across realization categories --
#: a single global E2 cutoff would be meaningless. "Diagnostic agreement"
#: is therefore defined PER GROUP: T1/T2/T4 group by underlying tone (their
#: shared canonical realization); T3 groups by
#: `e2_ompal_development.t3_context_category` (full_third / half_third /
#: T3_T3->T2 sandhi / chain), the same category scheme that evaluation
#: already established and reported.
def e2_group(row: dict[str, Any]) -> str:
    tone = row["underlying_tone"]
    if tone in (1, 2, 4):
        return f"T{tone}"
    return row["t3_context_category"]


# ---------------------------------------------------------------------------
# Merge Candidate F1's probability onto Candidate E2's per-character output
# ---------------------------------------------------------------------------


def _merge(f1_by_key: dict[tuple[str, str], float], e_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = []
    for row in e_rows:
        key = (row["audio_id"], row["syllable_index"])
        fp = f1_by_key.get(key)
        if fp is None or row["e2_score"] is None or row["human_majority_tone_correct"] is None:
            continue
        merged.append({**row, "f1_probability": fp, "e2_group": e2_group(row)})
    return merged


def build_development_dataset() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Returns (merged_rows, f1_dev_data, f1_dev_cv) -- the latter two kept
    around so `fit_frozen` can reuse the exact same development rows for
    the validation-time frozen fit without recomputing embeddings twice."""
    dev_data = f1.prepare_rows("development")
    cv = f1.run_grouped_cv(dev_data, use_praat=False)
    f1_by_key = {
        (row["audio_id"], row["syllable_index"]): float(p)
        for row, p in zip(dev_data["rows"], cv["oof_prob"]) if not np.isnan(p)
    }
    dev_rows_raw, _excluded = _usable(load_split_rows("development"))
    e_rows, e_diag = run_e1_e2_on_development(dev_rows_raw)
    merged = _merge(f1_by_key, e_rows)
    return merged, dev_data, cv, e_diag


def build_validation_dataset(dev_data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frozen = f1.fit_frozen(dev_data, use_praat=False)
    val_data = f1.prepare_rows("validation")
    val_prob = f1.apply_frozen(frozen, val_data, use_praat=False)
    f1_by_key = {
        (row["audio_id"], row["syllable_index"]): float(p)
        for row, p in zip(val_data["rows"], val_prob) if not np.isnan(p)
    }
    val_rows_raw, _excluded = _usable(load_split_rows("validation"))
    e_rows, e_diag = run_e1_e2_on_development(val_rows_raw)
    merged = _merge(f1_by_key, e_rows)
    return merged, e_diag


# ---------------------------------------------------------------------------
# STEP 2/3 -- policy: two F1 cutoffs (global) + one E2 cutoff per group
# ---------------------------------------------------------------------------


def compute_e2_group_cutoffs(merged_dev: list[dict[str, Any]], percentile: float) -> dict[str, float]:
    """The E2 "agreement" cutoff for one group: the `percentile`-th
    percentile of E2's OWN score among that group's EXPERT-CORRECT rows.
    A row scoring at or below this is unusually low even by the standard of
    what a CORRECT production can score in this group -- a meaningfully
    different claim than "low relative to some arbitrary global number",
    and the reason E2's agreement signal is worth anything on top of F1's
    weak one."""
    groups = sorted({row["e2_group"] for row in merged_dev})
    cutoffs: dict[str, float] = {}
    for group in groups:
        correct_scores = [
            row["e2_score"] for row in merged_dev
            if row["e2_group"] == group and row["human_majority_tone_correct"] == 1
        ]
        if correct_scores:
            cutoffs[group] = float(np.percentile(correct_scores, percentile))
    return cutoffs


def classify_row(
    row: dict[str, Any], f1_accept_min: float, f1_high_risk_max: float, e2_cutoffs: dict[str, float],
) -> str:
    fp = row["f1_probability"]
    if fp >= f1_accept_min:
        return ACCEPT
    if fp <= f1_high_risk_max:
        cutoff = e2_cutoffs.get(row["e2_group"])
        if cutoff is not None and row["e2_score"] <= cutoff:
            return NEEDS_PRACTICE
    return UNCERTAIN


def apply_policy(
    rows: list[dict[str, Any]], f1_accept_min: float, f1_high_risk_max: float, e2_cutoffs: dict[str, float],
) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        state = classify_row(row, f1_accept_min, f1_high_risk_max, e2_cutoffs)
        out.append({**row, "policy_state": state})
    return out


# ---------------------------------------------------------------------------
# STEP 6/8 -- offline evaluation
# ---------------------------------------------------------------------------


def summarize_policy(rows_with_state: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows_with_state)
    by_state: dict[str, list[dict[str, Any]]] = {ACCEPT: [], UNCERTAIN: [], NEEDS_PRACTICE: []}
    for row in rows_with_state:
        by_state[row["policy_state"]].append(row)

    def correct_rate(subset: list[dict[str, Any]]) -> float | None:
        return (sum(r["human_majority_tone_correct"] for r in subset) / len(subset)) if subset else None

    return {
        "n": n,
        "coverage": {state: len(subset) / n if n else None for state, subset in by_state.items()},
        "n_by_state": {state: len(subset) for state, subset in by_state.items()},
        "accept_expert_incorrect_rate": (
            1 - correct_rate(by_state[ACCEPT]) if by_state[ACCEPT] else None
        ),
        "needs_practice_expert_correct_rate": correct_rate(by_state[NEEDS_PRACTICE]),
        "needs_practice_expert_incorrect_rate": (
            1 - correct_rate(by_state[NEEDS_PRACTICE]) if by_state[NEEDS_PRACTICE] else None
        ),
        "uncertain_expert_correct_rate": correct_rate(by_state[UNCERTAIN]),
        "baseline_expert_correct_rate": correct_rate(rows_with_state),
    }


def summarize_by_tone(rows_with_state: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        f"T{tone}": summarize_policy([r for r in rows_with_state if r["underlying_tone"] == tone])
        for tone in (1, 2, 3, 4)
    }


T3_CATEGORY_ORDER = ("A_full_third", "B_half_third", "C_t3_t3_to_t2", "D_chain_multi_accept", "E_other_unresolved")


def summarize_by_t3_context(rows_with_state: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    t3_rows = [r for r in rows_with_state if r["underlying_tone"] == 3]
    return {
        category: summarize_policy([r for r in t3_rows if r["t3_context_category"] == category])
        for category in T3_CATEGORY_ORDER
    }


# ---------------------------------------------------------------------------
# STEP 6 -- named candidate policies (development-only sweep)
# ---------------------------------------------------------------------------

#: A small, pre-specified set of candidates -- not a grid search for the
#: "best" number, a transparent comparison of a few named, principled
#: choices along the conservative <-> permissive axis. ACCEPT's cutoff is
#: held fixed (the development median) across all candidates so the sweep
#: focuses on the safety-critical question -- how tightly to gate
#: NEEDS_PRACTICE -- rather than varying every knob at once.
CANDIDATE_POLICIES = {
    "tight": {"f1_accept_percentile": 50, "f1_high_risk_percentile": 10, "e2_agreement_percentile": 5},
    "moderate": {"f1_accept_percentile": 50, "f1_high_risk_percentile": 20, "e2_agreement_percentile": 10},
    "loose": {"f1_accept_percentile": 50, "f1_high_risk_percentile": 30, "e2_agreement_percentile": 15},
    "very_conservative": {"f1_accept_percentile": 60, "f1_high_risk_percentile": 10, "e2_agreement_percentile": 5},
}


def resolve_cutoffs(merged_dev: list[dict[str, Any]], config: dict[str, float]) -> dict[str, Any]:
    probs = np.array([row["f1_probability"] for row in merged_dev])
    f1_accept_min = float(np.percentile(probs, config["f1_accept_percentile"]))
    f1_high_risk_max = float(np.percentile(probs, config["f1_high_risk_percentile"]))
    e2_cutoffs = compute_e2_group_cutoffs(merged_dev, config["e2_agreement_percentile"])
    return {"f1_accept_min": f1_accept_min, "f1_high_risk_max": f1_high_risk_max, "e2_cutoffs": e2_cutoffs}


def simulate_candidates(merged_dev: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    results = {}
    for name, config in CANDIDATE_POLICIES.items():
        cutoffs = resolve_cutoffs(merged_dev, config)
        classified = apply_policy(merged_dev, cutoffs["f1_accept_min"], cutoffs["f1_high_risk_max"], cutoffs["e2_cutoffs"])
        results[name] = {"config": config, "cutoffs": cutoffs, "summary": summarize_policy(classified)}
    return results


#: STEP 7's frozen choice -- "moderate" from the STEP 6 sweep: smaller
#: NEEDS_PRACTICE coverage than "loose" with a comparable (not meaningfully
#: worse) expert-correct rate inside it, and meaningfully more NEEDS_PRACTICE
#: coverage than "tight"/"very_conservative" (i.e. more rows actually get a
#: useful diagnostic instead of defaulting to UNCERTAIN) -- see
#: `feedback_policy_design.md` STEP 7 for the full rationale, written from
#: the STEP 6 table alone, before validation was ever opened.
FROZEN_POLICY_NAME = "moderate"


# ---------------------------------------------------------------------------
# CSV / protocol output
# ---------------------------------------------------------------------------

ROW_FIELDS = [
    "audio_id", "speaker_id", "underlying_tone", "e2_group", "planner_rule",
    "accepted_surface_tones", "realization_category", "t3_context_category",
    "f1_probability", "e2_score", "human_majority_tone_correct", "policy_state",
]


def write_rows_csv(rows_with_state: list[dict[str, Any]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ROW_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_with_state)
    return len(rows_with_state)


def write_protocol(dev_result: dict[str, Any], path: Path = PROTOCOL_JSON) -> None:
    config = CANDIDATE_POLICIES[FROZEN_POLICY_NAME]
    cutoffs = dev_result["cutoffs"]
    protocol = {
        "policy": "three_state_feedback_policy",
        "states": [ACCEPT, UNCERTAIN, NEEDS_PRACTICE],
        "frozen_candidate_name": FROZEN_POLICY_NAME,
        "rule": {
            "f1_accept_min": cutoffs["f1_accept_min"],
            "f1_high_risk_max": cutoffs["f1_high_risk_max"],
            "e2_agreement_cutoffs_by_group": cutoffs["e2_cutoffs"],
            "logic": (
                "ACCEPT if f1_probability >= f1_accept_min. "
                "Else NEEDS_PRACTICE if f1_probability <= f1_high_risk_max "
                "AND e2_score <= e2_agreement_cutoffs_by_group[e2_group(row)]. "
                "Else UNCERTAIN."
            ),
        },
        "derivation": {
            "f1_accept_percentile_of_dev_oof_probability": config["f1_accept_percentile"],
            "f1_high_risk_percentile_of_dev_oof_probability": config["f1_high_risk_percentile"],
            "e2_agreement_percentile_of_group_expert_correct_scores": config["e2_agreement_percentile"],
            "note": "percentiles computed once on development out-of-fold data only; the resulting absolute cutoffs above are frozen and never recomputed on validation",
        },
        "components": {
            "f1": {"module": "benchmarking/candidates/f1_context_wav2vec.py", "variant": "F1a", "role": "learned pronunciation-risk signal"},
            "e2": {"module": "benchmarking/candidates/e2_ompal_development.py (via run_e1_e2_on_development)", "role": "context-aware acoustic diagnostic / pedagogical explanation", "note": "E2 formulas not modified; only its already-frozen score is thresholded"},
        },
        "development_summary": dev_result["summary"],
        "safety_principle": "NEEDS_PRACTICE requires agreement between F1 and E2; E2 never independently produces NEEDS_PRACTICE; UNCERTAIN is the default when evidence is not strong enough either way.",
        "ompal_status": "development used to derive every cutoff; validation opened exactly once, after this protocol was frozen; final_test not referenced",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run() -> dict[str, Any]:
    from benchmarking import report_feedback_policy as report

    print("Building development dataset (F1 out-of-fold + E2, merged)...")
    merged_dev, dev_data, dev_cv, e_diag_dev = build_development_dataset()
    print(f"  {len(merged_dev)} merged development rows (F1 pooled dev CV AUC={dev_cv['pooled_auc']})")

    print("STEP 6: simulating candidate policies on development...")
    candidates = simulate_candidates(merged_dev)
    for name, result in candidates.items():
        print(f"  {name}: {result['summary']['coverage']} needs_practice_expert_correct_rate={result['summary']['needs_practice_expert_correct_rate']}")

    frozen_cutoffs = resolve_cutoffs(merged_dev, CANDIDATE_POLICIES[FROZEN_POLICY_NAME])
    dev_classified = apply_policy(merged_dev, frozen_cutoffs["f1_accept_min"], frozen_cutoffs["f1_high_risk_max"], frozen_cutoffs["e2_cutoffs"])
    dev_summary = summarize_policy(dev_classified)
    dev_by_tone = summarize_by_tone(dev_classified)
    dev_by_t3 = summarize_by_t3_context(dev_classified)
    dev_result = {"cutoffs": frozen_cutoffs, "summary": dev_summary, "by_tone": dev_by_tone, "by_t3": dev_by_t3, "rows": dev_classified}

    n_dev_written = write_rows_csv(dev_classified, DEV_CSV)

    print("STEP 7: freezing policy protocol...")
    write_protocol(dev_result)

    print("STEP 8: opening validation (one-shot)...")
    merged_val, e_diag_val = build_validation_dataset(dev_data)
    print(f"  {len(merged_val)} merged validation rows")
    val_classified = apply_policy(merged_val, frozen_cutoffs["f1_accept_min"], frozen_cutoffs["f1_high_risk_max"], frozen_cutoffs["e2_cutoffs"])
    val_summary = summarize_policy(val_classified)
    val_by_tone = summarize_by_tone(val_classified)
    val_by_t3 = summarize_by_t3_context(val_classified)
    n_val_written = write_rows_csv(val_classified, VAL_CSV)

    print("Writing reports...")
    report.write_design_doc(merged_dev, candidates, dev_result, DESIGN_MD)
    recommendation = report.write_validation_report(
        {"summary": val_summary, "by_tone": val_by_tone, "by_t3": val_by_t3, "n": len(merged_val)}, VAL_MD,
    )

    return {
        "dev_result": dev_result, "candidates": candidates,
        "val_summary": val_summary, "val_by_tone": val_by_tone, "val_by_t3": val_by_t3,
        "n_dev_written": n_dev_written, "n_val_written": n_val_written,
        "recommendation": recommendation,
    }


if __name__ == "__main__":
    result = run()
    print(f"Development CSV: {DEV_CSV} ({result['n_dev_written']} rows)")
    print(f"Validation CSV: {VAL_CSV} ({result['n_val_written']} rows)")
    print(f"Protocol: {PROTOCOL_JSON}")
    print(f"Recommendation: {result['recommendation']}")
