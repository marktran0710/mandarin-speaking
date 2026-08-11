"""Renders Candidate C1's results dict (from `wav2vec_frozen_logistic.run()`)
into `benchmarking/results/candidate_c_frozen_wav2vec.md`.

Same "substantial improvement" bar as Candidate B1, applied here for the same
reason: fixed in code before this run, so the decision rule is pre-specified
rather than redrawn around whatever number came out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from benchmarking.candidates.wav2vec_frozen_logistic import (
    CHECKPOINT_NAME,
    CV_FOLDS,
    CV_SEED,
    EMBEDDING_DIM,
    EXCLUDED_FROM_FEATURES,
    L2,
    MIN_SPAN_SAMPLES,
    PCA_DIM_GRID,
    POOLING,
    REPORT_PATH,
    SAMPLE_RATE,
    TONES,
)
from benchmarking.splits import DEFAULT_SPLIT_PATH, load_split

#: Fixed before the run — identical bar to Candidate B1's, so the two
#: candidates are held to the same standard.
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


def _side_by_side(baseline: dict[str, Any], candidate: dict[str, Any], candidate_label: str) -> str:
    return _metric_table({"Baseline A": baseline, candidate_label: candidate}, ["Baseline A", candidate_label])


def write_report(result: dict[str, Any], path: Path = REPORT_PATH) -> None:
    split = load_split(DEFAULT_SPLIT_PATH)

    pca_grid_lines = "\n".join(
        f"| {entry['pca_dim']} | {_fmt(entry['pooled_dev_cv_auc'])} |"
        + ("  <- selected" if entry["pca_dim"] == result["pca_dim"] else "")
        for entry in result["pca_grid_results"]
    )

    cv_fold_lines = []
    for tone in TONES:
        for entry in result["cv_fold_metrics"][tone]:
            cv_fold_lines.append(
                f"| T{tone} | {entry['fold']} | {entry['n_train']} | {entry['n_test']} | "
                f"{entry['n_components']} | {_fmt(entry['auc'])} | {entry['converged']} |"
            )

    cv_by_tone_cols = {f"T{t}": result["cv_by_tone"][t] for t in TONES}
    cv_table = _metric_table(cv_by_tone_cols, list(cv_by_tone_cols))

    val_by_tone_cols = {f"T{t}": result["validation_by_tone"][t] for t in TONES}
    val_table = _metric_table(val_by_tone_cols, list(val_by_tone_cols))

    baseline_val_by_tone_cols = {f"T{t}": result["baseline_val_by_tone"][t] for t in TONES}

    overall_val_auc = result["validation_overall"].get("auc")
    per_tone_val_auc = {t: result["validation_by_tone"][t].get("auc") for t in TONES}
    contour_tones_ok = all((per_tone_val_auc[t] or 0) >= 0.60 for t in ("2", "3", "4"))
    substantial = (overall_val_auc or 0) >= SUBSTANTIAL_AUC_BAR and contour_tones_ok

    if substantial:
        recommendation = (
            f"**Freeze Candidate C1 and prepare for the single locked final_test "
            f"comparison.** Validation overall AUC {_fmt(overall_val_auc)} clears "
            f"the pre-specified bar of {SUBSTANTIAL_AUC_BAR:.2f}, and T2/T3/T4 each "
            "reach at least 0.60 AUC. Before final_test is opened for this "
            "candidate, resolve the provenance audit's disclosed caveat "
            "(`candidate_c_wav2vec_provenance_audit.md` §6): 7 of the 9 "
            "final_test speakers already had their OMPAL labels used to fit or "
            "select a *different* wav2vec2-embedding classifier in the prior "
            "research program, which is a real, if indirect, threat to "
            "final_test's blindness specifically for this representation family."
        )
    else:
        recommendation = (
            "**Do not open final_test.** "
            f"Validation overall AUC {_fmt(overall_val_auc)} does not clear the "
            f"pre-specified bar of {SUBSTANTIAL_AUC_BAR:.2f}"
            + (
                ", and/or one or more of T2/T3/T4 remain below 0.60 AUC"
                if not contour_tones_ok
                else ""
            )
            + ". Per the task's decision rule, this concludes that a frozen, "
            "off-the-shelf Wav2Vec2 representation — reduced to a low-dimensional "
            "linear signal and combined with a simple classifier — has not solved "
            "the discrimination problem either. Fine-tuning the encoder itself was "
            "explicitly out of scope for this candidate; whether it is worth "
            "attempting is a methodological question for review, not a decision "
            "this report makes."
        )

    report = f"""# Candidate C1 — Frozen Wav2Vec2 embeddings + logistic regression

Research question: does a richer, learned speech representation (frozen
Wav2Vec2 hidden states) discriminate OMPAL-correct from OMPAL-incorrect
tones substantially better than Baseline A's hand-crafted contour heuristic,
or Candidate B1's Praat-feature logistic baseline?

**final_test was not loaded, evaluated, or inspected at any point in this
run.** Row loading is delegated entirely to
`benchmarking.candidates.praat_logistic.load_split_rows`, which raises
`FinalTestLockedError` for that partition unless called with
`unlock_final_test=True` **and** the `OMPAL_FINAL_TEST_UNLOCKED=1`
environment variable set; neither is set anywhere in this module's own code
path.

**Provenance gate**: this candidate was only built after
`candidate_c_wav2vec_provenance_audit.md` classified the existing frozen
Wav2Vec2 checkpoint as **B — encoder clean, existing downstream classifier
contaminated by prior OMPAL use**. Per that audit, Candidate C1 uses the
checkpoint only as a fresh forward-pass feature extractor and fits an
entirely new classifier on the current development/validation split; it
never loads, reuses, or is informed by the design of the prior contaminated
classifier. **The audit also found that 7 of the 9 speakers in the new,
locked `final_test` partition were already used to fit or select that prior
wav2vec2-embedding classifier** — this doesn't affect the development/
validation numbers below (which never touch final_test), but it is a
disclosed, unresolved risk to final_test's blindness for this representation
family specifically; see the audit's §6 and §11 below.

## 1. Exact data split

Speaker split: `benchmarking/splits/ompal_speaker_split.json`, seed {split.seed}
— the same split Candidate B1 used.

| Split | Speakers | Rows available | Excluded (no acoustic span) | Excluded (no embedding) | Rows used |
|---|---|---|---|---|---|
| development | {len(split.development)} | {result['dev_n'] + result['dev_excluded_no_features'] + result['dev_excluded_no_embedding']} | {result['dev_excluded_no_features']} | {result['dev_excluded_no_embedding']} | {result['dev_n']} |
| validation | {len(split.validation)} | {result['val_n'] + result['val_excluded_no_features'] + result['val_excluded_no_embedding']} | {result['val_excluded_no_features']} | {result['val_excluded_no_embedding']} | {result['val_n']} |

"Excluded (no acoustic span)" reuses Candidate B1's exclusion rule
(`duration_seconds == NA` — no recoverable syllable alignment at all).
"Excluded (no embedding)" is Candidate C1's own additional exclusion:
spans shorter than {MIN_SPAN_SAMPLES} samples (~{MIN_SPAN_SAMPLES / SAMPLE_RATE * 1000:.0f}ms
at {SAMPLE_RATE}Hz), too short for the encoder's convolutional stem to
produce any output frame. `final_test` is not shown because it was not
loaded.

## 2. Representation

- **Checkpoint**: `{result['checkpoint']}` (see the provenance audit §1 for
  how this was identified as the only checkpoint in use anywhere in the
  repository, and §2 for the runtime-enforced proof it was never fine-tuned).
- **Encoder frozen**: `True`, asserted at construction
  (`FrozenEncoder.__init__` raises if any parameter has `requires_grad`).
- **Checkpoint weight hash (SHA-256)**: `{result['checkpoint_sha256']}` —
  computed once per run over every parameter tensor's name and bytes; stored
  alongside every cached embedding batch so a future run can confirm the
  same weights produced them.
- **Pooling**: `{result['pooling']}` over the syllable's own time span (not
  the whole utterance) — the task's pre-specified default, and also the
  pooling method documented in `pronunciation/wav2vec_tone/extract_embeddings.py`
  *before* the later, OMPAL-informed mean-vs-temporal3 comparison existed.
  Only mean pooling was tried; no other pooling method was evaluated at any
  point in this candidate's development.
- **Unit of analysis**: the same judged syllables as Candidate B1, using the
  same frozen syllable alignment (`syllable_start_time`/`syllable_end_time`
  from `human_vs_system_diagnostics.csv`) to select the audio span passed to
  the encoder.
- **Embedding dimensionality**: {EMBEDDING_DIM} (one mean-pooled vector per syllable
  span, per Wav2Vec2-base's hidden size).

Excluded from the representation, per the task's instruction:

{chr(10).join(f"- {item}" for item in EXCLUDED_FROM_FEATURES)}

## 3. Embedding cache

Cached under `private-data/wav2vec_embeddings_cache/` (git-ignored — large
binary derivative of private OMPAL audio), one `.npz` + metadata `.json` pair
per split, keyed by `(audio_id, syllable_index)`. Re-running this module
against the same rows re-uses the cache instead of re-invoking the encoder.
Each metadata file records the checkpoint name, its weight hash,
`encoder_frozen: true`, the pooling method, the split name, and per-key
provenance (speaker ID, audio ID, syllable span, expected tone) — the STEP 3
metadata requirement.

## 4. Dimension control

{EMBEDDING_DIM} embedding dimensions against as few as ~250 incorrect-label examples for
the smallest tone (see `candidate_b_praat_logistic.md` §4) is roughly 0.3
events per predictor — more than an order of magnitude below the
conventional ~10-events-per-predictor guideline. Per the task's STEP 4,
option A (direct high-dimensional logistic regression on raw embeddings) was
therefore not attempted; this candidate goes straight to option B:

1. **Standardize** each of the {EMBEDDING_DIM} dimensions (zero mean, unit variance),
   fit on the training rows only.
2. **PCA**, fit on the *standardized* training rows only, reducing to a
   single shared dimensionality (not one per tone, to keep the search small)
   chosen from the pre-specified grid `{list(PCA_DIM_GRID)}` by maximizing
   pooled out-of-fold ROC AUC across all four tones under development
   grouped cross-validation — **never using validation** (see
   `tests/test_candidate_c.py` for the guard that this selection function's
   signature cannot even accept validation data).

Both steps are refit independently inside each cross-validation fold, on
that fold's training speakers only — exactly Candidate B1's discipline,
adapted from Praat features to embeddings.

### PCA dimension grid (development-only, frozen before validation)

| PCA dimension | Pooled development CV AUC |
|---|---|
{pca_grid_lines}

**Selected: {result['pca_dim']}** dimensions.

## 5. Model specification

**One L2-penalized logistic regression per expected tone** (design choice A,
same reasoning as Candidate B1 — the per-tone incorrect-label counts are
adequate for a {result['pca_dim']}-dimensional model, and a shared model
would require hand-specifying tone × principal-component interaction terms,
a larger and more arbitrary design surface for the same reason Candidate B1
rejected it). Fit by Newton's method (`benchmarking/logistic.py`).

L2 strength `{L2:g}` — fixed for numerical stability, not searched.
The intercept is never penalized.

## 6. Development grouped cross-validation

{CV_FOLDS}-fold, grouped by speaker (`benchmarking.splits.grouped_kfold`,
seed {CV_SEED}) — the same fold partition Candidate B1 used, so "fold N"
means the same held-out speakers across both candidates. No speaker appears
in both the training and held-out side of any fold.

### Per-fold detail (at the selected PCA dimension)

| Tone | Fold | N train | N held out | N components | AUC | Converged |
|---|---|---|---|---|---|---|
{chr(10).join(cv_fold_lines)}

### Pooled out-of-fold metrics, by tone

{cv_table}

### Pooled out-of-fold metrics, overall

{_metric_table({"Development CV": result['cv_overall']}, ["Development CV"])}

**Primary metric is ROC AUC.** The threshold-dependent rows use the
threshold selected in the next step.

### Threshold selection (development only, frozen before validation)

Same rule as Candidate B1: for each tone, the threshold maximizing balanced
accuracy on that tone's pooled out-of-fold CV predictions (at the selected
PCA dimension) was selected and frozen:

| Tone | Threshold |
|---|---|
{chr(10).join(f"| T{t} | {result['thresholds'][t]:.2f} |" for t in TONES)}

## 7. Validation results (evaluated once)

Candidate C1's four per-tone models were fit on **all** of development at
the frozen PCA dimensionality (§5), frozen, and then applied to validation
exactly once, using the thresholds above.

{_metric_table({"Validation (overall)": result['validation_overall']}, ["Validation (overall)"])}

## 8. Per-tone validation results

{val_table}

## 9. Three-model comparison: Baseline A vs Candidate B1 vs Candidate C1

Read `candidate_b_praat_logistic.md` for Candidate B1's own full report;
combined numbers for all three methods are in
`benchmarking/results/candidate_abc_comparison.md`. This section covers only
Baseline A vs Candidate C1 on the same rows.

### Validation

{_side_by_side(result['baseline_val'], result['validation_overall'], "Candidate C1")}

### Validation, per tone

**Baseline A:**

{_metric_table(baseline_val_by_tone_cols, list(baseline_val_by_tone_cols))}

**Candidate C1:**

{val_table}

`tone_diagnostic_summary.md` characterised Baseline A's failure as T1
over-acceptance (very low specificity) alongside high T2/T3/T4 false
rejection. Whether Candidate C1 changes this pattern is discussed jointly
with Candidate B1 in `candidate_abc_comparison.md`.

## 10. Limitations

- The encoder was used strictly as a frozen feature extractor; fine-tuning
  it was explicitly out of scope for this candidate (per the task). A
  negative result here rules out *this* frozen-representation-plus-linear-
  classifier combination, not fine-tuning.
- PCA to {result['pca_dim']} dimensions discards most of the {EMBEDDING_DIM}-dimensional
  representation's structure by construction; a nonlinear classifier over
  the full embedding was explicitly out of scope ("keep it deliberately
  simple").
- Mean-pooling over the syllable span collapses all temporal structure
  within the syllable to a single vector — the same limitation Candidate
  B1's aggregate features (`voiced_fraction`, `duration_seconds`) have,
  for a different reason.
- See the provenance audit's §6 and §11 (reproduced in the notice above)
  for the disclosed, unresolved final_test-speaker-overlap risk specific to
  this representation family.
- Development and validation come from the same corpus, elicitation
  protocol and population as Baseline A's and Candidate B1's validation.

## 11. Recommendation

{recommendation}

---

*Per the task's constraint: final_test remains locked. This report contains
no final_test numbers, predictions, or references beyond this sentence and
the provenance-audit caveat cited above.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
