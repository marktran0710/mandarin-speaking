"""Calibrated late fusion: does Platt scaling let Praat influence the decision?

The uncalibrated 0.5/0.5 fusion recovered only 19 of 154 samples Praat alone
got right, because wav2vec2's posteriors are far more peaked (mean max
probability 0.832 vs 0.443). Averaging a confident distribution with a diffuse
one leaves the argmax almost unchanged, so equal weight on the probabilities
was not equal influence on the decision.

This puts both systems on a comparable probability scale first, then applies
the same fixed 0.5/0.5 weight. If the two feature sets genuinely combine, this
is the experiment that should show it.

Calibration is nested inside the outer folds. Each outer training set is split
again by speaker, the classifier is fitted on the inner training speakers and
the sigmoid fitted on the inner held-out speakers -- so the outer test
speakers are untouched by both the classifier and the calibrator. Calibrating
on data the model was fitted on would learn to correct overconfidence the
model does not show on that data, which produces a calibrator that looks good
and transfers badly.

    python -m pronunciation.wav2vec_tone.calibrated_fusion
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.praat_baseline import build_praat_classifier
from pronunciation.wav2vec_tone.prepare_dataset import KEEP_TONES
from pronunciation.wav2vec_tone.train_baseline import (
    confusion,
    format_confusion,
    make_folds,
    per_class_scores,
)
from pronunciation.wav2vec_tone.train_classifier import (
    assert_no_speaker_overlap,
    build_classifier,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
N_INNER_FOLDS = 3
CALIBRATION_METHOD = "sigmoid"   # Platt. Isotonic excluded by instruction.
ECE_BINS = 15


def inner_speaker_folds(tones, speakers, seed):
    """Speaker-disjoint folds *within* an outer training set, for calibration.

    Grouping by speaker here too. If the same voice trained the classifier and
    fitted the sigmoid, the calibrator would see unrealistically confident,
    unrealistically correct predictions and learn to leave them alone.
    """
    from sklearn.model_selection import StratifiedGroupKFold

    unique = len(set(map(str, speakers)))
    splits = min(N_INNER_FOLDS, max(2, unique - 1))
    splitter = StratifiedGroupKFold(n_splits=splits, shuffle=True, random_state=seed)
    folds = list(splitter.split(np.zeros(len(tones)), tones, speakers))
    for train_index, test_index in folds:
        assert_no_speaker_overlap(speakers[train_index], speakers[test_index])
    return folds


def calibrated_model(base_factory, features, tones, speakers, seed):
    """Fit a Platt-calibrated classifier using speaker-disjoint inner folds."""
    from sklearn.calibration import CalibratedClassifierCV

    folds = inner_speaker_folds(tones, speakers, seed)
    model = CalibratedClassifierCV(
        estimator=base_factory(seed), method=CALIBRATION_METHOD, cv=folds,
    )
    model.fit(features, tones)
    return model


def probability_matrix(model, features):
    """predict_proba, reordered into KEEP_TONES order via classes_."""
    raw = model.predict_proba(features)
    order = [list(model.classes_).index(tone) for tone in KEEP_TONES]
    return raw[:, order]


def one_hot(tones):
    labels = np.asarray(KEEP_TONES)
    return (tones[:, None] == labels[None, :]).astype(float)


def expected_calibration_error(probabilities, tones, bins=ECE_BINS):
    """Gap between confidence and accuracy, averaged over confidence bins.

    A well-calibrated system that says 0.7 is right about 70% of the time.
    """
    confidence = probabilities.max(axis=1)
    predicted = np.asarray(KEEP_TONES)[probabilities.argmax(axis=1)]
    correct = (predicted == tones).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    error = 0.0
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (confidence > low) & (confidence <= high)
        if mask.any():
            error += mask.mean() * abs(correct[mask].mean() - confidence[mask].mean())
    return float(error)


def score(probabilities, tones) -> dict:
    from sklearn.metrics import log_loss

    predicted = np.asarray(KEEP_TONES)[probabilities.argmax(axis=1)]
    scores = per_class_scores(tones, predicted)
    targets = one_hot(tones)
    return {
        "accuracy": float((predicted == tones).mean()),
        "macro_f1": float(np.mean([scores[t]["f1"] for t in KEEP_TONES])),
        "log_loss": float(log_loss(tones, probabilities, labels=list(KEEP_TONES))),
        # Multiclass Brier: squared error summed over classes, averaged over
        # samples. Unlike log loss it does not explode on a confident mistake.
        "brier": float(np.mean(np.sum((probabilities - targets) ** 2, axis=1))),
        "mean_max_probability": float(probabilities.max(axis=1).mean()),
        "median_max_probability": float(np.median(probabilities.max(axis=1))),
        "ece": expected_calibration_error(probabilities, tones),
        "per_tone_f1": {f"T{t}": scores[t]["f1"] for t in KEEP_TONES},
        "per_tone": {f"T{t}": scores[t] for t in KEEP_TONES},
        "predicted": predicted,
    }


def run(temporal_cache: Path, praat_cache: Path, n_splits: int, seed: int) -> dict:
    wav = np.load(temporal_cache, allow_pickle=True)
    praat = np.load(praat_cache, allow_pickle=True)

    if not np.array_equal(wav["dataset_indices"], praat["dataset_indices"]):
        raise RuntimeError("The two caches are not row-aligned.")
    if not np.array_equal(wav["tones"], praat["tones"]):
        raise RuntimeError("Tone labels disagree between the two caches.")

    tones = wav["tones"]
    speakers = wav["speakers"]
    indices = wav["dataset_indices"]
    systems = {
        "wav2vec2": (wav["embeddings"], build_classifier),
        "praat": (praat["embeddings"], build_praat_classifier),
    }

    folds, splitter_name = make_folds(tones, speakers, n_splits, seed)
    print(f"outer folds: {splitter_name}, {n_splits}, seed {seed}")
    print(f"calibration: {CALIBRATION_METHOD}, {N_INNER_FOLDS} speaker-disjoint "
          f"inner folds per outer fold")

    total = len(tones)
    raw = {name: np.zeros((total, len(KEEP_TONES))) for name in systems}
    calibrated = {name: np.zeros((total, len(KEEP_TONES))) for name in systems}

    for number, (train_index, test_index) in enumerate(folds, start=1):
        assert_no_speaker_overlap(speakers[train_index], speakers[test_index])
        outer_test_speakers = {str(s) for s in speakers[test_index]}

        for name, (features, factory) in systems.items():
            plain = factory(seed)
            plain.fit(features[train_index], tones[train_index])
            raw[name][test_index] = probability_matrix(plain, features[test_index])

            model = calibrated_model(
                factory, features[train_index], tones[train_index],
                speakers[train_index], seed,
            )
            # The calibrator's inner folds live entirely inside the outer
            # training set; assert it rather than trusting the construction.
            for inner_train, inner_test in inner_speaker_folds(
                tones[train_index], speakers[train_index], seed
            ):
                for part in (inner_train, inner_test):
                    leaked = {str(s) for s in speakers[train_index][part]} & \
                        outer_test_speakers
                    assert not leaked, f"calibration leak into outer test: {leaked}"
            calibrated[name][test_index] = probability_matrix(
                model, features[test_index]
            )

        print(f"  fold {number}: {len(train_index)} train / {len(test_index)} test "
              f"({len(outer_test_speakers)} held-out speakers)  ok")

    fused_raw = 0.5 * raw["wav2vec2"] + 0.5 * raw["praat"]
    fused_calibrated = 0.5 * calibrated["wav2vec2"] + 0.5 * calibrated["praat"]

    return {
        "tones": tones, "speakers": speakers, "dataset_indices": indices,
        "raw": raw, "calibrated": calibrated,
        "fused_raw": fused_raw, "fused_calibrated": fused_calibrated,
        "folds": folds,
    }


def metrics_table(rows: list[tuple[str, dict]]) -> str:
    header = (f"  {'system':<28}{'acc':>8}{'macroF1':>9}{'logloss':>9}"
              f"{'brier':>8}{'meanmax':>9}{'medmax':>8}{'ECE':>8}")
    lines = [header]
    for label, values in rows:
        lines.append(
            f"  {label:<28}{values['accuracy'] * 100:>7.1f}%{values['macro_f1']:>9.3f}"
            f"{values['log_loss']:>9.3f}{values['brier']:>8.3f}"
            f"{values['mean_max_probability']:>9.3f}"
            f"{values['median_max_probability']:>8.3f}{values['ece']:>8.3f}"
        )
    return "\n".join(lines)


def confidence_histogram(label: str, probabilities: np.ndarray) -> str:
    confidence = probabilities.max(axis=1)
    edges = [0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95, 1.01]
    counts = []
    previous = 0.0
    for edge in edges:
        counts.append(int(((confidence >= previous) & (confidence < edge)).sum()))
        previous = edge
    total = len(confidence)
    cells = "".join(f"{c / total * 100:>7.1f}" for c in counts)
    return f"  {label:<28}{cells}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temporal",
                        default=str(DATA_DIR / "embeddings_frozen_temporal3.npz"))
    parser.add_argument("--praat", default=str(DATA_DIR / "praat_feature_matrix.npz"))
    parser.add_argument("--previous-fusion",
                        default=str(DATA_DIR / "oof_predictions_fusion.csv"))
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    result = run(Path(args.temporal), Path(args.praat), args.folds, args.seed)
    tones = result["tones"]

    scored = {
        "wav2vec2 uncalibrated": score(result["raw"]["wav2vec2"], tones),
        "wav2vec2 calibrated": score(result["calibrated"]["wav2vec2"], tones),
        "praat uncalibrated": score(result["raw"]["praat"], tones),
        "praat calibrated": score(result["calibrated"]["praat"], tones),
        "fusion uncalibrated": score(result["fused_raw"], tones),
        "fusion CALIBRATED": score(result["fused_calibrated"], tones),
    }

    print("\n" + "=" * 92)
    print("CALIBRATION QUALITY  (all out-of-fold, outer test speakers only)")
    print("=" * 92)
    print(metrics_table(list(scored.items())))

    print("\nConfidence distribution -- share of samples by max probability (%)")
    print(f"  {'system':<28}" + "".join(
        f"{b:>7}" for b in ("<.35", ".35-45", ".45-55", ".55-65", ".65-75",
                            ".75-85", ".85-95", ">.95", "")[:8]))
    for label in ("wav2vec2 uncalibrated", "wav2vec2 calibrated",
                  "praat uncalibrated", "praat calibrated"):
        matrix = (result["raw"] if "uncalibrated" in label else result["calibrated"])
        print(confidence_histogram(label, matrix[label.split()[0]]))

    gap_before = abs(scored["wav2vec2 uncalibrated"]["mean_max_probability"]
                     - scored["praat uncalibrated"]["mean_max_probability"])
    gap_after = abs(scored["wav2vec2 calibrated"]["mean_max_probability"]
                    - scored["praat calibrated"]["mean_max_probability"])
    print(f"\n  mean-max-probability gap between the two systems: "
          f"{gap_before:.3f} before -> {gap_after:.3f} after calibration")

    final = scored["fusion CALIBRATED"]
    predicted = final["predicted"]
    matrix = confusion(tones, predicted)
    axis = [f"T{t}" for t in KEEP_TONES]

    print("\n" + "=" * 72)
    print("CALIBRATED 0.5/0.5 FUSION")
    print("=" * 72)
    print(f"Accuracy: {final['accuracy'] * 100:.1f}%")
    print(f"Macro F1: {final['macro_f1']:.3f}")
    print("\nPer-tone F1:")
    for tone in KEEP_TONES:
        entry = final["per_tone"][f"T{tone}"]
        print(f"  T{tone}: {entry['f1']:.3f}   (precision {entry['precision']:.3f}, "
              f"recall {entry['recall']:.3f}, n={entry['support']})")
    print("\nConfusion matrix:")
    print(format_confusion(matrix))
    print()
    for true_tone, predicted_tone in ((2, 3), (3, 2), (4, 1), (4, 3)):
        value = matrix[axis.index(f"T{true_tone}"), axis.index(f"T{predicted_tone}")]
        print(f"  T{true_tone} -> T{predicted_tone}: {value}")

    references = (("wav2vec2 temporal-3", 0.578, 0.533),
                  ("uncalibrated 0.5/0.5 fusion", 0.585, 0.538))
    print("\nComparison:")
    for name, accuracy, macro in references:
        print(f"  vs {name:<30} accuracy {(final['accuracy'] - accuracy) * 100:+5.1f} pts"
              f"   macro F1 {final['macro_f1'] - macro:+.3f}")

    # Recovery against the original uncalibrated disagreement sets.
    previous = {int(r["dataset_index"]): r
                for r in csv.DictReader(Path(args.previous_fusion).open(encoding="utf-8"))}
    order = [previous[int(i)] for i in result["dataset_indices"]]
    was_wav = np.asarray([int(r["predicted_tone_wav2vec2"]) for r in order])
    was_praat = np.asarray([int(r["predicted_tone_praat"]) for r in order])
    correct_wav, correct_praat = was_wav == tones, was_praat == tones
    praat_only = correct_praat & ~correct_wav
    wav_only = correct_wav & ~correct_praat
    correct_now = predicted == tones

    print(f"\nAgainst the original disagreement sets:")
    print(f"  Praat-only-correct   : {int(praat_only.sum())}  -> calibrated fusion "
          f"recovers {int((praat_only & correct_now).sum())} "
          f"({(praat_only & correct_now).sum() / max(praat_only.sum(), 1) * 100:.1f}%)"
          f"   [uncalibrated recovered 19]")
    print(f"  wav2vec2-only-correct: {int(wav_only.sum())}  -> calibrated fusion "
          f"loses {int((wav_only & ~correct_now).sum())} "
          f"({(wav_only & ~correct_now).sum() / max(wav_only.sum(), 1) * 100:.1f}%)"
          f"   [uncalibrated lost 14]")

    out = DATA_DIR / "oof_predictions_calibrated_fusion.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["dataset_index", "speaker_id", "true_tone", "predicted_tone",
                         *[f"probability_t{t}" for t in KEEP_TONES]])
        for position, index in enumerate(result["dataset_indices"]):
            writer.writerow([
                int(index), result["speakers"][position], int(tones[position]),
                int(predicted[position]),
                *[f"{p:.6f}" for p in result["fused_calibrated"][position]],
            ])

    summary_path = DATA_DIR / "calibrated_fusion_summary.json"
    summary_path.write_text(json.dumps({
        name: {k: v for k, v in values.items() if k != "predicted"}
        for name, values in scored.items()
    } | {"confusion_matrix": matrix.tolist(), "confusion_axis": axis,
         "calibration_method": CALIBRATION_METHOD,
         "inner_folds": N_INNER_FOLDS}, indent=2), encoding="utf-8")

    print(f"\nfused predictions : {out}")
    print(f"summary           : {summary_path}")
    print("\nCalibrated 0.5/0.5 fusion reported. No weights tuned.")


if __name__ == "__main__":
    main()
