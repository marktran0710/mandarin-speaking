"""Report writers for Candidate E2's first OMPAL development evaluation.

Reads only the `master` row list `e2_ompal_development.run()` already
computed (nothing here re-scores anything); slices it into the STEP 2-9
tables the task specified and renders the STEP 10 decision from a rule fixed
in this module BEFORE any of the numbers below were computed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from benchmarking.candidates.e2_ompal_development import (
    COMPARISON_MD,
    FIXED_THRESHOLD,
    REPORT_MD,
    T3_CATEGORY_LABELS,
    _auc_for,
    _binary_for,
    _human_correct_rate,
    score_distribution,
)
from benchmarking.stats import roc_auc

#: Same bar `compare_abc.py`'s pre-existing decision rule already used for
#: Candidate B1/C1 ("substantial" pooled AUC). Reused here, not re-derived,
#: so "substantial discrimination" means the same thing across every
#: candidate report in this project.
SUBSTANTIAL_AUC_BAR = 0.65
#: STEP 10's pre-specified "meaningful per-category gain" bar: Candidate E2
#: must beat Candidate E V1's OWN AUC in at least one of its two target T3
#: categories (half_third, T3_T3->T2) by this much, measured on the same
#: rows, before its architecture change counts as having transferred to real
#: speech. Fixed here, before any of STEP 4's numbers were computed.
CATEGORY_GAIN_BAR = 0.05
#: STEP 10's pre-specified "scale masks real discrimination" bar: how much
#: higher the unweighted macro-average of per-branch AUCs must sit above the
#: single pooled AUC before the gap is attributed to incomparable branch
#: score scales rather than noise.
SCALE_MASK_GAP = 0.10
#: STEP 6's pre-specified "one common scale is plausible" bar: the spread
#: between the highest and lowest median E2 score across realization
#: categories with N >= 5. The controlled-data score-scale audit
#: (`candidate_e2_controlled_test.md`) found a >25-point spread and called
#: that incompatible; 15 points is set here, before this task's own numbers
#: were computed, as a deliberately more conservative (stricter) bar for
#: real speech, where within-category noise is higher than controlled audio.
SCALE_COMPARABLE_SPREAD = 15.0
MIN_CATEGORY_N = 5


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _scored(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r["e2_score"] is not None and r["human_majority_tone_correct"] is not None]


# ---------------------------------------------------------------------------
# STEP 2 -- pooled comparison, A vs B1 vs C1 vs E1 vs E2
# ---------------------------------------------------------------------------


def pooled_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labeled = [r for r in rows if r["human_majority_tone_correct"] is not None]

    def model_block(score_key: str, pass_key: str | None) -> dict[str, Any]:
        scores = [r[score_key] for r in labeled]
        labels = [r["human_majority_tone_correct"] for r in labeled]
        block: dict[str, Any] = {"auc": _auc_for(scores, labels)}
        if pass_key is not None:
            preds = [r.get(pass_key) for r in labeled]
            block.update(_binary_for(preds, labels))
        return block

    return {
        "n_labeled": len(labeled),
        "baseline_a": model_block("baseline_a_score", "baseline_a_pass"),
        "b1": model_block("b1_probability", "b1_pass"),
        "c1": model_block("c1_probability", "c1_pass"),
        "e1": model_block("e1_score", "e1_pass"),
        "e2": model_block("e2_score", None),
    }


# ---------------------------------------------------------------------------
# STEP 3 -- E2 stratified by underlying tone
# ---------------------------------------------------------------------------


def per_tone_table(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for tone in (1, 2, 3, 4):
        subset = _scored([r for r in rows if r["underlying_tone"] == tone])
        correct = [r["e2_score"] for r in subset if r["human_majority_tone_correct"] == 1]
        incorrect = [r["e2_score"] for r in subset if r["human_majority_tone_correct"] == 0]
        result[str(tone)] = {
            "n": len(subset),
            "human_correct_rate": _human_correct_rate(subset),
            "auc": _auc_for([r["e2_score"] for r in subset], [r["human_majority_tone_correct"] for r in subset]),
            "median_correct": float(np.median(correct)) if correct else None,
            "median_incorrect": float(np.median(incorrect)) if incorrect else None,
        }
    return result


# ---------------------------------------------------------------------------
# STEP 4 -- T3 context stratification: E V1 vs E2, within the same categories
# ---------------------------------------------------------------------------


def t3_context_table(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for category in T3_CATEGORY_LABELS:
        subset = [r for r in rows if r["t3_context_category"] == category and r["human_majority_tone_correct"] is not None]
        subset_e2 = [r for r in subset if r["e2_score"] is not None]
        subset_e1 = [r for r in subset if r["e1_score"] is not None]
        result[category] = {
            "n": len(subset),
            "human_correct_rate": _human_correct_rate(subset),
            "e2_auc": _auc_for([r["e2_score"] for r in subset_e2], [r["human_majority_tone_correct"] for r in subset_e2]),
            "e1_auc": _auc_for([r["e1_score"] for r in subset_e1], [r["human_majority_tone_correct"] for r in subset_e1]),
            "e1_binary": _binary_for([r["e1_pass"] for r in subset_e1], [r["human_majority_tone_correct"] for r in subset_e1]),
            "e2_score_distribution": score_distribution([r["e2_score"] for r in subset_e2]),
        }
    return result


# ---------------------------------------------------------------------------
# STEP 5 -- full_third / phrase-final limitation, quantified not fixed
# ---------------------------------------------------------------------------


def phrase_final_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    full_third = [r for r in rows if r["realization_category"] == "full_third" and r["human_majority_tone_correct"] is not None]
    final_rows = [r for r in full_third if r.get("utterance_final") or r.get("boundary_after")]
    nonfinal_rows = [r for r in full_third if not (r.get("utterance_final") or r.get("boundary_after"))]

    def block(subset: list[dict[str, Any]]) -> dict[str, Any]:
        e2_sub = [r for r in subset if r["e2_score"] is not None]
        e1_sub = [r for r in subset if r["e1_score"] is not None]
        return {
            "n": len(subset),
            "human_correct_rate": _human_correct_rate(subset),
            "e1_auc": _auc_for([r["e1_score"] for r in e1_sub], [r["human_majority_tone_correct"] for r in e1_sub]),
            "e2_auc": _auc_for([r["e2_score"] for r in e2_sub], [r["human_majority_tone_correct"] for r in e2_sub]),
            "e1_binary": _binary_for([r["e1_pass"] for r in e1_sub], [r["human_majority_tone_correct"] for r in e1_sub]),
            "e2_score_distribution": score_distribution([r["e2_score"] for r in e2_sub]),
        }

    return {
        "all_full_third": block(full_third),
        "phrase_final": block(final_rows),
        "non_final": block(nonfinal_rows),
    }


# ---------------------------------------------------------------------------
# STEP 6 -- score-scale compatibility across realization categories
# ---------------------------------------------------------------------------


def score_scale_by_category(rows: list[dict[str, Any]]) -> dict[str, Any]:
    categories = {
        "T1": [r for r in rows if r["underlying_tone"] == 1],
        "T2": [r for r in rows if r["underlying_tone"] == 2],
        "T4": [r for r in rows if r["underlying_tone"] == 4],
        "full_third_T3": [r for r in rows if r["realization_category"] == "full_third"],
        "half_third_T3": [r for r in rows if r["realization_category"] == "half_third"],
        "T3_to_T2_sandhi": [r for r in rows if r["t3_context_category"] == "C_t3_t3_to_t2"],
        "T3_chain_multi_accept": [r for r in rows if r["t3_context_category"] == "D_chain_multi_accept"],
    }
    distributions = {
        name: score_distribution([r["e2_score"] for r in subset if r["e2_score"] is not None])
        for name, subset in categories.items()
    }
    medians = [d["median"] for d in distributions.values() if d["n"] >= MIN_CATEGORY_N and d["median"] is not None]
    spread = (max(medians) - min(medians)) if len(medians) >= 2 else None
    answer = (
        "A" if spread is not None and spread < SCALE_COMPARABLE_SPREAD
        else "B" if spread is not None
        else None
    )
    return {"distributions": distributions, "median_spread": spread, "answer": answer}


# ---------------------------------------------------------------------------
# STEP 7 -- within-branch discrimination + macro-average
# ---------------------------------------------------------------------------


def within_branch_discrimination(rows: list[dict[str, Any]], pooled_auc: float | None) -> dict[str, Any]:
    scored = _scored(rows)
    per_tone = {
        str(tone): _auc_for(
            [r["e2_score"] for r in scored if r["underlying_tone"] == tone],
            [r["human_majority_tone_correct"] for r in scored if r["underlying_tone"] == tone],
        )
        for tone in (1, 2, 3, 4)
    }
    per_category: dict[str, Any] = {}
    for tone in (1, 2, 4):
        subset = [r for r in scored if r["underlying_tone"] == tone]
        per_category[f"T{tone}"] = {"n": len(subset), "auc": _auc_for(
            [r["e2_score"] for r in subset], [r["human_majority_tone_correct"] for r in subset]
        )}
    for category in T3_CATEGORY_LABELS:
        subset = [r for r in scored if r["t3_context_category"] == category]
        per_category[T3_CATEGORY_LABELS[category]] = {"n": len(subset), "auc": _auc_for(
            [r["e2_score"] for r in subset], [r["human_majority_tone_correct"] for r in subset]
        )}

    eligible = {k: v for k, v in per_category.items() if v["n"] >= MIN_CATEGORY_N and v["auc"] is not None}
    unweighted = float(np.mean([v["auc"] for v in eligible.values()])) if eligible else None
    total_n = sum(v["n"] for v in eligible.values())
    weighted = (
        float(sum(v["auc"] * v["n"] for v in eligible.values()) / total_n) if eligible and total_n else None
    )

    return {
        "pooled_auc": pooled_auc,
        "per_tone_auc": per_tone,
        "per_category": per_category,
        "macro_avg_unweighted": unweighted,
        "macro_avg_weighted": weighted,
        "n_eligible_categories": len(eligible),
    }


# ---------------------------------------------------------------------------
# STEP 8 -- high-confidence subset
# ---------------------------------------------------------------------------


def high_confidence_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    subset = _scored([r for r in rows if r.get("high_confidence_subset")])
    return {
        "n": len(subset),
        "human_correct_rate": _human_correct_rate(subset),
        "e2_auc": _auc_for([r["e2_score"] for r in subset], [r["human_majority_tone_correct"] for r in subset]),
        "e1_auc": _auc_for(
            [r["e1_score"] for r in subset if r["e1_score"] is not None],
            [r["human_majority_tone_correct"] for r in subset if r["e1_score"] is not None],
        ),
    }


# ---------------------------------------------------------------------------
# STEP 10 -- decision, from the rule fixed at the top of this module
# ---------------------------------------------------------------------------


def render_decision(
    pooled: dict[str, Any], t3_table: dict[str, dict[str, Any]], branch: dict[str, Any]
) -> tuple[str, str]:
    pooled_e2_auc = pooled["e2"]["auc"]
    half_third = t3_table["B_half_third"]
    t3t3 = t3_table["C_t3_t3_to_t2"]

    def delta(cat: dict[str, Any]) -> float | None:
        if cat["e2_auc"] is None or cat["e1_auc"] is None:
            return None
        return cat["e2_auc"] - cat["e1_auc"]

    delta_half_third = delta(half_third)
    delta_t3t3 = delta(t3t3)
    category_gain = (
        (delta_half_third is not None and delta_half_third >= CATEGORY_GAIN_BAR)
        or (delta_t3t3 is not None and delta_t3t3 >= CATEGORY_GAIN_BAR)
    )

    macro = branch["macro_avg_unweighted"]
    scale_masks = (
        pooled_e2_auc is not None and macro is not None
        and macro >= SUBSTANTIAL_AUC_BAR
        and (macro - pooled_e2_auc) >= SCALE_MASK_GAP
        and (pooled_e2_auc < SUBSTANTIAL_AUC_BAR)
    )

    pooled_strong = pooled_e2_auc is not None and pooled_e2_auc >= SUBSTANTIAL_AUC_BAR

    if scale_masks:
        verdict = "D"
        reason = (
            f"Per-branch macro-average AUC ({_fmt(macro)}) sits >= {SCALE_MASK_GAP:.2f} above the pooled "
            f"AUC ({_fmt(pooled_e2_auc)}) and itself clears the substantial bar "
            f"({SUBSTANTIAL_AUC_BAR:.2f}) while pooled does not -- within-branch discrimination looks "
            f"real, but branch score scales are not comparable enough for the pooled number to be trusted."
        )
    elif category_gain and pooled_strong:
        verdict = "A"
        reason = (
            f"Candidate E2 beats Candidate E V1's own AUC by >= {CATEGORY_GAIN_BAR:.2f} in at least one "
            f"target category (half_third delta={_fmt(delta_half_third)}, T3_T3->T2 delta={_fmt(delta_t3t3)}) "
            f"AND the pooled AUC ({_fmt(pooled_e2_auc)}) clears the substantial bar ({SUBSTANTIAL_AUC_BAR:.2f})."
        )
    elif category_gain:
        verdict = "B"
        reason = (
            f"Candidate E2 beats Candidate E V1's own AUC by >= {CATEGORY_GAIN_BAR:.2f} in at least one "
            f"target category (half_third delta={_fmt(delta_half_third)}, T3_T3->T2 delta={_fmt(delta_t3t3)}), "
            f"but the pooled AUC ({_fmt(pooled_e2_auc)}) does not clear the substantial bar "
            f"({SUBSTANTIAL_AUC_BAR:.2f})."
        )
    else:
        verdict = "C"
        reason = (
            f"Neither target category shows a >= {CATEGORY_GAIN_BAR:.2f} AUC gain over Candidate E V1 "
            f"(half_third delta={_fmt(delta_half_third)}, T3_T3->T2 delta={_fmt(delta_t3t3)}) -- the "
            f"controlled-data improvement does not show up against real learner speech in this evaluation."
        )
    return verdict, reason


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _metric_row(label: str, block: dict[str, Any], keys: list[tuple[str, str]]) -> str:
    cells = " | ".join(_fmt(block.get(key)) for key, _ in keys)
    return f"| {label} | {cells} |"


def write_development_report(result: dict[str, Any], path: Path = REPORT_MD) -> str:
    master = result["master"]
    e_diag = result["e_diag"]
    scored = _scored(master)

    per_tone = per_tone_table(master)
    t3_table = t3_context_table(master)
    phrase_final = phrase_final_analysis(master)
    scale = score_scale_by_category(master)
    pooled = pooled_comparison(master)
    branch = within_branch_discrimination(master, pooled["e2"]["auc"])
    high_conf = high_confidence_summary(master)
    verdict, reason = render_decision(pooled, t3_table, branch)

    per_tone_lines = "\n".join(
        f"| T{tone} | {v['n']} | {_fmt(v['human_correct_rate'])} | {_fmt(v['auc'])} | "
        f"{_fmt(v['median_correct'])} | {_fmt(v['median_incorrect'])} |"
        for tone, v in per_tone.items()
    )

    t3_lines = "\n".join(
        f"| {T3_CATEGORY_LABELS[cat]} | {v['n']} | {_fmt(v['human_correct_rate'])} | "
        f"{_fmt(v['e1_auc'])} | {_fmt(v['e2_auc'])} | "
        f"{_fmt(v['e1_binary'].get('false_rejection_rate'))} | "
        f"{_fmt(v['e2_score_distribution']['median'])} "
        f"({_fmt(v['e2_score_distribution']['min'])}-{_fmt(v['e2_score_distribution']['max'])}) |"
        for cat, v in t3_table.items()
    )

    pf = phrase_final
    phrase_final_lines = "\n".join(
        f"| {name} | {b['n']} | {_fmt(b['human_correct_rate'])} | {_fmt(b['e1_auc'])} | {_fmt(b['e2_auc'])} | "
        f"{_fmt(b['e1_binary'].get('false_rejection_rate'))} | "
        f"{_fmt(b['e2_score_distribution']['median'])} |"
        for name, b in (("all full_third", pf["all_full_third"]), ("phrase-final / boundary", pf["phrase_final"]),
                        ("non-final", pf["non_final"]))
    )

    scale_lines = "\n".join(
        f"| {name} | {d['n']} | {_fmt(d['min'])} | {_fmt(d['median'])} | {_fmt(d['max'])} |"
        for name, d in scale["distributions"].items()
    )

    branch_lines = "\n".join(
        f"| {name} | {v['n']} | {_fmt(v['auc'])} |"
        for name, v in branch["per_category"].items()
    )

    report = f"""# Candidate E2 — first OMPAL evaluation (DEVELOPMENT split)

**Candidate E2 and Candidate E V1 remain frozen.** `tone_context.py` was not
modified. No threshold was tuned in this evaluation: Baseline A / Candidate
E V1 keep the pre-existing fixed 58; Candidate B1/C1 keep their own
already-frozen dev-only threshold-selection rule; Candidate E2 has NO
threshold anywhere below — every E2 number is an AUC or a raw score
distribution. `validation` and `final_test` were not loaded.

## STEP 1 — extraction summary

{e_diag['utterances_ok']} / {e_diag['utterances_total']} utterances produced
usable alignment; {e_diag['rows_scored']} of {result['dev_n']} development
rows were scored by both Candidate E V1 and Candidate E2 for the first time
against real OMPAL audio ({e_diag['rows_excluded']} excluded — see the
`e2_exclusion_reason` column in `candidate_e2_development_predictions.csv`
for why each one was dropped: {e_diag['utterances_not_found']} utterances not
found in the corpus loader, {e_diag['utterances_plan_failed']} utterances
where `tone_context.plan_expected_tones` could not be computed,
{e_diag['utterances_audio_load_error']} audio load errors,
{e_diag['utterances_span_unavailable']} utterances where the aligner could
not produce one span per character). {e_diag['rows_span_duration_mismatch']}
rows showed a re-derived span duration differing from the cached
`duration_seconds` by more than 5ms (should be ~0 — the same deterministic
aligner function is called on the same audio; a non-zero count here would
flag a real reproducibility problem).

Candidate C1's development embedding cache covered
{result['dev_n'] - result['c1_missing_embeddings']}/{result['dev_n']} rows
({result['c1_missing_embeddings']} missing).

## STEP 3 — Candidate E2 stratified by underlying tone

| Tone | N | Human-correct rate | AUC | Score median (human-correct) | Score median (human-incorrect) |
|---|---|---|---|---|---|
{per_tone_lines}

## STEP 4 — T3 context stratification: Candidate E V1 vs Candidate E2

Candidate E2 was designed to concentrate its gain in categories B
(half_third) and C (T3_T3 -> surface T2). `E1 false rejection rate` uses E V1's
pre-existing fixed threshold of 58 (a real, already-frozen verdict); Candidate
E2 has no such threshold, so its column is AUC and score distribution only.

| T3 context category | N | Human-correct rate | E V1 AUC | E2 AUC | E V1 false rejection rate | E2 score median (range) |
|---|---|---|---|---|---|---|
{t3_lines}

**Gain concentration check (STEP 10's decision rule):** half_third AUC delta
(E2 - E V1) = {_fmt(t3_table['B_half_third']['e2_auc'] - t3_table['B_half_third']['e1_auc']) if t3_table['B_half_third']['e2_auc'] is not None and t3_table['B_half_third']['e1_auc'] is not None else 'NA'};
T3_T3->T2 AUC delta = {_fmt(t3_table['C_t3_t3_to_t2']['e2_auc'] - t3_table['C_t3_t3_to_t2']['e1_auc']) if t3_table['C_t3_t3_to_t2']['e2_auc'] is not None and t3_table['C_t3_t3_to_t2']['e1_auc'] is not None else 'NA'}.

## STEP 5 — full_third / phrase-final limitation (quantified, not fixed)

Candidate E2's protocol already discloses that `full_third` (isolated and
phrase-final) T3 inherits Candidate E V1's unresolved formula unchanged. This
section quantifies that limitation on real speech; **no formula was changed**.

| Subset | N | Human-correct rate | E V1 AUC | E2 AUC | E V1 false rejection rate | E2 score median |
|---|---|---|---|---|---|---|
{phrase_final_lines}

## STEP 6 — score-scale compatibility across realization categories

| Category | N | Min | Median | Max |
|---|---|---|---|---|
{scale_lines}

Median spread across categories with N >= {MIN_CATEGORY_N}:
**{_fmt(scale['median_spread'])} points**. Answer (bar: < {SCALE_COMPARABLE_SPREAD:.0f}
points = A, otherwise B, fixed before this number was computed):
**{scale['answer'] or 'NA (insufficient categories with N >= ' + str(MIN_CATEGORY_N) + ')'}**
— {"one common 0-100 scale appears reasonably comparable" if scale['answer'] == 'A' else "branch-specific score calibration would likely be required before a single global verdict is used" if scale['answer'] == 'B' else "not enough populated categories to answer"}.
**No calibration was performed in this task.**

## STEP 7 — within-branch discrimination (diagnostic)

Pooled E2 AUC: **{_fmt(branch['pooled_auc'])}**. A pooled number can hide
branch-specific score-scale differences (STEP 6) — this section reports
per-tone and per-realization-category AUC separately, and two descriptive
macro-averages over the {branch['n_eligible_categories']} categories with
N >= {MIN_CATEGORY_N}.

| Branch | N | AUC |
|---|---|---|
{branch_lines}

**Diagnostic macro-average (unweighted):** {_fmt(branch['macro_avg_unweighted'])}
**Diagnostic macro-average (N-weighted):** {_fmt(branch['macro_avg_weighted'])}

## STEP 8 — high-confidence subset

Reuses the pre-existing `HIGH_CONFIDENCE_DIAGNOSTIC_SUBSET` definition from
`label_audit.meets_high_confidence_criteria` (unanimous rating + valid
single-character annotation + context-stable *lexical* tone + non-neutral
tone) unchanged — defined for validation before this task existed, applied to
development here without modification, and not redefined after seeing any
E2 result.

| | N | Human-correct rate | E2 AUC | E V1 AUC |
|---|---|---|---|---|
| High-confidence subset | {high_conf['n']} | {_fmt(high_conf['human_correct_rate'])} | {_fmt(high_conf['e2_auc'])} | {_fmt(high_conf['e1_auc'])} |
| All scored rows (for comparison) | {len(scored)} | {_fmt(_human_correct_rate(scored))} | {_fmt(pooled['e2']['auc'])} | {_fmt(pooled['e1']['auc'])} |

Note: `meets_high_confidence_criteria`'s "context-stable" criterion is
`sandhi_status == "stable"` from `label_audit.SANDHI_STATUS_MAP`, a coarser
three-way split (stable / T3-sandhi-candidate / yi-or-bu-sandhi-candidate)
than this report's own STEP 4 `t3_context_category` (which further splits T3
into full_third vs half_third). The two are related but not identical --
this subset is reused unmodified rather than redefined to match STEP 4's
finer categories, per the task's instruction not to redefine the subset after
looking at E2 results.

## STEP 9 — error export

{result['n_false_rejection_written']} false-rejection rows (human-correct,
E2 score < {FIXED_THRESHOLD:.0f}) written to
`candidate_e2_development_false_rejection.csv`;
{result['n_false_acceptance_written']} false-acceptance rows (human-incorrect,
E2 score >= {FIXED_THRESHOLD:.0f}) written to
`candidate_e2_development_false_acceptance.csv`. The 58 cut point here is the
same fixed, pre-existing constant used throughout this report for E1/Baseline
A binary metrics -- used ONLY to decide which rows are interesting enough to
export for manual review, never adopted as Candidate E2's deployment
threshold.

## STEP 10 — decision

**{verdict}.** {reason}

---

*`validation` and `final_test` were not loaded by any code in this
evaluation. Candidate E2, Candidate E V1, and `tone_context.py` were not
modified.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return verdict


def write_comparison_report(result: dict[str, Any], path: Path = COMPARISON_MD) -> None:
    master = result["master"]
    pooled = pooled_comparison(master)

    def row(label: str, key: str, has_binary: bool) -> str:
        block = pooled[key]
        if has_binary:
            return (
                f"| {label} | {_fmt(block.get('n'))} | {_fmt(block.get('auc'))} | "
                f"{_fmt(block.get('balanced_accuracy'))} | {_fmt(block.get('matthews_correlation'))} | "
                f"{_fmt(block.get('cohen_kappa'))} | {_fmt(block.get('f1'))} | "
                f"{_fmt(block.get('false_rejection_rate'))} | {_fmt(block.get('false_acceptance_rate'))} |"
            )
        return f"| {label} | {pooled['n_labeled']} | {_fmt(block.get('auc'))} | NA | NA | NA | NA | NA | NA |"

    report = f"""# Baseline A vs Candidate B1 vs Candidate C1 vs Candidate E V1 vs Candidate E2 — development

STEP 2 of Candidate E2's first OMPAL evaluation. All five models scored on
the SAME development rows ({pooled['n_labeled']} with a human label).
Candidate B1/C1 report their honest out-of-fold estimate (no leakage);
Baseline A and Candidate E V1 use the same fixed threshold of 58 every prior
report in this line already used; Candidate E2 has no threshold, so its
binary columns are NA by design, per the task's explicit instruction not to
invent one — see `candidate_e2_ompal_development.md` STEP 6 for whether one
would even be well-defined.

| Model | N | AUC | Balanced accuracy | MCC | Cohen's kappa | F1 | False rejection rate | False acceptance rate |
|---|---|---|---|---|---|---|---|---|
{row("Baseline A", "baseline_a", True)}
{row("Candidate B1 (dev OOF)", "b1", True)}
{row("Candidate C1 (dev OOF)", "c1", True)}
{row("Candidate E V1", "e1", True)}
{row("Candidate E2", "e2", False)}

---

*`validation` and `final_test` were not loaded. No model was fit or
threshold-tuned in this report -- Candidate B1/C1's cross-validation and
threshold selection are their own already-frozen, already-published
pipelines, re-run here only to produce numbers on the same row set.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def write_reports(result: dict[str, Any]) -> str:
    verdict = write_development_report(result)
    write_comparison_report(result)
    return verdict
