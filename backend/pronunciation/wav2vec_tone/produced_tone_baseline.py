"""Speaker-disjoint baseline for *produced* Mandarin tone (T1--T4).

OMPAL labels whether a prompted tone was judged correct, not the tone a learner
actually produced.  Consequently this module uses only ``tone_correctness=1``
tokens: for those tokens the prompted tone is a defensible proxy for the
produced tone.  Incorrect tokens are deliberately excluded rather than being
given a guessed produced-tone label.

The model consumes only normalised F0 trajectories and Praat acoustic summary
measurements.  Character, pinyin, prompt/expected tone, token ID, utterance ID
and speaker ID are never model features.  Speaker ID is used exclusively for
``GroupKFold`` splitting.

This is an OOF research baseline, not a deployed V2 tone model and not a
sealed-test result.  It reads frozen Train rows only; Dev and Test are never
used for model selection, feature fitting or scoring.

Run from ``backend``::

    python -m pronunciation.wav2vec_tone.produced_tone_baseline
"""

from __future__ import annotations

import csv
import json
import warnings
from pathlib import Path

import numpy as np


DATA_DIR = Path(__file__).resolve().parent / "data"
MANIFEST = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
TRAJECTORIES = DATA_DIR / "phase_c6_trajectories.npz"
OUTPUT = DATA_DIR / "ompal_produced_tone_train_oof.json"
PREDICTIONS = DATA_DIR / "ompal_produced_tone_train_oof.csv"

TONES = ("1", "2", "3", "4")
FOLDS = 5
SEED = 0
DEFAULT_C = 1.0
TRAJECTORY_CACHE_SCHEMA_VERSION = "phase_c6_f0_trajectory.v1"
TRAJECTORY_CACHE_UNIT = "semitones_re_1hz"
PITCH_REGISTER_UNIT = "semitones_re_1hz"


def normalise_trajectory(trajectory: np.ndarray) -> np.ndarray:
    """Median-centre a per-token semitone trajectory.

    Per-token centring removes speaker pitch register without using speaker
    identity.  All-unvoiced rows stay missing; median imputation is fit inside
    each training fold by :func:`make_estimator`.

    ``phase_c6_trajectories.npz`` is already in ``semitones_re_1hz``.  This
    function must never call ``log2``: doing so is a double conversion that
    non-linearly warps the F0 contour.
    """
    # Entirely unvoiced tokens remain missing and are imputed in a fold-local
    # pipeline.  Suppress NumPy's descriptive warning without replacing their
    # missing acoustic evidence with a synthetic contour.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        median = np.nanmedian(trajectory, axis=1, keepdims=True)
    return np.asarray(trajectory, dtype=float) - median


def contour_and_register(trajectory: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return centred contour plus a valid per-token pitch-register feature.

    The register is the token median in the same semitone unit as the cache.
    It is derived from the current audio only, not speaker identity, labels,
    character, or prompt.  Fold-local imputation/scaling in :func:`make_estimator`
    handles unvoiced rows.  Keeping it separate preserves contour shape while
    allowing a model to test whether absolute register is useful on unseen
    speakers rather than assuming it is an identity feature.
    """
    values = np.asarray(trajectory, dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        register = np.nanmedian(values, axis=1, keepdims=True)
    return normalise_trajectory(values), register


def make_estimator(C: float = DEFAULT_C):
    """A fold-local imputer/scaler plus a regularised multiclass classifier."""
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(
            C=C,
            class_weight="balanced",
            max_iter=8000,
            random_state=SEED,
        ),
    )


def load_train_only(
    manifest_path: Path = MANIFEST,
    cache_path: Path = CACHE,
    trajectory_path: Path = TRAJECTORIES,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return Train-only acoustic features, labels, speakers and token IDs.

    ``expected_tone`` is read only to form the target after a human correct
    label verifies it.  It is intentionally absent from the returned feature
    matrix.
    """
    # Keep only Train rows while loading the label source.  In particular, no
    # Dev/Test label is ever returned to, or observed by, the classifier.
    train_rows = {
        row["token_id"]: row
        for row in csv.DictReader(manifest_path.open(encoding="utf-8"))
        if row["split"] == "train"
    }
    cache = np.load(cache_path, allow_pickle=True)
    required = {"praat", "token_ids", "split", "speaker"}
    missing = required - set(cache.files)
    if missing:
        raise ValueError(f"feature cache missing {sorted(missing)}")
    split = cache["split"].astype(str)
    train = split == "train"
    if not train.any():
        raise ValueError("feature cache has no Train rows")
    ids = cache["token_ids"].astype(str)[train]
    if any(token_id not in train_rows for token_id in ids):
        raise ValueError("Train cache/manifest token IDs do not match")

    trajectory_store = np.load(trajectory_path, allow_pickle=True)
    if "learner" not in trajectory_store.files:
        raise ValueError("trajectory cache has no learner trajectories")
    all_trajectories = trajectory_store["learner"]
    if len(all_trajectories) != len(cache["token_ids"]):
        raise ValueError("trajectory cache and feature cache have different row counts")

    rows = [train_rows[token_id] for token_id in ids]
    labels = np.asarray([row["expected_tone"] for row in rows], dtype=str)
    human_correct = np.asarray([row["tone_correctness"] == "1" for row in rows])
    valid_tone = np.isin(labels, TONES)
    keep = human_correct & valid_tone
    if not keep.any():
        raise ValueError("no human-correct T1--T4 Train tokens")

    # The 10-vector is an acoustic-only summary; neither the prompt nor any
    # identity column appears in it.  Keep it alongside the relative contour.
    contours, register = contour_and_register(all_trajectories[train][keep])
    summaries = np.asarray(cache["praat"][train][keep], dtype=float)
    # The 20 centred points carry shape; one absolute semitone register keeps
    # legitimate acoustic variation available without reintroducing speaker ID.
    features = np.hstack([contours, register, summaries])
    return (features, labels[keep], cache["speaker"].astype(str)[train][keep], ids[keep])


def evaluate_oof(
    features: np.ndarray,
    labels: np.ndarray,
    speakers: np.ndarray,
    token_ids: np.ndarray,
    *,
    folds: int = FOLDS,
    C: float = DEFAULT_C,
) -> dict:
    """Produce exactly one out-of-fold prediction per token, by held-out speaker."""
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
    from sklearn.model_selection import GroupKFold

    if len(np.unique(speakers)) < folds:
        raise ValueError(f"need at least {folds} speakers")
    probabilities = np.full((len(labels), len(TONES)), np.nan, dtype=float)
    fold_rows: list[dict] = []
    for fold, (fit, holdout) in enumerate(
        GroupKFold(n_splits=folds).split(features, labels, groups=speakers), start=1
    ):
        seen = set(speakers[fit])
        held_out = set(speakers[holdout])
        if seen & held_out:
            raise RuntimeError("speaker leakage in GroupKFold split")
        model = make_estimator(C)
        model.fit(features[fit], labels[fit])
        # Classes are explicitly placed into canonical T1--T4 columns.
        local = model.predict_proba(features[holdout])
        for position, tone in enumerate(model.classes_):
            probabilities[holdout, TONES.index(str(tone))] = local[:, position]
        fold_rows.append({
            "fold": fold,
            "held_out_speakers": sorted(held_out),
            "n_tokens": int(len(holdout)),
            "n_train_tokens": int(len(fit)),
        })
    if not np.isfinite(probabilities).all():
        raise RuntimeError("one or more OOF tone probabilities are missing")

    predicted = np.asarray(TONES, dtype=str)[np.argmax(probabilities, axis=1)]
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, predicted, labels=list(TONES), zero_division=0
    )
    rows = []
    for token_id, speaker, label, prediction, distribution in zip(
        token_ids, speakers, labels, predicted, probabilities
    ):
        rows.append({
            "token_id": str(token_id),
            "speaker_id": str(speaker),
            "human_correct": 1,
            "produced_tone_proxy": f"T{label}",
            "predicted_tone": f"T{prediction}",
            **{f"probability_T{tone}": float(distribution[index])
               for index, tone in enumerate(TONES)},
        })
    return {
        "protocol": {
            "partition": "frozen OMPAL Train rows only; Dev/Test never used",
            "label": "expected_tone only where human tone_correctness=1",
            "cv": f"GroupKFold({folds}) by speaker_id",
            "feature_set": (
                "20-point median-centred semitone F0 contour + one per-token "
                "median pitch-register feature (semitones re 1 Hz) + 10 acoustic "
                "Praat measurements"
            ),
            "trajectory_cache_schema": TRAJECTORY_CACHE_SCHEMA_VERSION,
            "trajectory_cache_unit": TRAJECTORY_CACHE_UNIT,
            "pitch_register_unit": PITCH_REGISTER_UNIT,
            "forbidden_features": [
                "expected_tone/prompt", "character", "pinyin", "word_script",
                "speaker_id", "token_id", "utterance_id", "embeddings",
            ],
            "model": f"fold-local median imputation + standardisation + LogisticRegression(C={C})",
            "scope": "research baseline; not a sealed-test result or deployment threshold",
        },
        "n_tokens": int(len(labels)),
        "n_speakers": int(len(np.unique(speakers))),
        "class_support": {f"T{tone}": int((labels == tone).sum()) for tone in TONES},
        "oof_metrics": {
            "accuracy": float(accuracy_score(labels, predicted)),
            "macro_f1": float(f1_score(labels, predicted, labels=list(TONES), average="macro", zero_division=0)),
            "per_tone": {
                f"T{tone}": {
                    "precision": float(precision[index]),
                    "recall": float(recall[index]),
                    "f1": float(f1[index]),
                    "support": int(support[index]),
                }
                for index, tone in enumerate(TONES)
            },
            "confusion_matrix": confusion_matrix(labels, predicted, labels=list(TONES)).tolist(),
            "confusion_matrix_labels": [f"T{tone}" for tone in TONES],
        },
        "folds": fold_rows,
        "rows": rows,
    }


def run(
    *,
    manifest_path: Path = MANIFEST,
    cache_path: Path = CACHE,
    trajectory_path: Path = TRAJECTORIES,
    folds: int = FOLDS,
    C: float = DEFAULT_C,
) -> dict:
    return evaluate_oof(*load_train_only(manifest_path, cache_path, trajectory_path), folds=folds, C=C)


def write_artifacts(report: dict, output: Path = OUTPUT, predictions: Path = PREDICTIONS) -> None:
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with predictions.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report["rows"][0]))
        writer.writeheader()
        writer.writerows(report["rows"])


def main() -> None:
    report = run()
    write_artifacts(report)
    metrics = report["oof_metrics"]
    print(f"produced-tone OOF: {report['n_tokens']} tokens / {report['n_speakers']} speakers")
    print(f"accuracy {metrics['accuracy']:.3f}; macro-F1 {metrics['macro_f1']:.3f}")
    print(f"artifacts: {OUTPUT.name}, {PREDICTIONS.name}")


if __name__ == "__main__":
    main()
