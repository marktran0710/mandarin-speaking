"""Nested Train-only ablation: Wav2Vec/F0 fusion versus fusion + nucleus F0.

The voiced-nucleus proxy is extracted from the current audio using only energy
and voiced-run evidence. It is not a phone boundary or a vowel gold label.
This audit asks whether adding that acoustic contour improves an unseen-speaker
produced-tone proxy classifier. Prompt, pinyin, characters and identities are
not estimator inputs; prompt tone is a target only where OMPAL's human label
marks the token correct.
"""

from __future__ import annotations

import csv
import json
import warnings
from pathlib import Path

import numpy as np

from pronunciation.wav2vec_tone.produced_tone_baseline import contour_and_register


DATA = Path(__file__).resolve().parent / "data"
MANIFEST = DATA / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA / "dev_features_train_dev.npz"
TRAJECTORIES = DATA / "phase_c6_trajectories.npz"
NUCLEUS = DATA / "voiced_nucleus_proxy_train.npz"
OUTPUT = DATA / "ompal_produced_tone_nucleus_nested_train.json"
PREDICTIONS = DATA / "ompal_produced_tone_nucleus_nested_train_oof.csv"
TONES = ("1", "2", "3", "4")
OUTER_FOLDS, INNER_FOLDS, C = 5, 3, 0.03


def centre(matrix: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        median = np.nanmedian(matrix, axis=1, keepdims=True)
    return np.asarray(matrix, dtype=float) - median


def relative_register(rows: list[dict], register: np.ndarray) -> np.ndarray:
    """Recording-relative acoustic register; utterance IDs are discarded."""
    by_utterance: dict[str, list[float]] = {}
    for row, value in zip(rows, register[:, 0]):
        if np.isfinite(value):
            by_utterance.setdefault(row["utterance_id"], []).append(float(value))
    medians = {key: float(np.median(values)) for key, values in by_utterance.items()}
    return np.asarray([
        [float(value) - medians.get(row["utterance_id"], float("nan"))]
        if np.isfinite(value) else [float("nan")]
        for row, value in zip(rows, register[:, 0])
    ])


def load_train_only() -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray]:
    manifest_rows = {
        row["token_id"]: row for row in csv.DictReader(MANIFEST.open(encoding="utf-8"))
        if row["split"] == "train"
    }
    cache = np.load(CACHE, allow_pickle=True)
    split = cache["split"].astype(str)
    if np.any(split == "test"):
        raise ValueError("TEST LOCK VIOLATION: cache contains Test")
    train = split == "train"
    token_ids = cache["token_ids"].astype(str)[train]
    if any(token not in manifest_rows for token in token_ids):
        raise ValueError("Train cache/manifest mismatch")
    rows = [manifest_rows[token] for token in token_ids]
    labels_all = np.asarray([row["expected_tone"] for row in rows], dtype=str)
    keep = np.asarray([row["tone_correctness"] == "1" for row in rows]) & np.isin(labels_all, TONES)

    trajectory = np.load(TRAJECTORIES, allow_pickle=True)["learner"]
    if len(trajectory) != len(cache["token_ids"]):
        raise ValueError("trajectory/cache row count mismatch")
    nucleus = np.load(NUCLEUS, allow_pickle=True)
    if nucleus["token_ids"].astype(str).tolist() != token_ids.tolist():
        raise ValueError("nucleus proxy token order must match Train cache exactly")

    contour, register = contour_and_register(trajectory[train])
    acoustic = np.hstack([
        contour[keep], register[keep], relative_register(rows, register)[keep],
        np.asarray(cache["praat"])[train][keep],
    ])
    wav2vec = np.asarray(cache["mean"])[train][keep]
    base = np.hstack([wav2vec, acoustic])
    nucleus_contour = centre(np.asarray(nucleus["trajectories"], dtype=float))[keep]
    matrices = {"fusion": base, "fusion_plus_voiced_nucleus": np.hstack([base, nucleus_contour])}
    return matrices, labels_all[keep], cache["speaker"].astype(str)[train][keep], token_ids[keep]


def model():
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import LinearSVC

    return make_pipeline(
        SimpleImputer(strategy="median"), StandardScaler(),
        LinearSVC(C=C, class_weight="balanced", tol=1e-2, max_iter=10000, random_state=0),
    )


def splits(groups: np.ndarray, n: int):
    from sklearn.model_selection import GroupKFold
    if len(np.unique(groups)) < n:
        raise ValueError(f"need {n} speakers")
    return GroupKFold(n_splits=n).split(np.zeros(len(groups)), groups=groups)


def score_oof(features: np.ndarray, labels: np.ndarray, groups: np.ndarray, folds: int) -> np.ndarray:
    scores = np.full((len(labels), len(TONES)), np.nan)
    for fit, holdout in splits(groups, folds):
        if set(groups[fit]) & set(groups[holdout]):
            raise RuntimeError("speaker leakage")
        fitted = model().fit(features[fit], labels[fit])
        margin = fitted.decision_function(features[holdout])
        for index, tone in enumerate(fitted.classes_):
            scores[holdout, TONES.index(str(tone))] = margin[:, index]
    if not np.isfinite(scores).all():
        raise RuntimeError("incomplete OOF scores")
    return scores


def macro_f1(labels: np.ndarray, scores: np.ndarray) -> float:
    from sklearn.metrics import f1_score
    return float(f1_score(labels, np.asarray(TONES)[np.argmax(scores, axis=1)], average="macro"))


def run() -> dict:
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

    matrices, labels, speakers, token_ids = load_train_only()
    scores = np.full((len(labels), 4), np.nan)
    selected: list[str | None] = [None] * len(labels)
    folds = []
    for number, (fit, holdout) in enumerate(splits(speakers, OUTER_FOLDS), 1):
        inner = {
            name: macro_f1(labels[fit], score_oof(matrix[fit], labels[fit], speakers[fit], INNER_FOLDS))
            for name, matrix in matrices.items()
        }
        chosen = max(inner, key=inner.get)
        fitted = model().fit(matrices[chosen][fit], labels[fit])
        margin = fitted.decision_function(matrices[chosen][holdout])
        for index, tone in enumerate(fitted.classes_):
            scores[holdout, TONES.index(str(tone))] = margin[:, index]
        for index in holdout:
            selected[index] = chosen
        folds.append({"fold": number, "held_out_speakers": sorted(set(speakers[holdout])),
                      "inner_oof_macro_f1": inner, "selected": chosen})
    if not np.isfinite(scores).all():
        raise RuntimeError("outer OOF incomplete")
    predicted = np.asarray(TONES)[np.argmax(scores, axis=1)]
    precision, recall, f1, support = precision_recall_fscore_support(labels, predicted, labels=list(TONES), zero_division=0)
    rows = [
        {"token_id": str(token), "speaker_id": str(speaker), "human_correct": 1,
         "produced_tone_proxy": f"T{target}", "predicted_tone": f"T{decision}",
         "selected_candidate": choice, "score_type": "uncalibrated_linear_svm_margin",
         **{f"decision_score_T{tone}": float(values[index]) for index, tone in enumerate(TONES)}}
        for token, speaker, target, decision, choice, values in zip(token_ids, speakers, labels, predicted, selected, scores)
    ]
    return {"protocol": {
        "partition": "frozen OMPAL Train only; Dev/Test never used",
        "outer_cv": "GroupKFold(5) by speaker_id", "inner_cv": "GroupKFold(3) by speaker_id",
        "selection": "inner OOF macro-F1 selects fusion vs fusion_plus_voiced_nucleus; fixed LinearSVC C=0.03",
        "allowed_features": ["Wav2Vec mean", "F0/Praat", "token pitch register",
                             "utterance-relative pitch register", "voiced-nucleus acoustic proxy"],
        "forbidden_features": ["expected_tone/prompt", "character", "pinyin", "speaker_id", "token_id", "utterance_id"],
        "identity_usage": "speaker_id is used only for GroupKFold; utterance_id only pools label-blind pitch register within the current recording and is discarded before estimator input",
        "nucleus_schema": "voiced_nucleus_proxy.v1; not a phone/vowel gold boundary",
        "score_type": "uncalibrated one-vs-rest LinearSVC margins",
    }, "n_tokens": int(len(labels)), "n_speakers": int(len(np.unique(speakers))),
        "outer_oof_metrics": {"accuracy": float(accuracy_score(labels, predicted)),
            "macro_f1": float(f1_score(labels, predicted, average="macro")),
            "per_tone": {f"T{tone}": {"precision": float(precision[i]), "recall": float(recall[i]), "f1": float(f1[i]), "support": int(support[i])} for i, tone in enumerate(TONES)},
            "confusion_matrix_labels": [f"T{tone}" for tone in TONES], "confusion_matrix": confusion_matrix(labels, predicted, labels=list(TONES)).tolist()},
        "outer_folds": folds, "rows": rows}


def main() -> None:
    report = run()
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with PREDICTIONS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report["rows"][0]))
        writer.writeheader(); writer.writerows(report["rows"])
    print(f"nucleus nested macro-F1={report['outer_oof_metrics']['macro_f1']:.3f}; artifact={OUTPUT.name}")


if __name__ == "__main__":
    main()
