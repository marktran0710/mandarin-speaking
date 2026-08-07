"""Feature-level fusion: 2304-d wav2vec2 + 10 Praat contour features -> tone.

Late fusion is closed. This concatenates the two representations and lets a
single logistic regression weigh them, which lets the Praat features act on
individual decisions rather than on an averaged posterior.

The comparison is against a matched control, not against the earlier baseline
number. Model A is the wav2vec2 block alone under exactly the preprocessing it
receives inside the fused model, so B - A isolates the contribution of the
Praat features. Comparing against a differently-preprocessed run would fold a
preprocessing difference into the reported effect.

Each block is preprocessed separately inside a ColumnTransformer: the wav2vec2
dimensions are standardised, and the Praat block is imputed then standardised.
Both are fitted inside the pipeline, so both see training folds only.

    python -m pronunciation.wav2vec_tone.feature_fusion
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.praat_baseline import FEATURE_ORDER
from pronunciation.wav2vec_tone.prepare_dataset import KEEP_TONES
from pronunciation.wav2vec_tone.train_baseline import (
    confusion,
    format_confusion,
    make_folds,
    per_class_scores,
)
from pronunciation.wav2vec_tone.train_classifier import assert_no_speaker_overlap

DATA_DIR = Path(__file__).resolve().parent / "data"
SEED = 0
N_SPLITS = 5


def logistic(seed: int):
    """The same configuration as every previous experiment. Untouched."""
    from sklearn.linear_model import LogisticRegression

    return LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)


def build_control(width: int, seed: int):
    """Model A: wav2vec2 only, under the preprocessing it gets inside Model B."""
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(StandardScaler(), logistic(seed))


def build_fusion(wav_width: int, praat_width: int, seed: int):
    """Model B: both blocks, each preprocessed on its own terms.

    A shared imputer would be wrong -- wav2vec2 dimensions are never missing,
    and the Praat block's missing values are meaningful absences of pitch. A
    single StandardScaler over the concatenation would be defensible but hides
    which block is which, and the separate transformer makes the
    2304-versus-10 asymmetry visible in the code.
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline, make_pipeline
    from sklearn.preprocessing import StandardScaler

    praat_block = Pipeline([
        # Median: the Praat features still contain the tracking outliers that
        # were deliberately not removed.
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    return make_pipeline(
        ColumnTransformer([
            ("wav2vec2", StandardScaler(), slice(0, wav_width)),
            ("praat", praat_block, slice(wav_width, wav_width + praat_width)),
        ]),
        logistic(seed),
    )


def evaluate(features, tones, speakers, folds, factory, label: str) -> dict:
    predicted = np.zeros(len(tones), dtype=int)
    covered = np.zeros(len(tones), dtype=bool)
    accuracies, models = [], []

    for number, (train_index, test_index) in enumerate(folds, start=1):
        assert_no_speaker_overlap(speakers[train_index], speakers[test_index])
        model = factory()
        model.fit(features[train_index], tones[train_index])
        guesses = model.predict(features[test_index])
        predicted[test_index] = guesses
        covered[test_index] = True
        accuracies.append(float((guesses == tones[test_index]).mean()))
        models.append(model)

    if not covered.all():
        raise RuntimeError(f"{label}: {int((~covered).sum())} samples never tested.")

    scores = per_class_scores(tones, predicted)
    return {
        "label": label,
        "predicted": predicted,
        "accuracy": float((predicted == tones).mean()),
        "cv_accuracy_mean": float(np.mean(accuracies)),
        "cv_accuracy_sd": float(np.std(accuracies, ddof=1)),
        "fold_accuracies": accuracies,
        "macro_f1": float(np.mean([scores[t]["f1"] for t in KEEP_TONES])),
        "per_tone_f1": {f"T{t}": scores[t]["f1"] for t in KEEP_TONES},
        "per_tone": {f"T{t}": scores[t] for t in KEEP_TONES},
        "confusion": confusion(tones, predicted),
        "models": models,
    }


def coefficient_share(models, wav_width: int, praat_width: int) -> str:
    """How much of the fitted model's weight actually sits on the Praat block.

    With 2304 wav2vec2 dimensions against 10 Praat ones, an L2 penalty spreads
    weight across the many correlated embedding dimensions. This reports
    whether the Praat features carry influence proportionate to their count or
    are simply outnumbered -- which the accuracy alone would not reveal.
    """
    wav_norms, praat_norms = [], []
    for model in models:
        coefficients = model[-1].coef_
        wav_norms.append(float(np.abs(coefficients[:, :wav_width]).sum()))
        praat_norms.append(float(np.abs(coefficients[:, wav_width:]).sum()))
    wav_total, praat_total = float(np.mean(wav_norms)), float(np.mean(praat_norms))
    total = wav_total + praat_total
    return "\n".join([
        "",
        "Where the fitted weight sits (mean |coefficient| sum across folds):",
        f"  wav2vec2 block : {wav_total:>9.2f}  ({wav_total / total * 100:5.1f}% of total"
        f" weight, {wav_width / (wav_width + praat_width) * 100:.1f}% of features)",
        f"  Praat block    : {praat_total:>9.2f}  ({praat_total / total * 100:5.1f}% of total"
        f" weight, {praat_width / (wav_width + praat_width) * 100:.1f}% of features)",
        f"  mean |coef| per dimension: wav2vec2 {wav_total / wav_width:.4f}, "
        f"Praat {praat_total / praat_width:.4f}",
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temporal",
                        default=str(DATA_DIR / "embeddings_frozen_temporal3.npz"))
    parser.add_argument("--praat", default=str(DATA_DIR / "praat_feature_matrix.npz"))
    parser.add_argument("--folds", type=int, default=N_SPLITS)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    wav = np.load(args.temporal, allow_pickle=True)
    praat = np.load(args.praat, allow_pickle=True)

    if not np.array_equal(wav["dataset_indices"], praat["dataset_indices"]):
        raise RuntimeError("Caches are not row-aligned; fusion would mix samples.")
    if not np.array_equal(wav["tones"], praat["tones"]):
        raise RuntimeError("Tone labels disagree between caches.")
    if not np.array_equal(wav["speakers"].astype(str), praat["speakers"].astype(str)):
        raise RuntimeError("Speaker ids disagree between caches.")

    tones, speakers = wav["tones"], wav["speakers"]
    wav_features = wav["embeddings"]
    praat_features = praat["embeddings"]
    wav_width, praat_width = wav_features.shape[1], praat_features.shape[1]
    fused = np.hstack([wav_features, praat_features])

    print("=" * 74)
    print("FEATURE-LEVEL FUSION vs MATCHED WAV2VEC2 CONTROL")
    print("=" * 74)
    print(f"samples                : {len(tones)}")
    print(f"speakers               : {len(set(speakers.tolist()))}")
    print(f"Wav2Vec2 dimensions    : {wav_width}")
    print(f"Praat dimensions       : {praat_width}   ({', '.join(FEATURE_ORDER)})")
    print(f"Total fused dimensions : {fused.shape[1]}")
    print(f"missing Praat cells    : {int(np.isnan(praat_features).sum())} "
          f"in {int(np.isnan(praat_features).any(axis=1).sum())} rows "
          f"(imputed inside folds only)")
    print("excluded as predictors : speaker_id, raw mean F0, tone-derived, "
          "corpus/variety metadata")

    folds, splitter = make_folds(tones, speakers, args.folds, args.seed)
    print(f"splitter               : {splitter}, {args.folds} folds, seed {args.seed}")

    control = evaluate(wav_features, tones, speakers, folds,
                       lambda: build_control(wav_width, args.seed),
                       "Matched Wav2Vec2 control")
    fusion = evaluate(fused, tones, speakers, folds,
                      lambda: build_fusion(wav_width, praat_width, args.seed),
                      "Feature fusion")

    axis = [f"T{t}" for t in KEEP_TONES]
    for result in (control, fusion):
        print(f"\n--- {result['label']} " + "-" * (68 - len(result['label'])))
        print(f"Accuracy: {result['accuracy'] * 100:.1f}%   "
              f"(CV {result['cv_accuracy_mean'] * 100:.1f}% +/- "
              f"{result['cv_accuracy_sd'] * 100:.1f}; folds "
              + ", ".join(f"{a * 100:.1f}" for a in result["fold_accuracies"]) + ")")
        print(f"Macro F1: {result['macro_f1']:.3f}")
        for tone in KEEP_TONES:
            print(f"  T{tone} F1: {result['per_tone_f1'][f'T{tone}']:.3f}")
        print(format_confusion(result["confusion"]))
        for true_tone, predicted_tone in ((2, 3), (3, 2), (4, 1), (4, 3)):
            value = result["confusion"][axis.index(f"T{true_tone}"),
                                        axis.index(f"T{predicted_tone}")]
            print(f"  T{true_tone} -> T{predicted_tone}: {value}")

    print("\n" + "=" * 74)
    print("ABSOLUTE DIFFERENCES  (B fusion - A matched control)")
    print("=" * 74)
    print(f"  Accuracy : {(fusion['accuracy'] - control['accuracy']) * 100:+.1f} pts"
          f"   ({fusion['accuracy'] * 100:.1f}% vs {control['accuracy'] * 100:.1f}%)")
    print(f"  Macro F1 : {fusion['macro_f1'] - control['macro_f1']:+.3f}"
          f"   ({fusion['macro_f1']:.3f} vs {control['macro_f1']:.3f})")
    for tone in KEEP_TONES:
        key = f"T{tone}"
        print(f"  {key}       : "
              f"{fusion['per_tone_f1'][key] - control['per_tone_f1'][key]:+.3f}"
              f"   ({fusion['per_tone_f1'][key]:.3f} vs "
              f"{control['per_tone_f1'][key]:.3f})")

    correct_a = control["predicted"] == tones
    correct_b = fusion["predicted"] == tones
    gains, losses = int((correct_b & ~correct_a).sum()), int((~correct_b & correct_a).sum())
    from math import comb

    n = gains + losses
    p_value = (sum(comb(n, k) for k in range(min(gains, losses) + 1)) / 2 ** n * 2
               if n else 1.0)
    print(f"\n  McNemar: {gains} gained, {losses} lost, net {gains - losses:+d} "
          f"of {len(tones)}, exact p={min(p_value, 1.0):.3f}")
    per_fold = [b - a for a, b in zip(control["fold_accuracies"],
                                      fusion["fold_accuracies"])]
    print("  per-fold delta: "
          + ", ".join(f"{d * 100:+.1f}" for d in per_fold)
          + f"   ({sum(d > 0 for d in per_fold)}/{len(per_fold)} folds improved)")

    print(coefficient_share(fusion["models"], wav_width, praat_width))

    print("\nVerification:")
    print(f"  speaker overlap        : 0 (asserted every fold, both models)")
    print(f"  samples used           : {len(tones)}/879, each tested exactly once")
    print(f"  identical fold membership in A and B: True (one fold list, both models)")
    print(f"  preprocessing fitted on held-out speakers: never "
          f"(scaler and imputer are pipeline steps)")

    summary = {
        name: {k: v for k, v in result.items()
               if k not in ("predicted", "models", "confusion")}
        | {"confusion_matrix": result["confusion"].tolist()}
        for name, result in (("control", control), ("fusion", fusion))
    }
    summary["dimensions"] = {
        "wav2vec2": wav_width, "praat": praat_width, "total": int(fused.shape[1]),
    }
    summary["mcnemar"] = {"gains": gains, "losses": losses, "p_value": min(p_value, 1.0)}
    path = DATA_DIR / "feature_fusion_summary.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nsummary: {path}")
    print("\nMatched feature-level fusion reported. Nothing tuned.")


if __name__ == "__main__":
    main()
