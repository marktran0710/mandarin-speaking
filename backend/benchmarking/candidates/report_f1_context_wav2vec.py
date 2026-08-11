"""Report writers for Candidate F1 (development CV + one-shot validation).

Reads only what `f1_context_wav2vec.run()` already computed; renders the
STEP "decision rule" verdict from the SAME pre-existing rule
`compare_abc.py` already used for Candidate B1/C1 (validation overall AUC
>= 0.65 AND T2/T3/T4 validation AUC each >= 0.60) -- not a new rule invented
for Candidate F1.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from benchmarking.candidates.f1_context_wav2vec import (
    B_VAL_PREDICTIONS,
    COMPARISON_MD,
    C_VAL_PREDICTIONS,
    NEARLY_TIED_AUC_GAP,
    REPORT_DEV_MD,
    REPORT_VAL_MD,
)
from benchmarking.stats import binary_agreement, roc_auc

SUBSTANTIAL_AUC_BAR = 0.65
PER_TONE_AUC_BAR = 0.60


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "NA"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# Development report
# ---------------------------------------------------------------------------


def write_development_report(result: dict[str, Any], path: Path = REPORT_DEV_MD) -> None:
    cv_a, cv_b = result["cv_a"], result["cv_b"]
    variant = result["variant"]
    auc_a, auc_b = cv_a["pooled_auc"], cv_b["pooled_auc"]
    gap = abs((auc_a or 0.0) - (auc_b or 0.0))

    fold_lines_a = "\n".join(
        f"| {m['fold']} | {m['n_train']} | {m['n_test']} | {m['n_pca_components']} | {_fmt(m['auc'])} | {m['converged']} |"
        for m in cv_a["fold_metrics"]
    )
    fold_lines_b = "\n".join(
        f"| {m['fold']} | {m['n_train']} | {m['n_test']} | {m['n_pca_components']} | {_fmt(m['auc'])} | {m['converged']} |"
        for m in cv_b["fold_metrics"]
    )

    report = f"""# Candidate F1 — development (5-fold speaker-grouped CV)

F1a = frozen Wav2Vec2 embedding (Candidate C1's encoder, standardize+PCA({30}))
+ linguistic context features (`tone_context.plan_expected_tones`, never
character/word/speaker/audio-ID). F1b = F1a + the existing Praat diagnostic
features (`praat_logistic.FEATURE_NAMES`). Classifier: one fixed
one-hidden-layer MLP (`benchmarking/mlp.py`), no architecture search. PCA,
Praat imputation, and the final feature standardizer are all fit inside each
training fold only; class imbalance is handled from each training fold's own
label counts (`benchmarking.mlp.class_weights`).

Development row count: {result['dev_n']}.

## F1a (embedding + context)

Pooled out-of-fold AUC: **{_fmt(auc_a)}**

| Fold | N train | N test | PCA components | Fold AUC | Converged |
|---|---|---|---|---|---|
{fold_lines_a}

## F1b (embedding + context + Praat)

Pooled out-of-fold AUC: **{_fmt(auc_b)}**

| Fold | N train | N test | PCA components | Fold AUC | Converged |
|---|---|---|---|---|---|
{fold_lines_b}

## Selection

|AUC gap| = {_fmt(gap)}. Rule (fixed before either number was computed): if
|AUC gap| <= {NEARLY_TIED_AUC_GAP}, choose F1a; otherwise choose whichever
variant has the higher pooled dev CV AUC.

**Selected variant: {variant}.** {"Nearly tied -- F1a chosen per the pre-specified tie-break." if gap <= NEARLY_TIED_AUC_GAP else f"F1b's Praat features added a non-trivial AUC gain ({_fmt(gap)} > {NEARLY_TIED_AUC_GAP})." if variant == "F1b" else f"F1a already led by {_fmt(gap)}."}

This variant is frozen on ALL of development (no further fitting) and
evaluated exactly once on validation -- see `candidate_f1_validation.md`.

---

*`final_test` was not loaded by any code in this evaluation.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


# ---------------------------------------------------------------------------
# Validation report + decision
# ---------------------------------------------------------------------------


def decision_rule(val_pooled: dict[str, Any], val_by_tone: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    overall_auc = val_pooled.get("auc")
    t2 = val_by_tone.get("2", {}).get("auc")
    t3 = val_by_tone.get("3", {}).get("auc")
    t4 = val_by_tone.get("4", {}).get("auc")
    per_tone_ok = all(v is not None and v >= PER_TONE_AUC_BAR for v in (t2, t3, t4))
    passes = overall_auc is not None and overall_auc >= SUBSTANTIAL_AUC_BAR and per_tone_ok
    reason = (
        f"overall AUC {_fmt(overall_auc)} {'>=' if (overall_auc or 0) >= SUBSTANTIAL_AUC_BAR else '<'} "
        f"{SUBSTANTIAL_AUC_BAR:.2f}; T2={_fmt(t2)}, T3={_fmt(t3)}, T4={_fmt(t4)} "
        f"({'all >= ' + f'{PER_TONE_AUC_BAR:.2f}' if per_tone_ok else 'not all >= ' + f'{PER_TONE_AUC_BAR:.2f}'})"
    )
    return passes, reason


def write_validation_report(result: dict[str, Any], path: Path = REPORT_VAL_MD) -> tuple[bool, str]:
    val_pooled = result["val_pooled"]
    val_by_tone = result["val_by_tone"]
    val_by_t3 = result["val_by_t3"]

    tone_lines = "\n".join(
        f"| T{tone} | {v.get('n_scored', v.get('n', 0))} | {_fmt(v.get('auc'))} | {_fmt(v.get('balanced_accuracy'))} | "
        f"{_fmt(v.get('matthews_correlation'))} | {_fmt(v.get('cohen_kappa'))} | {_fmt(v.get('f1'))} | "
        f"{_fmt(v.get('false_rejection_rate'))} | {_fmt(v.get('false_acceptance_rate'))} |"
        for tone, v in val_by_tone.items()
    )

    t3_lines = "\n".join(
        f"| {name} | {v.get('n_scored', v.get('n', 0))} | {_fmt(v.get('auc'))} | {_fmt(v.get('balanced_accuracy'))} | "
        f"{_fmt(v.get('false_rejection_rate'))} | {_fmt(v.get('false_acceptance_rate'))} |"
        for name, v in val_by_t3.items()
    )

    passes, reason = decision_rule(val_pooled, val_by_tone)

    report = f"""# Candidate F1 ({result['variant']}) — validation (ONE-SHOT evaluation)

Frozen on all of development; applied exactly once to validation
({result['val_n']} rows), no refitting, no threshold re-selection.
Threshold ({_fmt(result['threshold'])}) selected on development
out-of-fold predictions only. `final_test` was not loaded.

## Overall

| Metric | Value |
|---|---|
| N | {val_pooled.get('n_scored')} |
| AUC | {_fmt(val_pooled.get('auc'))} |
| Balanced accuracy | {_fmt(val_pooled.get('balanced_accuracy'))} |
| MCC | {_fmt(val_pooled.get('matthews_correlation'))} |
| Cohen's kappa | {_fmt(val_pooled.get('cohen_kappa'))} |
| F1 | {_fmt(val_pooled.get('f1'))} |
| False rejection rate | {_fmt(val_pooled.get('false_rejection_rate'))} |
| False acceptance rate | {_fmt(val_pooled.get('false_acceptance_rate'))} |

## Per tone

| Tone | N | AUC | Balanced accuracy | MCC | Cohen's kappa | F1 | False rejection rate | False acceptance rate |
|---|---|---|---|---|---|---|---|---|
{tone_lines}

## T3 context

| Category | N | AUC | Balanced accuracy | False rejection rate | False acceptance rate |
|---|---|---|---|---|---|
{t3_lines}

## Decision rule (pre-existing: validation overall AUC >= {SUBSTANTIAL_AUC_BAR:.2f} AND T2/T3/T4 AUC each >= {PER_TONE_AUC_BAR:.2f})

**{"PASSES" if passes else "does not pass"}** -- {reason}

{"Candidate F1 meets the pre-specified bar. STOPPING here, per the task's instruction -- Wav2Vec2 is not fine-tuned." if passes else "Candidate F1 does not meet the pre-specified bar. Per the task's instruction, this report RECOMMENDS Candidate F2 (supervised Wav2Vec2 fine-tuning) as the next step -- F2 is NOT implemented in this task."}

---

*`final_test` was not loaded by any code in this evaluation. Candidate E V1,
Candidate E2, and `tone_context.py` were not modified.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return passes, reason


# ---------------------------------------------------------------------------
# A / B1 / C1 / E1 / E2 / F1 comparison on validation
# ---------------------------------------------------------------------------


def _evaluate_frozen_predictions_csv(path: Path, prob_key: str, pred_key: str) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labels = [row["human_majority_tone_correct"] == "1" for row in rows]
    probabilities = [float(row[prob_key]) for row in rows]
    predicted = [bool(int(row[pred_key])) for row in rows]
    metrics = binary_agreement(predicted, labels)
    metrics["auc"] = roc_auc(probabilities, labels)
    metrics["n"] = len(rows)
    return metrics


def write_comparison_report(result: dict[str, Any], path: Path = COMPARISON_MD) -> None:
    baseline_a = result["baseline_a"]
    b1 = _evaluate_frozen_predictions_csv(B_VAL_PREDICTIONS, "candidate_b_probability", "candidate_b_predicted_correct")
    c1 = _evaluate_frozen_predictions_csv(C_VAL_PREDICTIONS, "candidate_c_probability", "candidate_c_predicted_correct")
    e1 = result["e1e2"]["e1"]
    e2 = result["e1e2"]["e2"]
    f1 = result["val_pooled"]

    def row(label: str, block: dict[str, Any], has_binary: bool, n_key: str = "n") -> str:
        n = block.get(n_key, block.get("n_scored"))
        if has_binary:
            return (
                f"| {label} | {n} | {_fmt(block.get('auc'))} | {_fmt(block.get('balanced_accuracy'))} | "
                f"{_fmt(block.get('matthews_correlation'))} | {_fmt(block.get('cohen_kappa'))} | "
                f"{_fmt(block.get('f1'))} | {_fmt(block.get('false_rejection_rate'))} | "
                f"{_fmt(block.get('false_acceptance_rate'))} |"
            )
        return f"| {label} | {n} | {_fmt(block.get('auc'))} | NA | NA | NA | NA | NA | NA |"

    report = f"""# Baseline A vs Candidate B1 vs Candidate C1 vs Candidate E V1 vs Candidate E2 vs Candidate F1 — validation

All six evaluated on validation (each candidate's own native, already-usable
row subset -- see each candidate's own report for its exact exclusion
rules). Baseline A / Candidate E V1 use the fixed threshold 58; Candidate
B1/C1/F1 use their own dev-only threshold-selection rule; Candidate E2 has
no threshold (AUC only), per its own protocol.

| Model | N | AUC | Balanced accuracy | MCC | Cohen's kappa | F1 | False rejection rate | False acceptance rate |
|---|---|---|---|---|---|---|---|---|
{row("Baseline A", baseline_a, True, n_key="n")}
{row("Candidate B1", b1, True)}
{row("Candidate C1", c1, True)}
{row("Candidate E V1", e1, True)}
{row("Candidate E2", e2, False)}
{row(f"Candidate F1 ({result['variant']})", f1, True, n_key="n_scored")}

---

*`final_test` was not loaded by any code in this report. Candidate E V1 and
Candidate E2 were re-run unmodified on validation for this comparison only
(they were not previously evaluated on validation); Candidate B1/C1's
numbers are read from their own existing, already-frozen validation
predictions CSVs.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def write_reports(result: dict[str, Any]) -> str:
    write_development_report(result)
    passes, _reason = write_validation_report(result)
    write_comparison_report(result)
    return "PASSES" if passes else "does not pass -> recommend Candidate F2 (not implemented)"
