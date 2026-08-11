"""Report writers for Candidate F2 (partial Wav2Vec2 fine-tuning).

Reads only what `wav2vec_partial_finetune.run()` already computed. The
decision rule (STEP 12) is the SAME pre-existing rule used for every
candidate in this line (validation overall AUC >= 0.65 AND T2/T3/T4 AUC
each >= 0.60); the STEP 13 interpretation (A/B/C/D) adds two bars — a
"material improvement over Candidate F1" bar and an "unstable fold" bar —
both fixed here, before any Candidate F2 number was computed.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from benchmarking.candidates.f1_context_wav2vec import COMPARISON_MD as F1_COMPARISON_MD
from benchmarking.candidates.f1_context_wav2vec import PREDICTIONS_CSV as F1_PREDICTIONS_CSV
from benchmarking.candidates.f1_context_wav2vec import (
    B_VAL_PREDICTIONS,
    C_VAL_PREDICTIONS,
)
from benchmarking.candidates.wav2vec_partial_finetune import (
    COMPARISON_MD,
    DEV_DEV_MD,
    ENCODER_LEARNING_RATE,
    HEAD_LEARNING_RATE,
    PREDICTIONS_CSV,
    VAL_MD,
)
from benchmarking.stats import binary_agreement, roc_auc

SUBSTANTIAL_AUC_BAR = 0.65
PER_TONE_AUC_BAR = 0.60
#: STEP 13's "material improvement over Candidate F1" bar -- fixed before
#: any Candidate F2 result existed. Consistent in spirit with this whole
#: research line's other pre-specified "material gain" bars (e.g. Candidate
#: E2's 0.05 category-gain bar, Candidate F1's 0.02 "nearly tied" bar).
MATERIAL_IMPROVEMENT_BAR = 0.03
#: STEP 9/13's "unstable fold" bars -- a development CV whose held-out-
#: speaker fold AUCs vary this much, or whose worst fold sits at/below this
#: level, is flagged as unstable regardless of the pooled number.
UNSTABLE_FOLD_SD_BAR = 0.08
UNSTABLE_FOLD_MIN_AUC = 0.45


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


def _fold_overfitting_flags(fold_reports: list[dict[str, Any]]) -> list[str]:
    flags = []
    for fr in fold_reports:
        last_train_loss = fr["history"][-1]["train_loss"] if fr["history"] else None
        test_auc = fr["test_auc"]
        note = []
        if last_train_loss is not None and last_train_loss < 0.3 and (test_auc is None or test_auc < 0.55):
            note.append("low train loss but weak held-out AUC (possible overfitting)")
        if test_auc is not None and test_auc <= UNSTABLE_FOLD_MIN_AUC:
            note.append(f"held-out AUC <= {UNSTABLE_FOLD_MIN_AUC:.2f}")
        flags.append("; ".join(note) if note else "none")
    return flags


def write_development_report(result: dict[str, Any], path: Path = DEV_DEV_MD) -> None:
    base = result["base"]
    cv = result["cv_result"]
    fold_reports = cv["fold_reports"]
    ablation = result["ablation"]

    fold_lines = []
    for fr, flag in zip(fold_reports, _fold_overfitting_flags(fold_reports)):
        epochs_run = len(fr["history"])
        last = fr["history"][-1] if fr["history"] else {}
        fold_lines.append(
            f"| {fr['fold']} | {fr['n_train']} | {fr['n_early_stop']} | {fr['n_test']} | "
            f"{fr['n_pos_train']}/{fr['n_neg_train']} | {_fmt(fr['pos_weight'])}/{_fmt(fr['neg_weight'])} | "
            f"{epochs_run} | {_fmt(last.get('train_loss'))} | {_fmt(fr['best_early_stop_auc'])} | "
            f"{_fmt(fr['test_auc'])} | {flag} |"
        )

    test_aucs = [fr["test_auc"] for fr in fold_reports if fr["test_auc"] is not None]
    mean_auc = float(np.mean(test_aucs)) if test_aucs else None
    sd_auc = float(np.std(test_aucs)) if len(test_aucs) > 1 else 0.0 if test_aucs else None
    unstable = (sd_auc is not None and sd_auc >= UNSTABLE_FOLD_SD_BAR) or (test_aucs and min(test_aucs) <= UNSTABLE_FOLD_MIN_AUC)

    history_lines = []
    for fr in fold_reports:
        for h in fr["history"]:
            history_lines.append(
                f"| {fr['fold']} | {h['epoch']} | {_fmt(h['train_loss'])} | {_fmt(h['early_stop_loss'])} | {_fmt(h['early_stop_auc'])} |"
            )

    ablation_lines = "\n".join(
        f"| {label} | {v['n']} | {_fmt(v['auc_f1'])} | {_fmt(v['auc_f2'])} | {_fmt(v['delta'])} |"
        for label, v in ablation.items()
    )

    freeze = result["freeze_result"]["train_result"]

    report = f"""# Candidate F2 — development (speaker-grouped CV + overfitting check)

## STEP 1 — base checkpoint

| | |
|---|---|
| Checkpoint | `{base['checkpoint']}` |
| Checkpoint SHA-256 | `{base['checkpoint_sha256']}` |
| Architecture | Wav2Vec2Model |
| Transformer layers | {base['num_hidden_layers']} |
| Hidden dimension | {base['hidden_size']} |

## STEP 2 — partial freeze

Frozen: convolutional feature extractor, feature projection,
positional-embedding convolution + its layer norm, `encoder.layers[0:{base['n_frozen_layers']}]`.
Trainable: `{', '.join(base['trainable_modules'])}`, the linguistic-context
projection, and the binary correctness head.

Trainable parameters: {base['trainable_parameters']:,} / {base['total_parameters']:,}
({base['trainable_parameters']/base['total_parameters']:.1%}).

## STEP 6 — training recipe

No existing Wav2Vec2 FINE-TUNING convention exists anywhere in this
repository (checked before choosing any value here — the provenance audit
already established the encoder has never been fine-tuned; existing
`pronunciation/wav2vec_tone/` training code only fits classifiers on frozen
embeddings). One fixed, standard recipe was chosen instead: AdamW, encoder
LR = {ENCODER_LEARNING_RATE}, head LR = {HEAD_LEARNING_RATE}, gradient
clipping, weight decay, a small fixed epoch budget with development-only
early stopping — see `candidate_f2_protocol.json` for every exact value.

## STEP 7 — speaker-grouped development CV

Development row count: {result['dev_n']}. `n_train`/`n_early_stop` are both
INSIDE the fold's training speakers (speaker-disjoint from each other and
from the fold's held-out test speakers); `n_test` is the fold's held-out
speakers, scored only after training + early stopping finished.

| Fold | N train | N early-stop | N test | pos/neg (train) | pos/neg weight | Epochs run | Final train loss | Best early-stop AUC | Held-out speaker AUC | Overfitting flag |
|---|---|---|---|---|---|---|---|---|---|---|
{chr(10).join(fold_lines)}

Pooled out-of-fold AUC: **{_fmt(cv['pooled_auc'])}**
Mean fold held-out AUC: **{_fmt(mean_auc)}** (SD: {_fmt(sd_auc)})

## STEP 9 — overfitting / stability check

Per-epoch history (every fold):

| Fold | Epoch | Train loss | Early-stop loss | Early-stop AUC |
|---|---|---|---|---|
{chr(10).join(history_lines)}

**Stability verdict**: {"UNSTABLE" if unstable else "stable"} — bar: fold-AUC
SD >= {UNSTABLE_FOLD_SD_BAR:.2f} OR any fold's held-out AUC <=
{UNSTABLE_FOLD_MIN_AUC:.2f} (fixed before this run). Observed SD =
{_fmt(sd_auc)}, worst fold AUC = {_fmt(min(test_aucs) if test_aucs else None)}.

## Final freeze fit (all of development, before validation opened)

N train (inner): {freeze['n_train']}, N early-stop: {freeze['n_early_stop']},
epochs run: {len(freeze['history'])}, best early-stop AUC: {_fmt(freeze['best_early_stop_auc'])}.

## STEP 8 — direct Candidate F1 vs Candidate F2 ablation (identical development rows)

Candidate F1's own frozen procedure (F1a) was re-run unmodified to obtain
row-keyed out-of-fold probabilities directly comparable to Candidate F2's;
both AUCs below are computed on the SAME rows (the intersection of both
candidates' out-of-fold coverage).

| | N | AUC (Candidate F1) | AUC (Candidate F2) | Delta (F2 - F1) |
|---|---|---|---|---|
{ablation_lines}

---

*`final_test` was not loaded by any code in this evaluation. `validation`
was not loaded until AFTER this report's protocol was frozen.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


# ---------------------------------------------------------------------------
# Validation report + decision
# ---------------------------------------------------------------------------


def decision_rule(val_pooled: dict[str, Any], val_by_tone: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    overall_auc = val_pooled.get("auc")
    t2, t3, t4 = (val_by_tone.get(t, {}).get("auc") for t in ("2", "3", "4"))
    per_tone_ok = all(v is not None and v >= PER_TONE_AUC_BAR for v in (t2, t3, t4))
    passes = overall_auc is not None and overall_auc >= SUBSTANTIAL_AUC_BAR and per_tone_ok
    reason = (
        f"overall AUC {_fmt(overall_auc)} {'>=' if (overall_auc or 0) >= SUBSTANTIAL_AUC_BAR else '<'} "
        f"{SUBSTANTIAL_AUC_BAR:.2f}; T2={_fmt(t2)}, T3={_fmt(t3)}, T4={_fmt(t4)} "
        f"({'all >= ' + f'{PER_TONE_AUC_BAR:.2f}' if per_tone_ok else 'not all >= ' + f'{PER_TONE_AUC_BAR:.2f}'})"
    )
    return passes, reason


def _f1_validation_auc() -> float | None:
    if not F1_PREDICTIONS_CSV.exists():
        return None
    with F1_PREDICTIONS_CSV.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    pairs = [
        (float(row["candidate_f1_probability"]), row["human_majority_tone_correct"] == "1")
        for row in rows if row["candidate_f1_probability"] not in (None, "", "NA")
    ]
    if not pairs:
        return None
    return roc_auc([p[0] for p in pairs], [p[1] for p in pairs])


def interpret(passes: bool, unstable: bool, f2_val_auc: float | None, f1_val_auc: float | None) -> tuple[str, str]:
    delta = (f2_val_auc - f1_val_auc) if (f2_val_auc is not None and f1_val_auc is not None) else None
    if passes:
        return "A", "Candidate F2 meets the pre-specified validation criterion -- task-specific adaptation of the speech representation provides a meaningful gain beyond frozen Wav2Vec2."
    if unstable:
        return "D", (
            f"Development CV showed an unstable/overfitting pattern (fold AUC SD or a low-outlier fold "
            f"crossed the pre-specified bar -- see `candidate_f2_development.md` STEP 9) even though the "
            f"validation criterion was not met either way -- speaker-disjoint generalization does not track "
            f"development training as cleanly as the pooled numbers alone would suggest."
        )
    if delta is not None and delta >= MATERIAL_IMPROVEMENT_BAR:
        return "B", f"Candidate F2 improves materially over Candidate F1 on validation AUC (delta={_fmt(delta)} >= {MATERIAL_IMPROVEMENT_BAR:.2f}) but does not satisfy the full pass criterion."
    return "C", f"Candidate F2 remains close to Candidate F1 (delta={_fmt(delta)}) and/or below useful discrimination -- fine-tuning the top layers did not transfer a meaningful additional gain in this evaluation."


def write_validation_report(result: dict[str, Any], path: Path = VAL_MD) -> tuple[str, str, bool, str]:
    val_pooled, val_by_tone, val_by_t3 = result["val_pooled"], result["val_by_tone"], result["val_by_t3"]

    tone_lines = "\n".join(
        f"| T{tone} | {v.get('n_scored', v.get('n', 0))} | {_fmt(v.get('auc'))} | {_fmt(v.get('accuracy'))} | "
        f"{_fmt(v.get('balanced_accuracy'))} | {_fmt(v.get('matthews_correlation'))} | {_fmt(v.get('cohen_kappa'))} | "
        f"{_fmt(v.get('precision'))} | {_fmt(v.get('recall'))} | {_fmt(v.get('specificity'))} | {_fmt(v.get('f1'))} | "
        f"{_fmt(v.get('false_rejection_rate'))} | {_fmt(v.get('false_acceptance_rate'))} |"
        for tone, v in val_by_tone.items()
    )
    t3_lines = "\n".join(
        f"| {name} | {v.get('n_scored', v.get('n', 0))} | {_fmt(v.get('auc'))} | {_fmt(v.get('balanced_accuracy'))} | "
        f"{_fmt(v.get('false_rejection_rate'))} | {_fmt(v.get('false_acceptance_rate'))} |"
        for name, v in val_by_t3.items() if name in ("full_third", "half_third", "T3_to_T2_sandhi")
    )

    passes, reason = decision_rule(val_pooled, val_by_tone)

    cv = result["cv_result"]
    test_aucs = [fr["test_auc"] for fr in cv["fold_reports"] if fr["test_auc"] is not None]
    sd_auc = float(np.std(test_aucs)) if len(test_aucs) > 1 else 0.0
    unstable = (sd_auc >= UNSTABLE_FOLD_SD_BAR) or (test_aucs and min(test_aucs) <= UNSTABLE_FOLD_MIN_AUC)

    f1_val_auc = _f1_validation_auc()
    verdict, verdict_reason = interpret(passes, unstable, val_pooled.get("auc"), f1_val_auc)

    report = f"""# Candidate F2 — validation (ONE-SHOT evaluation)

Frozen after development (checkpoint `{result['checkpoint_sha256'][:16]}...`);
applied exactly once to validation ({result['val_n']} rows), no retraining,
no threshold re-selection. Threshold ({_fmt(result['threshold'])}) selected
on development CV out-of-fold predictions only. `final_test` was not
loaded.

## Overall

| Metric | Value |
|---|---|
| N | {val_pooled.get('n_scored')} |
| AUC | {_fmt(val_pooled.get('auc'))} |
| Accuracy | {_fmt(val_pooled.get('accuracy'))} |
| Balanced accuracy | {_fmt(val_pooled.get('balanced_accuracy'))} |
| MCC | {_fmt(val_pooled.get('matthews_correlation'))} |
| Cohen's kappa | {_fmt(val_pooled.get('cohen_kappa'))} |
| Precision | {_fmt(val_pooled.get('precision'))} |
| Recall | {_fmt(val_pooled.get('recall'))} |
| Specificity | {_fmt(val_pooled.get('specificity'))} |
| F1 | {_fmt(val_pooled.get('f1'))} |
| False rejection rate | {_fmt(val_pooled.get('false_rejection_rate'))} |
| False acceptance rate | {_fmt(val_pooled.get('false_acceptance_rate'))} |

## Per tone

| Tone | N | AUC | Accuracy | Balanced accuracy | MCC | Cohen's kappa | Precision | Recall | Specificity | F1 | False rejection rate | False acceptance rate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
{tone_lines}

## T3 context

| Category | N | AUC | Balanced accuracy | False rejection rate | False acceptance rate |
|---|---|---|---|---|---|
{t3_lines}

## High-confidence diagnostic subset (already-defined, not redefined)

| | N | AUC | Balanced accuracy | False rejection rate | False acceptance rate |
|---|---|---|---|---|---|
| High-confidence subset | {result['hc_n']} | {_fmt(result['hc_metrics'].get('auc'))} | {_fmt(result['hc_metrics'].get('balanced_accuracy'))} | {_fmt(result['hc_metrics'].get('false_rejection_rate'))} | {_fmt(result['hc_metrics'].get('false_acceptance_rate'))} |
| All validation rows (for comparison) | {val_pooled.get('n_scored')} | {_fmt(val_pooled.get('auc'))} | {_fmt(val_pooled.get('balanced_accuracy'))} | {_fmt(val_pooled.get('false_rejection_rate'))} | {_fmt(val_pooled.get('false_acceptance_rate'))} |

## STEP 12 — decision rule (unchanged: validation overall AUC >= {SUBSTANTIAL_AUC_BAR:.2f} AND T2/T3/T4 AUC each >= {PER_TONE_AUC_BAR:.2f}; T1 reported, not gating)

**{"PASSES" if passes else "does not pass"}** -- {reason}

## STEP 13 — interpretation

**{verdict}.** {verdict_reason}

Candidate F1 validation AUC (for reference): {_fmt(f1_val_auc)}. Candidate F2
validation AUC: {_fmt(val_pooled.get('auc'))}. Delta: {_fmt((val_pooled.get('auc') - f1_val_auc) if (val_pooled.get('auc') is not None and f1_val_auc is not None) else None)}.

---

*`final_test` was not loaded by any code in this evaluation.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return verdict, verdict_reason, passes, reason


# ---------------------------------------------------------------------------
# STEP 14 -- A / B1 / C1 / E1 / E2 / F1 / F2 comparison
# ---------------------------------------------------------------------------

ROLE = {
    "Baseline A": "hand-crafted acoustic scorer",
    "Candidate B1": "hand-crafted-feature learned classifier",
    "Candidate C1": "learned correctness classifier (frozen embedding)",
    "Candidate E V1": "hand-crafted acoustic scorer (corrected)",
    "Candidate E2": "context-aware diagnostic scorer (not a correctness classifier)",
    "Candidate F1": "learned correctness classifier (frozen embedding + context)",
    "Candidate F2": "learned correctness classifier (fine-tuned embedding + context)",
}


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


def _f1_pooled_from_csv() -> dict[str, Any]:
    with F1_PREDICTIONS_CSV.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labels = [row["human_majority_tone_correct"] == "1" for row in rows]
    probabilities = [float(row["candidate_f1_probability"]) for row in rows if row["candidate_f1_probability"] not in ("", "NA")]
    predicted = [bool(int(row["candidate_f1_predicted_correct"])) for row in rows if row["candidate_f1_predicted_correct"] not in ("", "NA")]
    metrics = binary_agreement(predicted, [l for l, row in zip(labels, rows) if row["candidate_f1_predicted_correct"] not in ("", "NA")])
    metrics["auc"] = roc_auc(probabilities, [l for l, row in zip(labels, rows) if row["candidate_f1_probability"] not in ("", "NA")])
    metrics["n"] = len(rows)
    return metrics


def write_comparison_report(result: dict[str, Any], path: Path = COMPARISON_MD) -> None:
    baseline_a = result["baseline_a"]
    b1 = _evaluate_frozen_predictions_csv(B_VAL_PREDICTIONS, "candidate_b_probability", "candidate_b_predicted_correct")
    c1 = _evaluate_frozen_predictions_csv(C_VAL_PREDICTIONS, "candidate_c_probability", "candidate_c_predicted_correct")
    e1 = result["e1e2"]["e1"]
    e2 = result["e1e2"]["e2"]
    f1 = _f1_pooled_from_csv()
    f2 = result["val_pooled"]

    def row(label: str, block: dict[str, Any], has_binary: bool, n_key: str = "n") -> str:
        n = block.get(n_key, block.get("n_scored"))
        role = ROLE.get(label, "")
        if has_binary:
            return f"| {label} | {role} | {n} | {_fmt(block.get('auc'))} | {_fmt(block.get('balanced_accuracy'))} |"
        return f"| {label} | {role} | {n} | {_fmt(block.get('auc'))} | NA |"

    report = f"""# Baseline A vs Candidate B1 vs C1 vs E V1 vs E2 vs F1 vs F2 — validation

Primary column: ROC AUC. `Candidate E2` is a context-aware DIAGNOSTIC
scorer, not a correctness classifier -- its purpose (explain/localize a
learner's tone error against a linguistic-context template) is not the same
as Candidate C1/F1/F2's purpose (predict OMPAL expert correctness directly).
The two should not be read as competing on the same task.

| Model | Role | N | AUC | Balanced accuracy |
|---|---|---|---|---|
{row("Baseline A", baseline_a, True, n_key="n")}
{row("Candidate B1", b1, True)}
{row("Candidate C1", c1, True)}
{row("Candidate E V1", e1, True)}
{row("Candidate E2", e2, False)}
{row("Candidate F1", f1, True)}
{row("Candidate F2", f2, True, n_key="n_scored")}

---

*`final_test` was not loaded by any code in this report. Candidate E V1 and
Candidate E2 were re-run unmodified on validation for this comparison only.
Candidate B1/C1/F1's numbers are read from their own existing, already-
frozen validation predictions CSVs.*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")


def write_reports(result: dict[str, Any]) -> str:
    write_development_report(result)
    verdict, _reason, _passes, _decision_reason = write_validation_report(result)
    write_comparison_report(result)
    return verdict
