"""STEP 8 — three-model comparison: Baseline A vs Candidate B1 vs Candidate C1.

    python -m benchmarking.candidates.compare_abc

Re-runs `praat_logistic.run()` and `wav2vec_frozen_logistic.run()` (both
cheap on a warm embedding cache -- this script does not re-invoke the
Wav2Vec2 encoder unless the cache is missing) so the comparison table is
generated from live numbers rather than hand-copied from the two individual
reports, and writes `benchmarking/results/candidate_abc_comparison.md`.

Development and validation only. final_test is never referenced -- neither
`praat_logistic.run()` nor `wav2vec_frozen_logistic.run()` ever calls
`load_split_rows("final_test", ...)`.

Candidate B1 and Candidate C1 apply slightly different row-level exclusion
rules (B1 excludes rows with no Praat/alignment features; C1 additionally
excludes rows with a span too short to embed), so their own recorded
Baseline A comparison numbers are computed on two slightly different row
subsets. Rather than force a single Baseline A number that isn't exactly
apples-to-apples with both candidates at once, this report keeps each
candidate's Baseline A column scoped to that candidate's own row subset --
each individual comparison stays internally consistent even though the two
Baseline A columns differ from each other in the third or fourth digit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from benchmarking.candidates import praat_logistic, wav2vec_frozen_logistic
from benchmarking.candidates.report_praat_logistic import SUBSTANTIAL_AUC_BAR, _fmt, _metric_table

REPORT_PATH = Path("benchmarking/results/candidate_abc_comparison.md")
TONES = ("1", "2", "3", "4")


def _decision(overall_auc: float | None, per_tone_auc: dict[str, float | None]) -> tuple[bool, str]:
    contour_tones_ok = all((per_tone_auc[t] or 0) >= 0.60 for t in ("2", "3", "4"))
    passes = (overall_auc or 0) >= SUBSTANTIAL_AUC_BAR and contour_tones_ok
    return passes, (
        f"AUC {_fmt(overall_auc)} {'>=' if passes else '<'} {SUBSTANTIAL_AUC_BAR:.2f}"
        + ("" if contour_tones_ok else "; T2/T3/T4 not all >= 0.60")
    )


def build_report(b_result: dict[str, Any], c_result: dict[str, Any]) -> str:
    dev_cols = {
        "Baseline A (B1 rows)": b_result["baseline_dev"],
        "Candidate B1 (dev CV)": b_result["cv_overall"],
        "Baseline A (C1 rows)": c_result["baseline_dev"],
        "Candidate C1 (dev CV)": c_result["cv_overall"],
    }
    val_cols = {
        "Baseline A (B1 rows)": b_result["baseline_val"],
        "Candidate B1": b_result["validation_overall"],
        "Baseline A (C1 rows)": c_result["baseline_val"],
        "Candidate C1": c_result["validation_overall"],
    }

    per_tone_val_lines = []
    for tone in TONES:
        per_tone_val_lines.append(
            f"| T{tone} AUC | {_fmt(b_result['baseline_val_by_tone'][tone].get('auc'))} "
            f"| {_fmt(b_result['validation_by_tone'][tone].get('auc'))} "
            f"| {_fmt(c_result['baseline_val_by_tone'][tone].get('auc'))} "
            f"| {_fmt(c_result['validation_by_tone'][tone].get('auc'))} |"
        )
        per_tone_val_lines.append(
            f"| T{tone} specificity | {_fmt(b_result['baseline_val_by_tone'][tone].get('specificity'))} "
            f"| {_fmt(b_result['validation_by_tone'][tone].get('specificity'))} "
            f"| {_fmt(c_result['baseline_val_by_tone'][tone].get('specificity'))} "
            f"| {_fmt(c_result['validation_by_tone'][tone].get('specificity'))} |"
        )
        per_tone_val_lines.append(
            f"| T{tone} false rejection rate | "
            f"{_fmt(b_result['baseline_val_by_tone'][tone].get('false_rejection_rate'))} "
            f"| {_fmt(b_result['validation_by_tone'][tone].get('false_rejection_rate'))} "
            f"| {_fmt(c_result['baseline_val_by_tone'][tone].get('false_rejection_rate'))} "
            f"| {_fmt(c_result['validation_by_tone'][tone].get('false_rejection_rate'))} |"
        )

    b_overall_auc = b_result["validation_overall"].get("auc")
    b_per_tone_auc = {t: b_result["validation_by_tone"][t].get("auc") for t in TONES}
    b_passes, b_reason = _decision(b_overall_auc, b_per_tone_auc)

    c_overall_auc = c_result["validation_overall"].get("auc")
    c_per_tone_auc = {t: c_result["validation_by_tone"][t].get("auc") for t in TONES}
    c_passes, c_reason = _decision(c_overall_auc, c_per_tone_auc)

    if not b_passes and not c_passes:
        overall_call = (
            "**Neither candidate clears the pre-specified bar.** Per the task's "
            "decision rule (validation overall AUC >= 0.65 and T2/T3/T4 each >= "
            "0.60, fixed before Candidate B1 was ever run), final_test stays "
            "closed for both. Moving from hand-crafted Praat features to a "
            "frozen, off-the-shelf speech representation changed the numbers "
            "but did not change the qualitative conclusion: nothing built so far "
            "in this line of candidates discriminates OMPAL-correct from "
            "OMPAL-incorrect tones at more than a modest margin over chance."
        )
    elif b_passes and not c_passes:
        overall_call = (
            "**Candidate B1 clears the bar; Candidate C1 does not.** This would "
            "be an unusual result (a richer representation underperforming "
            "simple acoustic features) and should be treated as a signal to "
            "re-check Candidate C1's pipeline before acting on it."
        )
    elif c_passes and not b_passes:
        overall_call = (
            "**Candidate C1 clears the bar; Candidate B1 does not.** Per the "
            "task's decision rule, prepare Candidate C1 for the single locked "
            "final_test comparison -- but first resolve the provenance audit's "
            "disclosed final_test-speaker-overlap caveat "
            "(`candidate_c_wav2vec_provenance_audit.md` §6)."
        )
    else:
        overall_call = (
            "**Both candidates clear the bar.** Compare their validation AUC "
            "directly to decide which one (if either) is worth carrying into a "
            "locked final_test comparison; either way, resolve the provenance "
            "audit's final_test-speaker-overlap caveat first if Candidate C1 is "
            "the one chosen."
        )

    report = f"""# Candidate comparison: Baseline A vs Candidate B1 vs Candidate C1

Development and validation only. **final_test is not referenced anywhere in
this report** -- neither `praat_logistic.run()` nor
`wav2vec_frozen_logistic.run()`, both re-run to produce the numbers below,
ever loads that partition.

## Development

Candidate B1 and C1 numbers are each candidate's own pooled out-of-fold
grouped-CV result (the honest development-only estimate of performance on
speakers the model wasn't trained on); Baseline A needs no such distinction
since it was not fit on development at all. The two Baseline A columns
differ slightly because B1 and C1 exclude slightly different rows (see this
module's docstring).

{_metric_table(dev_cols, list(dev_cols))}

## Validation (evaluated once per candidate)

{_metric_table(val_cols, list(val_cols))}

## Per-tone validation: AUC, specificity, false rejection rate

`tone_diagnostic_summary.md` characterised Baseline A's failure mode as: T1
is passed almost indiscriminately (over-acceptance -- very low specificity),
while T2/T3/T4 carry high false rejection.

| | Baseline A (B1 rows) | Candidate B1 | Baseline A (C1 rows) | Candidate C1 |
|---|---|---|---|---|
{chr(10).join(per_tone_val_lines)}

**T1 over-acceptance**: Baseline A's T1 specificity above is the direct
measure of this -- a low value means Baseline A rarely rejects an incorrect
T1 attempt. Whether either candidate improves it is read directly off the T1
specificity row.

**T2/T3/T4 false rejection**: Baseline A's false rejection rate on these
three tones is the direct measure of the complementary failure -- rejecting
correct attempts. Whether either candidate reduces these rates, and whether
their AUC (a threshold-independent measure of the same underlying
discrimination) actually improved, are both in the table above; the AUC
rows are the more trustworthy comparison since the two candidates' operating
thresholds were selected by different rules than Baseline A's fixed
threshold of 58.

## Decision rule (pre-specified, fixed before either candidate was evaluated)

Validation overall ROC AUC >= {SUBSTANTIAL_AUC_BAR:.2f} **and** T2/T3/T4
validation AUC each >= 0.60.

- **Candidate B1**: {b_reason} -> {"PASSES" if b_passes else "does not pass"}
- **Candidate C1**: {c_reason} -> {"PASSES" if c_passes else "does not pass"}

{overall_call}

## PCA dimensionality selected for Candidate C1

{c_result['pca_dim']} (from the pre-specified grid, chosen by pooled
development-CV AUC -- see `candidate_c_frozen_wav2vec.md` §4).

---

*final_test remains locked. This report contains no final_test numbers,
predictions, or references.*
"""
    return report


def run() -> None:
    print("Re-running Candidate B1 (Praat features)...")
    b_result = praat_logistic.run()
    print("Re-running Candidate C1 (frozen Wav2Vec2) -- fast if the embedding cache is warm...")
    c_result = wav2vec_frozen_logistic.run()

    report = build_report(b_result, c_result)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Comparison written to {REPORT_PATH}")


if __name__ == "__main__":
    run()
