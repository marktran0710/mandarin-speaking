"""CANDIDATE B1 — a simple, interpretable acoustic-feature baseline.

    python -m benchmarking.candidates.praat_logistic

Research question: can the acoustic features the frozen Praat pipeline
already computes (per-syllable F0 shape, duration, voicing) discriminate
OMPAL-correct from OMPAL-incorrect tones substantially better than the
current hand-crafted `directional_tone_scores` heuristic? Candidate B1 is
one L2-penalized logistic regression per expected tone (see the report's
"Model specification" section for why one-per-tone rather than one shared
model with interaction terms), fit with `benchmarking.logistic` — a small,
dependency-free Newton's-method implementation, not scikit-learn (see that
module's docstring for why).

FINAL_TEST IS NOT TOUCHED ANYWHERE IN THIS MODULE.

`load_split_rows` refuses to load the `final_test` partition unless called
with `unlock_final_test=True` AND the `OMPAL_FINAL_TEST_UNLOCKED=1`
environment variable is set — two independent, deliberately inconvenient
gates, so that neither a copy-pasted call nor a stray env var alone can open
it. Nothing in this module ever passes `unlock_final_test=True`; the two
splits loaded throughout are `development` and `validation` only.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from benchmarking.baseline_a import evaluate as evaluate_baseline_a
from benchmarking.logistic import fit as fit_logistic
from benchmarking.splits import DEFAULT_SPLIT_PATH, grouped_kfold, load_split
from benchmarking.stats import binary_agreement, roc_auc

DIAGNOSTICS_CSV = Path("benchmarking/results/human_vs_system_diagnostics.csv")
REPORT_PATH = Path("benchmarking/results/candidate_b_praat_logistic.md")
PREDICTIONS_PATH = Path("benchmarking/results/candidate_b_validation_predictions.csv")

TONES = ("1", "2", "3", "4")

#: Exactly the feature set specified for Candidate B1. `expected_tone` is not
#: a column here — it selects *which* per-tone model applies, per the A/B
#: design choice explained in the report, rather than entering any one
#: model's feature vector.
FEATURE_NAMES = (
    "normalized_f0_start",
    "normalized_f0_mid",
    "normalized_f0_end",
    "f0_range",
    "f0_slope_full",
    "f0_slope_first_half",
    "f0_slope_second_half",
    "duration_seconds",
    "voiced_fraction",
)

#: Explicitly NOT used, per the task's exclusion list. Recorded so the report
#: can state it rather than leave it implicit.
EXCLUDED_FROM_FEATURES = (
    "human ratings other than the target label (individual_rater_labels, "
    "human_accuracy, human_fluency, human_prosody)",
    "word identity (word, pinyin)",
    "speaker identity (speaker_id) — used only for CV grouping, never as a feature",
    "audio ID (audio_id)",
    "sentence ID (there is no separate sentence ID column; audio_id already excluded)",
)

CV_FOLDS = 5
CV_SEED = 20260810  # same seed as the top-level speaker split, for one auditable number
L2 = 1.0  # matches benchmarking.logistic.DEFAULT_L2; fixed, not searched

#: Candidate thresholds the dev-only selection rule scans. Coarse and fixed
#: in advance — not searched finely enough to be mistaken for tuning.
THRESHOLD_GRID = tuple(round(t, 2) for t in np.arange(0.05, 0.96, 0.01))


class FinalTestLockedError(RuntimeError):
    """Raised whenever anything tries to read the locked final_test split
    without both explicit gates open. See the module docstring."""


def load_split_rows(
    split_name: str,
    *,
    diagnostics_csv: Path = DIAGNOSTICS_CSV,
    split_path: Path = DEFAULT_SPLIT_PATH,
    unlock_final_test: bool = False,
) -> list[dict[str, Any]]:
    """Rows for one partition, excluded exactly as the official pipeline
    excludes them (already baked into `human_vs_system_diagnostics.csv`:
    neutral tone, unjudged syllables, incomplete rater panels — see
    `diagnostics.py`), further restricted to rows with usable acoustic
    features (`duration_seconds != NA` — the 14-corpus-wide utterances with
    no recoverable syllable alignment; see `tone_diagnostic_summary.md`).
    """
    if split_name == "final_test":
        if not (unlock_final_test and os.environ.get("OMPAL_FINAL_TEST_UNLOCKED") == "1"):
            raise FinalTestLockedError(
                "final_test is locked for all candidate development (see "
                "model_comparison_protocol.md). Candidate B1 never unlocks it. "
                "If you are intentionally running the one-time final evaluation "
                "after every model-selection decision is frozen, call this "
                "function with unlock_final_test=True AND set "
                "OMPAL_FINAL_TEST_UNLOCKED=1 — both, deliberately, so neither "
                "alone is enough."
            )
    elif split_name not in ("development", "validation"):
        raise ValueError(f"unknown split {split_name!r}")

    split = load_split(split_path)
    speakers = set(getattr(split, split_name))
    with diagnostics_csv.open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["speaker_id"] in speakers]
    return rows


def _usable(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    usable = [row for row in rows if row.get("duration_seconds") not in (None, "", "NA")]
    return usable, len(rows) - len(usable)


def _feature_matrix(rows: Sequence[dict[str, Any]]) -> np.ndarray:
    matrix = np.full((len(rows), len(FEATURE_NAMES)), np.nan)
    for i, row in enumerate(rows):
        for j, name in enumerate(FEATURE_NAMES):
            value = row.get(name)
            if value not in (None, "", "NA"):
                matrix[i, j] = float(value)
    return matrix


def _labels(rows: Sequence[dict[str, Any]]) -> np.ndarray:
    return np.array([1.0 if row["human_majority_tone_correct"] == "1" else 0.0 for row in rows])


class Preprocessor:
    """Median imputation + standardization, both fit on one set of rows only
    (development, or a development CV training fold) and then applied
    unchanged to whatever is transformed next. Never re-fit on validation."""

    def __init__(self, medians: np.ndarray, means: np.ndarray, scales: np.ndarray) -> None:
        self.medians = medians
        self.means = means
        self.scales = scales

    @classmethod
    def fit(cls, raw_features: np.ndarray) -> "Preprocessor":
        medians = np.nanmedian(raw_features, axis=0)
        imputed = np.where(np.isnan(raw_features), medians, raw_features)
        means = imputed.mean(axis=0)
        scales = imputed.std(axis=0)
        scales = np.where(scales < 1e-9, 1.0, scales)  # guard a constant column
        return cls(medians=medians, means=means, scales=scales)

    def transform(self, raw_features: np.ndarray) -> np.ndarray:
        imputed = np.where(np.isnan(raw_features), self.medians, raw_features)
        return (imputed - self.means) / self.scales


def _select_threshold(probabilities: np.ndarray, labels: np.ndarray) -> float:
    """The one, pre-specified threshold-selection rule: the grid point
    maximizing balanced accuracy on DEVELOPMENT out-of-fold predictions.
    Computed once, before validation is ever touched by this candidate.
    """
    best_threshold, best_score = 0.5, -1.0
    for threshold in THRESHOLD_GRID:
        predicted = probabilities >= threshold
        metrics = binary_agreement(list(predicted), list(labels.astype(bool)))
        score = metrics.get("balanced_accuracy")
        if score is not None and score > best_score:
            best_score, best_threshold = score, threshold
    return best_threshold


def run_grouped_cv(
    dev_rows_by_tone: dict[str, list[dict[str, Any]]], *, k: int = CV_FOLDS, seed: int = CV_SEED
) -> dict[str, Any]:
    """Speaker-grouped CV within development, per tone.

    All four tones share one fold partition of the 28 development speakers
    (computed once), so "fold 3" means the same held-out speakers regardless
    of which tone's model is being scored — folds are not re-randomized per
    tone, which would make the per-fold numbers harder to compare.
    """
    all_dev_speakers = sorted({row["speaker_id"] for rows in dev_rows_by_tone.values() for row in rows})
    folds = grouped_kfold(all_dev_speakers, k=k, seed=seed)

    per_tone_oof: dict[str, dict[str, np.ndarray]] = {}
    per_tone_fold_metrics: dict[str, list[dict[str, Any]]] = {tone: [] for tone in TONES}

    for tone in TONES:
        rows = dev_rows_by_tone[tone]
        raw_features = _feature_matrix(rows)
        labels = _labels(rows)
        speaker_ids = np.array([row["speaker_id"] for row in rows])

        oof_prob = np.full(len(rows), np.nan)
        for fold_index, (train_speakers, held_out_speakers) in enumerate(folds):
            train_mask = np.isin(speaker_ids, train_speakers)
            test_mask = np.isin(speaker_ids, held_out_speakers)
            if train_mask.sum() == 0 or test_mask.sum() == 0:
                continue  # this tone has no rows from one side in this fold
            if len(set(labels[train_mask])) < 2:
                continue  # degenerate training fold (all one class); skip, report as such

            preprocessor = Preprocessor.fit(raw_features[train_mask])
            model = fit_logistic(
                preprocessor.transform(raw_features[train_mask]), labels[train_mask], l2=L2
            )
            test_prob = model.predict_proba(preprocessor.transform(raw_features[test_mask]))
            oof_prob[test_mask] = test_prob

            fold_auc = roc_auc(list(test_prob), list(labels[test_mask].astype(bool)))
            per_tone_fold_metrics[tone].append({
                "fold": fold_index,
                "n_train": int(train_mask.sum()),
                "n_test": int(test_mask.sum()),
                "auc": fold_auc,
                "converged": model.converged,
            })

        per_tone_oof[tone] = {"probabilities": oof_prob, "labels": labels}

    return {"folds": folds, "oof": per_tone_oof, "fold_metrics": per_tone_fold_metrics}


def _pooled_metrics(probabilities: np.ndarray, labels: np.ndarray, threshold: float) -> dict[str, Any]:
    valid = ~np.isnan(probabilities)
    probabilities, labels = probabilities[valid], labels[valid]
    predicted = probabilities >= threshold
    metrics = binary_agreement(list(predicted), list(labels.astype(bool)))
    metrics["auc"] = roc_auc(list(probabilities), list(labels.astype(bool))) if len(probabilities) else None
    metrics["n_scored"] = int(valid.sum())
    return metrics


def fit_frozen_models(
    dev_rows_by_tone: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """The model Candidate B1 actually is: one preprocessor + one logistic
    fit per tone, trained on ALL of development. Frozen after this call —
    nothing downstream may refit on validation."""
    frozen = {}
    for tone in TONES:
        rows = dev_rows_by_tone[tone]
        raw_features = _feature_matrix(rows)
        labels = _labels(rows)
        preprocessor = Preprocessor.fit(raw_features)
        model = fit_logistic(preprocessor.transform(raw_features), labels, l2=L2)
        frozen[tone] = {"preprocessor": preprocessor, "model": model, "n_train": len(rows)}
    return frozen


def evaluate_validation_once(
    frozen: dict[str, dict[str, Any]],
    thresholds: dict[str, float],
    val_rows_by_tone: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """The single, frozen application of Candidate B1 to validation. Returns
    per-tone and pooled metrics plus the row-level predictions for export."""
    per_tone: dict[str, Any] = {}
    predictions: list[dict[str, Any]] = []
    all_prob: list[float] = []
    all_label: list[float] = []
    all_pred: list[bool] = []

    for tone in TONES:
        rows = val_rows_by_tone[tone]
        if not rows:
            per_tone[tone] = {"n": 0}
            continue
        raw_features = _feature_matrix(rows)
        labels = _labels(rows)
        preprocessor: Preprocessor = frozen[tone]["preprocessor"]
        model = frozen[tone]["model"]
        probabilities = model.predict_proba(preprocessor.transform(raw_features))
        threshold = thresholds[tone]
        predicted = probabilities >= threshold

        metrics = binary_agreement(list(predicted), list(labels.astype(bool)))
        metrics["auc"] = roc_auc(list(probabilities), list(labels.astype(bool)))
        metrics["threshold"] = threshold
        per_tone[tone] = metrics

        all_prob.extend(probabilities.tolist())
        all_label.extend(labels.tolist())
        all_pred.extend(predicted.tolist())

        for row, prob, pred in zip(rows, probabilities, predicted):
            predictions.append({
                "audio_id": row["audio_id"],
                "speaker_id": row["speaker_id"],
                "word": row["word"],
                "expected_tone": tone,
                "human_majority_tone_correct": row["human_majority_tone_correct"],
                "candidate_b_probability": round(float(prob), 4),
                "candidate_b_threshold": threshold,
                "candidate_b_predicted_correct": int(bool(pred)),
                "baseline_a_system_tone_correct": row["system_tone_correct"],
                "baseline_a_system_character_score": row["system_character_score"],
            })

    overall = binary_agreement(all_pred, [bool(v) for v in all_label])
    overall["auc"] = roc_auc(all_prob, [bool(v) for v in all_label]) if all_prob else None
    return {"overall": overall, "by_tone": per_tone, "predictions": predictions}


def write_predictions_csv(predictions: list[dict[str, Any]], path: Path = PREDICTIONS_PATH) -> int:
    fieldnames = [
        "audio_id", "speaker_id", "word", "expected_tone",
        "human_majority_tone_correct", "candidate_b_probability",
        "candidate_b_threshold", "candidate_b_predicted_correct",
        "baseline_a_system_tone_correct", "baseline_a_system_character_score",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(predictions)
    return len(predictions)


def _group_by_tone(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {tone: [row for row in rows if row["expected_tone"] == tone] for tone in TONES}


def run() -> dict[str, Any]:
    dev_rows_raw = load_split_rows("development")
    val_rows_raw = load_split_rows("validation")
    dev_rows, dev_excluded = _usable(dev_rows_raw)
    val_rows, val_excluded = _usable(val_rows_raw)

    dev_by_tone = _group_by_tone(dev_rows)
    val_by_tone = _group_by_tone(val_rows)

    cv = run_grouped_cv(dev_by_tone)
    thresholds = {
        tone: _select_threshold(cv["oof"][tone]["probabilities"], cv["oof"][tone]["labels"])
        for tone in TONES
    }
    cv_metrics_per_tone = {
        tone: _pooled_metrics(cv["oof"][tone]["probabilities"], cv["oof"][tone]["labels"], thresholds[tone])
        for tone in TONES
    }
    all_oof_prob = np.concatenate([cv["oof"][t]["probabilities"] for t in TONES])
    all_oof_label = np.concatenate([cv["oof"][t]["labels"] for t in TONES])
    all_oof_pred = np.concatenate([
        cv["oof"][t]["probabilities"] >= thresholds[t] for t in TONES
    ])
    valid = ~np.isnan(all_oof_prob)
    cv_overall = binary_agreement(
        list(all_oof_pred[valid]), list(all_oof_label[valid].astype(bool))
    )
    cv_overall["auc"] = roc_auc(list(all_oof_prob[valid]), list(all_oof_label[valid].astype(bool)))

    frozen = fit_frozen_models(dev_by_tone)
    validation_result = evaluate_validation_once(frozen, thresholds, val_by_tone)

    baseline_dev = evaluate_baseline_a(dev_rows)
    baseline_val = evaluate_baseline_a(val_rows)
    baseline_dev_by_tone = {tone: evaluate_baseline_a(dev_by_tone[tone]) for tone in TONES}
    baseline_val_by_tone = {tone: evaluate_baseline_a(val_by_tone[tone]) for tone in TONES}

    n_predictions = write_predictions_csv(validation_result["predictions"])

    return {
        "dev_excluded_no_features": dev_excluded,
        "val_excluded_no_features": val_excluded,
        "dev_n": len(dev_rows),
        "val_n": len(val_rows),
        "thresholds": thresholds,
        "cv_fold_metrics": cv["fold_metrics"],
        "cv_overall": cv_overall,
        "cv_by_tone": cv_metrics_per_tone,
        "validation_overall": validation_result["overall"],
        "validation_by_tone": validation_result["by_tone"],
        "baseline_dev": baseline_dev,
        "baseline_val": baseline_val,
        "baseline_dev_by_tone": baseline_dev_by_tone,
        "baseline_val_by_tone": baseline_val_by_tone,
        "n_predictions_written": n_predictions,
    }


if __name__ == "__main__":
    from benchmarking.candidates import report_praat_logistic

    result = run()
    report_praat_logistic.write_report(result)
    print(f"Predictions written to {PREDICTIONS_PATH} ({result['n_predictions_written']} rows)")
    print(f"Report written to {REPORT_PATH}")
