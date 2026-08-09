"""Nested, speaker-disjoint OOF audit for a produced-tone T1--T4 candidate.

OMPAL only says whether a learner produced the prompted tone correctly.  This
candidate treats the prompt tone as a produced-tone *target* only for those
human-correct tokens; incorrect tokens are excluded instead of receiving a
fabricated tone label.  The model features are strictly acoustic:

* frozen Wav2Vec mean audio embeddings;
* a median-centred F0 trajectory; and
* Praat acoustic measurements.

It never exposes expected tone/prompt, character, pinyin, word, speaker,
token, or utterance identity to an estimator.  Speaker ID is used only for
GroupKFold.  Model family, representation and regularisation are selected
inside each outer Train-only fold, producing an honest train OOF estimate.
Dev and Test are neither scored nor used for selection.

Run from ``backend``::

    python -m pronunciation.wav2vec_tone.produced_tone_fusion_nested
"""

from __future__ import annotations

import csv
import json
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pronunciation.wav2vec_tone.produced_tone_baseline import contour_and_register


DATA_DIR = Path(__file__).resolve().parent / "data"
MANIFEST = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
TRAJECTORIES = DATA_DIR / "phase_c6_trajectories.npz"
OUTPUT = DATA_DIR / "ompal_produced_tone_fusion_nested_train.json"
PREDICTIONS = DATA_DIR / "ompal_produced_tone_fusion_nested_train_oof.csv"

TONES = ("1", "2", "3", "4")
OUTER_FOLDS = 5
INNER_FOLDS = 3
# A deliberately small, fixed grid.  Wav2Vec-only and fusion are the two
# product candidates; the F0/Praat-only baseline remains in the artifact input
# but is not a selectable final model.  This yields 65 fits for 5 outer x 3
# inner nested CV on CPU rather than searching an open-ended model space.
C_GRID = (0.03, 0.1)
SELECTABLE_REPRESENTATIONS = ("wav2vec_mean", "fusion")
SEED = 0


@dataclass(frozen=True)
class Candidate:
    representation: str
    C: float


def utterance_relative_register(rows: list[dict], register: np.ndarray) -> np.ndarray:
    """Current token's register relative to medians in its own recording.

    ``utterance_id`` is only used to pool acoustic measurements, then is
    discarded. It never enters the estimator as an identity feature.
    """
    groups: dict[str, list[float]] = {}
    for row, value in zip(rows, register[:, 0]):
        if np.isfinite(value):
            groups.setdefault(row["utterance_id"], []).append(float(value))
    medians = {key: float(np.median(values)) for key, values in groups.items()}
    return np.asarray([
        [float(value) - medians.get(row["utterance_id"], float("nan"))]
        if np.isfinite(value) else [float("nan")]
        for row, value in zip(rows, register[:, 0])
    ])


def load_train_only(
    manifest_path: Path = MANIFEST,
    cache_path: Path = CACHE,
    trajectory_path: Path = TRAJECTORIES,
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray]:
    """Load human-correct T1--T4 Train rows and acoustic matrices only.

    The cache can contain Dev features for other experiments, but this function
    selects only ``split == train`` before it assembles labels or inputs.  It
    fails closed if a Test row exists in the cache so a future cache format
    cannot silently unseal Test data.
    """
    train_rows = {
        row["token_id"]: row
        for row in csv.DictReader(manifest_path.open(encoding="utf-8"))
        if row["split"] == "train"
    }
    cache = np.load(cache_path, allow_pickle=True)
    required = {"mean", "praat", "token_ids", "split", "speaker"}
    missing = required - set(cache.files)
    if missing:
        raise ValueError(f"feature cache missing {sorted(missing)}")
    split = cache["split"].astype(str)
    if np.any(split == "test"):
        raise ValueError("TEST LOCK VIOLATION: feature cache contains test rows")
    train = split == "train"
    if not train.any():
        raise ValueError("feature cache has no train rows")
    token_ids = cache["token_ids"].astype(str)[train]
    if any(token not in train_rows for token in token_ids):
        raise ValueError("train cache/manifest token IDs do not match")

    trajectory_data = np.load(trajectory_path, allow_pickle=True)
    if "learner" not in trajectory_data.files:
        raise ValueError("trajectory cache has no learner matrix")
    if len(trajectory_data["learner"]) != len(cache["token_ids"]):
        raise ValueError("trajectory cache and feature cache have different row counts")

    rows = [train_rows[token] for token in token_ids]
    labels = np.asarray([row["expected_tone"] for row in rows], dtype=str)
    is_human_correct = np.asarray([row["tone_correctness"] == "1" for row in rows])
    keep = is_human_correct & np.isin(labels, TONES)
    if not keep.any():
        raise ValueError("no human-correct T1--T4 Train tokens")

    contours, register = contour_and_register(np.asarray(trajectory_data["learner"])[train])
    relative_register = utterance_relative_register(rows, register)
    f0_praat = np.hstack([
        contours[keep], register[keep], relative_register[keep],
        np.asarray(cache["praat"])[train][keep],
    ])
    wav2vec = np.asarray(cache["mean"])[train][keep]
    matrices = {
        "f0_praat": f0_praat,
        "wav2vec_mean": wav2vec,
        "fusion": np.hstack([wav2vec, f0_praat]),
    }
    speakers = cache["speaker"].astype(str)[train][keep]
    return matrices, labels[keep], speakers, token_ids[keep]


def make_estimator(C: float):
    """Fold-local preprocessing plus a fast, uncalibrated linear SVM."""
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import LinearSVC

    return make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LinearSVC(
            C=C,
            class_weight="balanced",
            tol=1e-2,
            max_iter=10000,
            random_state=SEED,
        ),
    )


def grouped_splits(groups: np.ndarray, folds: int):
    from sklearn.model_selection import GroupKFold

    if len(np.unique(groups)) < folds:
        raise ValueError(f"need at least {folds} speakers, got {len(np.unique(groups))}")
    return GroupKFold(n_splits=folds).split(np.zeros(len(groups)), groups=groups)


def oof_decision_scores(features: np.ndarray, labels: np.ndarray, groups: np.ndarray,
                        *, folds: int, C: float) -> np.ndarray:
    """Uncalibrated SVM margins, one held-out-speaker score per token."""
    scores = np.full((len(labels), len(TONES)), np.nan, dtype=float)
    for fit, holdout in grouped_splits(groups, folds):
        if set(groups[fit]) & set(groups[holdout]):
            raise RuntimeError("speaker leakage in GroupKFold split")
        estimator = make_estimator(C)
        estimator.fit(features[fit], labels[fit])
        predicted = estimator.decision_function(features[holdout])
        if predicted.ndim == 1:
            predicted = predicted[:, None]
        for index, label in enumerate(estimator.classes_):
            scores[holdout, TONES.index(str(label))] = predicted[:, index]
    if not np.isfinite(scores).all():
        raise RuntimeError("incomplete OOF decision scores; a tone was absent from a fold's training data")
    return scores


def macro_f1(labels: np.ndarray, scores: np.ndarray) -> float:
    from sklearn.metrics import f1_score

    predicted = np.asarray(TONES)[np.argmax(scores, axis=1)]
    return float(f1_score(labels, predicted, labels=list(TONES), average="macro", zero_division=0))


def select_candidate(
    matrices: dict[str, np.ndarray], labels: np.ndarray, speakers: np.ndarray, *, inner_folds: int
) -> tuple[Candidate, list[dict]]:
    """Select representation/C using only inner speaker-disjoint OOF rows."""
    candidates: list[dict] = []
    for representation in SELECTABLE_REPRESENTATIONS:
        features = matrices[representation]
        for C in C_GRID:
            scores = oof_decision_scores(features, labels, speakers, folds=inner_folds, C=C)
            candidates.append({
                "candidate": Candidate(representation, C),
                "inner_oof_macro_f1": macro_f1(labels, scores),
            })
    selected = max(candidates, key=lambda item: item["inner_oof_macro_f1"])
    report = [
        {"representation": item["candidate"].representation, "C": item["candidate"].C,
         "inner_oof_macro_f1": item["inner_oof_macro_f1"]}
        for item in candidates
    ]
    return selected["candidate"], report


def evaluate_nested_oof(
    matrices: dict[str, np.ndarray], labels: np.ndarray, speakers: np.ndarray, token_ids: np.ndarray,
    *, outer_folds: int = OUTER_FOLDS, inner_folds: int = INNER_FOLDS,
) -> dict:
    """Nested CV: choose candidate inside each held-out-speaker outer fold."""
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

    if len(np.unique(speakers)) < outer_folds:
        raise ValueError(f"need at least {outer_folds} speakers")
    scores = np.full((len(labels), len(TONES)), np.nan, dtype=float)
    selected_by_row: list[str | None] = [None] * len(labels)
    fold_reports: list[dict] = []
    for fold, (fit, holdout) in enumerate(grouped_splits(speakers, outer_folds), start=1):
        fit_matrices = {name: matrix[fit] for name, matrix in matrices.items()}
        candidate, candidate_scores = select_candidate(
            fit_matrices, labels[fit], speakers[fit], inner_folds=inner_folds
        )
        if set(speakers[fit]) & set(speakers[holdout]):
            raise RuntimeError("speaker leakage in outer GroupKFold split")
        estimator = make_estimator(candidate.C)
        estimator.fit(matrices[candidate.representation][fit], labels[fit])
        predicted = estimator.decision_function(matrices[candidate.representation][holdout])
        if predicted.ndim == 1:
            predicted = predicted[:, None]
        for index, label in enumerate(estimator.classes_):
            scores[holdout, TONES.index(str(label))] = predicted[:, index]
        choice = f"{candidate.representation};C={candidate.C}"
        for row in holdout:
            selected_by_row[row] = choice
        fold_reports.append({
            "fold": fold,
            "held_out_speakers": sorted(set(speakers[holdout])),
            "n_train_tokens": int(len(fit)),
            "n_held_out_tokens": int(len(holdout)),
            "selected_representation": candidate.representation,
            "selected_C": candidate.C,
            "candidate_inner_oof": candidate_scores,
        })
    if not np.isfinite(scores).all() or any(choice is None for choice in selected_by_row):
        raise RuntimeError("outer OOF prediction is incomplete")

    predicted = np.asarray(TONES)[np.argmax(scores, axis=1)]
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, predicted, labels=list(TONES), zero_division=0
    )
    rows = []
    for token, speaker, target, decision, distribution, choice in zip(
        token_ids, speakers, labels, predicted, scores, selected_by_row
    ):
        rows.append({
            "token_id": str(token), "speaker_id": str(speaker), "human_correct": 1,
            "produced_tone_proxy": f"T{target}", "predicted_tone": f"T{decision}",
            "nested_selected_candidate": choice,
            "score_type": "uncalibrated_linear_svm_margin",
            **{f"decision_score_T{tone}": float(distribution[index]) for index, tone in enumerate(TONES)},
        })
    return {
        "protocol": {
            "partition": "frozen OMPAL Train rows only; Dev/Test never used",
            "label": "expected tone only where independently human-labelled tone_correctness=1",
            "outer_cv": f"GroupKFold({outer_folds}) by speaker_id",
            "inner_cv": f"GroupKFold({inner_folds}) by speaker_id",
            "selection_metric": "inner OOF macro-F1",
            "candidate_representations": list(SELECTABLE_REPRESENTATIONS),
            "regularisation_grid": list(C_GRID),
            "allowed_features": [
                "Wav2Vec mean embedding", "median-centred F0 trajectory",
                "token pitch register", "utterance-relative pitch register",
                "Praat acoustic summary",
            ],
            "forbidden_features": ["expected tone/prompt", "character", "pinyin", "word_script", "speaker_id", "token_id", "utterance_id"],
            "identity_usage": (
                "speaker_id is used only for GroupKFold; utterance_id is used only "
                "to aggregate label-blind pitch register within the current recording, "
                "then discarded before estimator input"
            ),
            "model": "fold-local median imputation + standardisation + deterministic LinearSVC(tol=0.01)",
            "score_type": "uncalibrated one-vs-rest decision margins; not probabilities",
            "scope": "research candidate only; not a sealed result or production model",
        },
        "n_tokens": int(len(labels)),
        "n_speakers": int(len(np.unique(speakers))),
        "class_support": {f"T{tone}": int((labels == tone).sum()) for tone in TONES},
        "outer_oof_metrics": {
            "accuracy": float(accuracy_score(labels, predicted)),
            "macro_f1": float(f1_score(labels, predicted, labels=list(TONES), average="macro", zero_division=0)),
            "per_tone": {
                f"T{tone}": {"precision": float(precision[index]), "recall": float(recall[index]),
                            "f1": float(f1[index]), "support": int(support[index])}
                for index, tone in enumerate(TONES)
            },
            "confusion_matrix_labels": [f"T{tone}" for tone in TONES],
            "confusion_matrix": confusion_matrix(labels, predicted, labels=list(TONES)).tolist(),
        },
        "outer_fold_selections": fold_reports,
        "rows": rows,
    }


def run() -> dict:
    return evaluate_nested_oof(*load_train_only())


def write_artifacts(report: dict, output: Path = OUTPUT, predictions: Path = PREDICTIONS) -> None:
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with predictions.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report["rows"][0]))
        writer.writeheader()
        writer.writerows(report["rows"])


def main() -> None:
    report = run()
    write_artifacts(report)
    metrics = report["outer_oof_metrics"]
    print(f"nested fusion OOF: {report['n_tokens']} tokens / {report['n_speakers']} speakers")
    print(f"accuracy {metrics['accuracy']:.3f}; macro-F1 {metrics['macro_f1']:.3f}")
    print(f"artifacts: {OUTPUT.name}, {PREDICTIONS.name}")


if __name__ == "__main__":
    main()
