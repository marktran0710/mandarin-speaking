"""Honest model-selection audit for OMPAL tone correctness.

This is deliberately a *research audit*, not an inference module.  It measures
the complete selection procedure using nested, speaker-disjoint cross
validation on the frozen ``train`` partition only.  It never opens Dev or Test
and it has no access to speaker ID, character, word, or token ID as a feature.

The audit answers a useful question before changing a learner-facing model:
does selecting a contour representation, regularisation value and operating
threshold still improve when the held-out speaker was not involved in any of
those choices?

Run from ``backend``:

    python -m pronunciation.wav2vec_tone.nested_speaker_audit

The output is an evidence artifact; it must not be used to replace a sealed
evaluation or to select a deployed threshold after Test has been opened.
"""

from __future__ import annotations

import csv
import json
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent / "data"
MANIFEST = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
TRAJECTORIES = DATA_DIR / "phase_c6_trajectories.npz"
OUTPUT = DATA_DIR / "ompal_nested_speaker_audit.json"
PREDICTIONS = DATA_DIR / "ompal_nested_speaker_audit_oof.csv"

TONES = ("1", "2", "3", "4")
OUTER_FOLDS = 5
INNER_FOLDS = 4
C_GRID = (0.01, 0.1, 1.0, 10.0)
THRESHOLDS = tuple(np.linspace(0.20, 0.80, 61))
SEED = 0


@dataclass(frozen=True)
class Candidate:
    representation: str
    C: float


def normalise_trajectory(matrix: np.ndarray) -> np.ndarray:
    """Median-centre each token, retaining missing F0 for fold-local imputation."""
    # Entirely unvoiced rows are intentionally retained as NaN so that the
    # imputer is fit on the corresponding training fold.  Silence the expected
    # NumPy warning rather than silently replacing it with a label-dependent
    # value.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        median = np.nanmedian(matrix, axis=1, keepdims=True)
    return matrix - median


def design(base: np.ndarray, tones: np.ndarray) -> np.ndarray:
    """Acoustic values + known expected tone + acoustic/tone interactions.

    The expected tone comes from the practice prompt and is available at
    inference.  No identity or lexical feature is included.
    """
    dummies = np.stack([(tones == tone).astype(float) for tone in TONES[1:]], axis=1)
    return np.hstack([base, dummies, *[base * d[:, None] for d in dummies.T]])


def make_estimator(C: float):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(C=C, class_weight="balanced", max_iter=8000,
                           random_state=SEED),
    )


def score_metrics(y: np.ndarray, probabilities: np.ndarray, threshold: float) -> dict:
    from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
                                 precision_score, recall_score, roc_auc_score)

    prediction = (probabilities >= threshold).astype(int)
    return {
        "roc_auc": float(roc_auc_score(y, probabilities)),
        "pr_auc_incorrect": float(average_precision_score(y, probabilities)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "incorrect_precision": float(precision_score(y, prediction, zero_division=0)),
        "incorrect_recall": float(recall_score(y, prediction, zero_division=0)),
        "threshold": float(threshold),
    }


def best_threshold(y: np.ndarray, probabilities: np.ndarray) -> float:
    """Select an operating point from *inner-fold OOF predictions only*."""
    from sklearn.metrics import balanced_accuracy_score

    return max(THRESHOLDS,
               key=lambda threshold: balanced_accuracy_score(y, probabilities >= threshold))


def grouped_splits(groups: np.ndarray, folds: int):
    from sklearn.model_selection import GroupKFold

    unique_groups = np.unique(groups)
    if len(unique_groups) < folds:
        raise ValueError(f"need {folds} speakers, found {len(unique_groups)}")
    return GroupKFold(n_splits=folds).split(np.zeros(len(groups)), groups=groups)


def candidate_inner_oof(candidate: Candidate, base: np.ndarray, tones: np.ndarray,
                        y: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """Generate selection scores without ever predicting a seen speaker."""
    matrix = design(base, tones)
    oof = np.full(len(y), np.nan)
    for fit_index, holdout_index in grouped_splits(groups, INNER_FOLDS):
        model = make_estimator(candidate.C)
        model.fit(matrix[fit_index], y[fit_index])
        oof[holdout_index] = model.predict_proba(matrix[holdout_index])[:, 1]
    if not np.isfinite(oof).all():
        raise RuntimeError("inner OOF is incomplete")
    return oof


def select_candidate(bases: dict[str, np.ndarray], tones: np.ndarray, y: np.ndarray,
                     groups: np.ndarray) -> tuple[Candidate, float, dict]:
    """Select feature representation, C and threshold inside one outer fold."""
    from sklearn.metrics import average_precision_score

    scores: list[dict] = []
    for representation, base in bases.items():
        for C in C_GRID:
            candidate = Candidate(representation, C)
            oof = candidate_inner_oof(candidate, base, tones, y, groups)
            threshold = best_threshold(y, oof)
            metrics = score_metrics(y, oof, threshold)
            # Ranking uses PR-AUC, which is independent of the threshold.
            scores.append({"candidate": candidate, "threshold": threshold, **metrics})
    chosen = max(scores, key=lambda entry: entry["pr_auc_incorrect"])
    serialised = [{"representation": item["candidate"].representation,
                   "C": item["candidate"].C,
                   **{key: value for key, value in item.items() if key != "candidate"}}
                  for item in scores]
    return chosen["candidate"], chosen["threshold"], {"candidates": serialised}


def load_train_only() -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load cache and fail closed if row order or partitions are unexpected."""
    rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8")))
    rows = [row for row in rows if row["split"] in ("train", "dev")]
    cache = np.load(CACHE, allow_pickle=True)
    trajectory = np.load(TRAJECTORIES, allow_pickle=True)["learner"]
    token_ids = cache["token_ids"].astype(str)
    if len(rows) != len(token_ids) or len(trajectory) != len(token_ids):
        raise RuntimeError("feature caches and manifest do not have identical rows")
    if [row["token_id"] for row in rows] != token_ids.tolist():
        raise RuntimeError("feature-cache order does not match manifest")
    split = cache["split"].astype(str)
    # It is intentional that Dev is visible to the function only to reject it.
    train = split == "train"
    if not train.any() or np.any(split[train] != "train"):
        raise RuntimeError("could not establish a train-only partition")

    tones = cache["tone"].astype(str)[train]
    y = cache["y"].astype(int)[train]
    speakers = cache["speaker"].astype(str)[train]
    ids = token_ids[train]
    if set(np.unique(tones)) - set(TONES) or not set(np.unique(y)).issubset({0, 1}):
        raise RuntimeError("unexpected target domain")

    contour = normalise_trajectory(trajectory[train])
    summary = cache["praat"][train]
    return {"R2_contour": contour, "R3_contour_plus_summary": np.hstack([contour, summary])}, tones, y, speakers, ids


def run_audit() -> dict:
    bases, tones, y, speakers, token_ids = load_train_only()
    outer_probabilities = np.full(len(y), np.nan)
    outer_thresholds = np.full(len(y), np.nan)
    outer_choice: list[dict] = []

    for fold, (fit_index, holdout_index) in enumerate(grouped_splits(speakers, OUTER_FOLDS), start=1):
        train_bases = {name: value[fit_index] for name, value in bases.items()}
        candidate, threshold, selection = select_candidate(
            train_bases, tones[fit_index], y[fit_index], speakers[fit_index])
        model = make_estimator(candidate.C)
        model.fit(design(bases[candidate.representation][fit_index], tones[fit_index]), y[fit_index])
        outer_probabilities[holdout_index] = model.predict_proba(
            design(bases[candidate.representation][holdout_index], tones[holdout_index]))[:, 1]
        outer_thresholds[holdout_index] = threshold
        outer_choice.append({
            "fold": fold,
            "held_out_speakers": sorted(np.unique(speakers[holdout_index]).tolist()),
            "selected_representation": candidate.representation,
            "selected_C": candidate.C,
            "selected_threshold": threshold,
            **selection,
        })

    if not np.isfinite(outer_probabilities).all():
        raise RuntimeError("outer OOF is incomplete")
    # Every token was scored by a model and threshold selected without its speaker.
    decisions = outer_probabilities >= outer_thresholds
    from sklearn.metrics import balanced_accuracy_score, precision_score, recall_score
    metrics = score_metrics(y, outer_probabilities, 0.5)
    metrics.update({
        "balanced_accuracy_with_nested_threshold": float(balanced_accuracy_score(y, decisions)),
        "incorrect_precision_with_nested_threshold": float(precision_score(y, decisions, zero_division=0)),
        "incorrect_recall_with_nested_threshold": float(recall_score(y, decisions, zero_division=0)),
    })
    return {
        "protocol": {
            "partition": "frozen train only; Dev and Test not read for scoring or selection",
            "outer_cv": f"GroupKFold({OUTER_FOLDS}) by speaker_id",
            "inner_cv": f"GroupKFold({INNER_FOLDS}) by speaker_id",
            "forbidden_features": ["speaker_id", "token_id", "character", "word_script", "utterance_id"],
            "allowed_features": ["median-centred F0 trajectory", "Praat acoustic summary", "expected tone from prompt"],
            "selection_metric": "inner OOF PR-AUC for Incorrect",
            "threshold_metric": "inner OOF balanced accuracy",
            "warning": "research estimate only; never substitute for sealed Test evaluation",
        },
        "n_tokens": int(len(y)),
        "n_speakers": int(len(np.unique(speakers))),
        "incorrect_prevalence": float(y.mean()),
        "outer_oof_metrics": metrics,
        "outer_fold_selections": outer_choice,
        "rows": [
            {"token_id": token, "speaker_id": speaker, "expected_tone": tone,
             "tone_correctness": int(label == 0), "incorrect_probability": float(score),
             "nested_threshold": float(threshold), "predicted_incorrect": int(score >= threshold)}
            for token, speaker, tone, label, score, threshold in zip(
                token_ids, speakers, tones, y, outer_probabilities, outer_thresholds)
        ],
    }


def main() -> None:
    report = run_audit()
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with PREDICTIONS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report["rows"][0]))
        writer.writeheader()
        writer.writerows(report["rows"])
    metrics = report["outer_oof_metrics"]
    print(f"nested speaker audit: {report['n_tokens']} tokens / {report['n_speakers']} speakers")
    print(f"ROC-AUC {metrics['roc_auc']:.3f}; PR-AUC {metrics['pr_auc_incorrect']:.3f}; "
          f"BA (nested threshold) {metrics['balanced_accuracy_with_nested_threshold']:.3f}")
    print(f"artifacts: {OUTPUT.name}, {PREDICTIONS.name}")


if __name__ == "__main__":
    main()
