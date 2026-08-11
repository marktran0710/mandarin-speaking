"""Renders Candidate B1's results dict (from `praat_logistic.run()`) into
`benchmarking/results/candidate_b_praat_logistic.md`.

Kept separate from `praat_logistic.py` so the modelling code and the report
prose can each be read without the other — the same separation
`benchmarking/validation_cli.py` and `benchmarking/error_analysis.py` already
use elsewhere in this package.

The "substantial improvement" bar in section 11 is fixed here, in code,
BEFORE `run()` is ever executed against real data: validation overall ROC
AUC >= 0.65, a conventional rule-of-thumb boundary between "poor" and
"fair" discrimination, chosen because it sits well clear of both chance
(0.5) and Baseline A's already-measured ~0.51. Stating it in code ahead of
the run is what keeps it a pre-specified rule rather than a bar quietly
redrawn around whatever number came out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from benchmarking.candidates.praat_logistic import (
    CV_FOLDS,
    CV_SEED,
    EXCLUDED_FROM_FEATURES,
    FEATURE_NAMES,
    L2,
    REPORT_PATH,
    TONES,
)
from benchmarking.splits import DEFAULT_SPLIT_PATH, load_split

#: Fixed before the run — see module docstring.
SUBSTANTIAL_AUC_BAR = 0.65


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def _pct(value: Any) -> str:
    return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else "NA"


METRIC_ROWS = [
    ("ROC AUC", "auc", 3),
    ("Accuracy", "accuracy", 3),
    ("Balanced accuracy", "balanced_accuracy", 3),
    ("Precision", "precision", 3),
    ("Recall (sensitivity)", "recall", 3),
    ("Specificity", "specificity", 3),
    ("F1", "f1", 3),
    ("Cohen's kappa", "cohen_kappa", 4),
    ("Matthews correlation (MCC)", "matthews_correlation", 4),
    ("False acceptance rate", "false_acceptance_rate", 3),
    ("False rejection rate", "false_rejection_rate", 3),
]


def _metric_table(entries: dict[str, dict[str, Any]], columns: list[str]) -> str:
    header = "| Metric | " + " | ".join(columns) + " |\n"
    header += "|---|" + "|".join(["---"] * len(columns)) + "|\n"
    body = []
    for label, key, digits in METRIC_ROWS:
        row = [label] + [_fmt(entries[col].get(key), digits) for col in columns]
        body.append("| " + " | ".join(row) + " |")
    return header + "\n".join(body)


def _side_by_side(baseline: dict[str, Any], candidate: dict[str, Any]) -> str:
    return _metric_table({"Baseline A": baseline, "Candidate B1": candidate}, ["Baseline A", "Candidate B1"])


def write_report(result: dict[str, Any], path: Path = REPORT_PATH) -> None:
    split = load_split(DEFAULT_SPLIT_PATH)

    cv_fold_lines = []
    for tone in TONES:
        for entry in result["cv_fold_metrics"][tone]:
            cv_fold_lines.append(
                f"| T{tone} | {entry['fold']} | {entry['n_train']} | {entry['n_test']} | "
                f"{_fmt(entry['auc'])} | {entry['converged']} |"
            )

    cv_by_tone_cols = {f"T{t}": result["cv_by_tone"][t] for t in TONES}
    cv_table = _metric_table(cv_by_tone_cols, list(cv_by_tone_cols))

    val_by_tone_cols = {f"T{t}": result["validation_by_tone"][t] for t in TONES}
    val_table = _metric_table(val_by_tone_cols, list(val_by_tone_cols))

    baseline_dev_by_tone_cols = {f"T{t}": result["baseline_dev_by_tone"][t] for t in TONES}
    baseline_val_by_tone_cols = {f"T{t}": result["baseline_val_by_tone"][t] for t in TONES}

    overall_val_auc = result["validation_overall"].get("auc")
    per_tone_val_auc = {t: result["validation_by_tone"][t].get("auc") for t in TONES}
    contour_tones_ok = all(
        (per_tone_val_auc[t] or 0) >= 0.60 for t in ("2", "3", "4")
    )
    substantial = (overall_val_auc or 0) >= SUBSTANTIAL_AUC_BAR and contour_tones_ok

    if substantial:
        recommendation = (
            f"**Keep investigating Praat features.** Validation overall AUC "
            f"{_fmt(overall_val_auc)} clears the pre-specified bar of "
            f"{SUBSTANTIAL_AUC_BAR:.2f}, and T2/T3/T4 each reach at least 0.60 "
            "AUC. The acoustic representation already computed by the frozen "
            "pipeline contains discriminative information the current "
            "hand-crafted contour rule is not using. Per the interpretation "
            "rule fixed before this run, the contour-scoring heuristic — not "
            "the acoustic features — looks like the main limitation."
        )
    else:
        recommendation = (
            "**Proceed to Candidate C / a richer speech representation.** "
            f"Validation overall AUC {_fmt(overall_val_auc)} does not clear the "
            f"pre-specified bar of {SUBSTANTIAL_AUC_BAR:.2f}"
            + (
                ", and/or one or more of T2/T3/T4 remain below 0.60 AUC"
                if not contour_tones_ok
                else ""
            )
            + ". A linear model on this exact feature set stays close to "
            "chance, which — per the interpretation rule fixed before this "
            "run — points at the features themselves being insufficient for "
            "this task, not merely at the scoring rule applied to them. This "
            "does not by itself prove no simple feature combination would "
            "work (see Limitations); it is the evidence this task asked for "
            "to justify moving to a richer representation."
        )

    report = f"""# Candidate B1 — Praat acoustic features + logistic regression

Research question: can the acoustic features the frozen Praat pipeline
already computes discriminate OMPAL-correct from OMPAL-incorrect tones
substantially better than the current hand-crafted `directional_tone_scores`
heuristic (Baseline A)?

**final_test was not loaded, evaluated, or inspected at any point in this
run.** `praat_logistic.load_split_rows` raises `FinalTestLockedError` for
that partition unless called with `unlock_final_test=True` **and** the
`OMPAL_FINAL_TEST_UNLOCKED=1` environment variable set; neither is set
anywhere in this module's own code path.

## 1. Exact data split

Speaker split: `benchmarking/splits/ompal_speaker_split.json`, seed {split.seed}.

| Split | Speakers | Rows available | Excluded (no acoustic features) | Rows used |
|---|---|---|---|---|
| development | {len(split.development)} | {result['dev_n'] + result['dev_excluded_no_features']} | {result['dev_excluded_no_features']} | {result['dev_n']} |
| validation | {len(split.validation)} | {result['val_n'] + result['val_excluded_no_features']} | {result['val_excluded_no_features']} | {result['val_n']} |

"Rows available" already reflects the official OMPAL exclusion rules baked
into `human_vs_system_diagnostics.csv` (neutral tone, syllables the analyzer
declined to judge, incomplete 3-rater panels — see `diagnostics.py`).
"Excluded (no acoustic features)" is Candidate B1's own additional
exclusion: utterances where the aligner produced no usable per-syllable
span at all (`duration_seconds == NA`), for which none of the nine features
below can be computed. `final_test` is not shown because it was not loaded.

## 2. Feature definitions

| Feature | Meaning |
|---|---|
| `normalized_f0_start` / `_mid` / `_end` | The syllable's own F0 contour, robust-z-normalised to itself (`chinese_tones.normalize_pitch_contour`) and read at the first/middle/last of 100 resampled points. |
| `f0_range` | max(F0) − min(F0) across the syllable's voiced frames, Hz. |
| `f0_slope_full` | (F0 at end − F0 at start) / duration across the whole syllable, Hz/s. |
| `f0_slope_first_half` / `f0_slope_second_half` | The same slope computed separately on each half of the syllable — a linear model can weight early vs. late movement differently, which the single hand-crafted `directional_tone_scores` rule does not do per tone. |
| `duration_seconds` | Syllable span duration from the energy aligner. |
| `voiced_fraction` | Voiced frame count / span duration — the closest available voicing-quality signal (see `tone_diagnostic_summary.md` §7: no native alignment-confidence score exists in the pipeline). |

`expected_tone` selects which of the four per-tone models applies; it is not
a feature inside any one model (see §4).

Excluded, per the task's instruction:

{chr(10).join(f"- {item}" for item in EXCLUDED_FROM_FEATURES)}

No automatic feature selection was performed — all nine features enter
every tone's model unconditionally.

## 3. Preprocessing

For each tone's model, independently:

1. **Median imputation.** `f0_slope_first_half`/`_second_half` in particular
   are `NA` for syllables with fewer than two usable frames in that half —
   about 13% of development rows for at least one feature. The median is
   computed once per feature, from that tone's development rows only, then
   applied unchanged to validation.
2. **Standardization.** Zero mean, unit variance, mean/SD computed from the
   same development rows, applied unchanged to validation. A constant
   feature (SD ≈ 0) is left unscaled rather than divided by ~0.

Both steps are refit independently inside each cross-validation fold on that
fold's training speakers only (§5) — the reported CV numbers describe a
freshly-preprocessed-and-fit model each time, not one model's in-sample fit
re-evaluated on held-out rows.

## 4. Model specification

**One L2-penalized logistic regression per expected tone** (design choice A
of the two offered), fit by Newton's method
(`benchmarking/logistic.py` — dependency-free; scikit-learn is installed in
this environment but not declared in `requirements.txt`, so it is not used
here).

Chosen over the shared-model-with-interactions design (B) for two reasons:
first, B requires hand-specifying every tone × feature interaction term
in advance — for nine features against four tones that is up to 27
interaction coefficients to choose, which is a bigger and more arbitrary
design surface than A's "one model, tone's own coefficients" and sits
uncomfortably close to *ad hoc* feature engineering for a task that
explicitly rules out feature selection. Second, it is empirically supported:
development's per-tone incorrect-label counts (T1=260, T2=247, T3=265,
T4=389) each comfortably exceed the conventional ~10-events-per-predictor
guideline for a 9-feature model, so nothing forces pooling across tones for
sample size.

L2 strength `{L2:g}` — fixed for numerical stability, not searched (no
nested tuning loop; "no large hyperparameter search" per the task). The
intercept is never penalized.

## 5. Development grouped cross-validation

{CV_FOLDS}-fold, grouped by speaker (`benchmarking.splits.grouped_kfold`,
seed {CV_SEED}), all four tone-models sharing one fold partition of
development's speakers so "fold N" means the same held-out speakers across
tones. No speaker appears in both the training and held-out side of any
fold (`tests/test_splits.py::TestGroupedKFold`).

### Per-fold detail

| Tone | Fold | N train | N held out | AUC | Converged |
|---|---|---|---|---|---|
{chr(10).join(cv_fold_lines)}

### Pooled out-of-fold metrics, by tone

{cv_table}

### Pooled out-of-fold metrics, overall

{_metric_table({"Development CV": result['cv_overall']}, ["Development CV"])}

**Primary metric is ROC AUC**, since it evaluates discrimination without
committing to a threshold. The threshold-dependent rows above (accuracy,
precision, …) use the threshold selected in the next step — reported for
completeness, not as the headline development number.

### Threshold selection (development only, frozen before validation)

For each tone, the threshold in `THRESHOLD_GRID` (0.05 to 0.95, step 0.01)
maximizing **balanced accuracy on that tone's pooled out-of-fold CV
predictions** was selected and frozen:

| Tone | Threshold |
|---|---|
{chr(10).join(f"| T{t} | {result['thresholds'][t]:.2f} |" for t in TONES)}

These thresholds are applied to validation in §6 unchanged. Validation
results were not available at the point this selection was made, and are
never fed back into it.

## 6. Validation results (evaluated once)

Candidate B1's four per-tone models were fit on **all** of development
(§4), frozen, and then applied to validation exactly once, using the
thresholds above.

{_metric_table({"Validation (overall)": result['validation_overall']}, ["Validation (overall)"])}

## 7. Per-tone validation results

{val_table}

## 8. Baseline A vs Candidate B1

Same rows, same split, both methods' predictions read from the same
`human_vs_system_diagnostics.csv` (Baseline A: `system_tone_correct` /
`system_character_score`, already verified against the frozen scorer — see
`diagnostics.py`).

### Development

{_side_by_side(result['baseline_dev'], result['cv_overall'])}

*(Candidate B1's development column is its pooled out-of-fold CV result —
the honest development-only estimate of how it performs on speakers it was
not trained on. Baseline A needs no such distinction; it was not fit on
development at all.)*

### Validation

{_side_by_side(result['baseline_val'], result['validation_overall'])}

### Validation, per tone

**Baseline A:**

{_metric_table(baseline_val_by_tone_cols, list(baseline_val_by_tone_cols))}

**Candidate B1:**

{val_table}

## 9. Error pattern comparison

`tone_diagnostic_summary.md` characterised Baseline A's failure as: T1 is
passed almost indiscriminately (over-acceptance — very low specificity)
while T2/T3/T4 carry high false rejection. On validation:

| | Baseline A | Candidate B1 |
|---|---|---|
| T1 specificity | {_fmt(result['baseline_val_by_tone']['1'].get('specificity'))} | {_fmt(result['validation_by_tone']['1'].get('specificity'))} |
| T1 false acceptance rate | {_pct(result['baseline_val_by_tone']['1'].get('false_acceptance_rate'))} | {_pct(result['validation_by_tone']['1'].get('false_acceptance_rate'))} |
| T2 false rejection rate | {_pct(result['baseline_val_by_tone']['2'].get('false_rejection_rate'))} | {_pct(result['validation_by_tone']['2'].get('false_rejection_rate'))} |
| T3 false rejection rate | {_pct(result['baseline_val_by_tone']['3'].get('false_rejection_rate'))} | {_pct(result['validation_by_tone']['3'].get('false_rejection_rate'))} |
| T4 false rejection rate | {_pct(result['baseline_val_by_tone']['4'].get('false_rejection_rate'))} | {_pct(result['validation_by_tone']['4'].get('false_rejection_rate'))} |
| T2 AUC | {_fmt(result['baseline_val_by_tone']['2'].get('auc'))} | {_fmt(result['validation_by_tone']['2'].get('auc'))} |
| T3 AUC | {_fmt(result['baseline_val_by_tone']['3'].get('auc'))} | {_fmt(result['validation_by_tone']['3'].get('auc'))} |
| T4 AUC | {_fmt(result['baseline_val_by_tone']['4'].get('auc'))} | {_fmt(result['validation_by_tone']['4'].get('auc'))} |

Threshold-dependent rows (specificity, the two error rates) depend on where
each method's threshold happens to sit and are not a clean like-for-like
comparison by themselves; AUC, which does not depend on a threshold, is the
more trustworthy comparison for "did the error pattern actually improve."

## 10. Limitations

- Nine linear, syllable-level features and a linear decision boundary are a
  deliberately narrow hypothesis class. A negative result here rules out
  *this* representation-plus-linear-model combination; it does not rule out
  every possible use of Praat-derived features (a richer nonlinear model
  over the same features was explicitly out of scope — "keep it deliberately
  simple").
- The per-tone split (design A) means each model sees only ~1,900-3,300
  development rows; T1's small incorrect-label count (260) in particular
  keeps its confidence interval on any metric wide.
- `voiced_fraction` and duration are aggregate summaries of the syllable;
  they do not capture the shape of voicing loss within the syllable (e.g.
  a broken/creaky release vs. a clean but short vowel) the way a
  frame-level representation could.
- Development and validation come from the same corpus, elicitation
  protocol and (mostly) French-L1 population as Baseline A's own validation
  — see the population caveat already on record in
  `benchmarking/results/validation_summary_CURRENT_2026-08-10.md`.
- The four per-tone thresholds were selected to maximize balanced accuracy;
  a different criterion (e.g. matching Baseline A's false-rejection rate)
  would move the threshold-dependent rows in §6-7 without moving AUC.

## 11. Recommendation

{recommendation}

---

*Per the task's constraint: final_test remains locked. This report contains
no final_test numbers, predictions, or references beyond this sentence
confirming that fact.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
