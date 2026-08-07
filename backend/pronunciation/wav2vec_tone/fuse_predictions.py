"""Fixed equal-weight late fusion of two out-of-fold probability sets.

    P_fusion(tone) = 0.5 * P_wav2vec2(tone) + 0.5 * P_praat(tone)

The weight is fixed at 0.5/0.5 before looking at any result. That is the point
of the experiment: an equal weight cannot have been chosen to flatter the
outcome, so whatever it produces is an honest estimate of what the two systems
carry jointly. A weight fitted on these same out-of-fold predictions would be
fitted on the test labels, and its score would no longer be an estimate of
anything.

Both inputs are already out-of-fold, produced under identical folds, so
averaging them introduces no new leakage.

    python -m pronunciation.wav2vec_tone.fuse_predictions
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.prepare_dataset import KEEP_TONES
from pronunciation.wav2vec_tone.train_baseline import (
    confusion,
    format_confusion,
    per_class_scores,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
PROBABILITY_COLUMNS = tuple(f"probability_t{tone}" for tone in KEEP_TONES)
WEIGHT_A = 0.5
WEIGHT_B = 0.5


def load_predictions(path: Path) -> dict[int, dict]:
    """Index a predictions file by dataset_index, refusing duplicates.

    Keyed rather than positional: two files that happen to be in different
    orders would still join correctly, and a file that is missing a row fails
    loudly instead of silently shifting every subsequent pairing.
    """
    rows = {}
    for row in csv.DictReader(path.open(encoding="utf-8")):
        key = int(row["dataset_index"])
        if key in rows:
            raise RuntimeError(f"{path.name}: dataset_index {key} appears twice.")
        rows[key] = row
    return rows


def join(first: dict[int, dict], second: dict[int, dict], expected: int) -> list[tuple]:
    """Pair rows by dataset_index, asserting the two files describe the same data.

    Every field checked here would, if mismatched, produce a fused number that
    looks plausible while combining probabilities from two different
    recordings.
    """
    missing_in_second = sorted(set(first) - set(second))
    missing_in_first = sorted(set(second) - set(first))
    if missing_in_second or missing_in_first:
        raise RuntimeError(
            f"dataset_index sets differ: {len(missing_in_second)} only in the "
            f"first file, {len(missing_in_first)} only in the second."
        )
    if len(first) != expected:
        raise RuntimeError(f"expected {expected} samples, joined {len(first)}.")

    paired = []
    for key in sorted(first):
        left, right = first[key], second[key]
        if left["speaker_id"] != right["speaker_id"]:
            raise RuntimeError(
                f"dataset_index {key}: speaker_id differs "
                f"({left['speaker_id']} vs {right['speaker_id']})."
            )
        if int(left["true_tone"]) != int(right["true_tone"]):
            raise RuntimeError(
                f"dataset_index {key}: true tone differs "
                f"({left['true_tone']} vs {right['true_tone']})."
            )
        paired.append((key, left, right))
    return paired


def fuse(paired: list[tuple], weight_a: float, weight_b: float) -> dict:
    labels = np.asarray(KEEP_TONES)
    truth, predicted_a, predicted_b = [], [], []
    probabilities_a, probabilities_b = [], []

    for _, left, right in paired:
        truth.append(int(left["true_tone"]))
        predicted_a.append(int(left["predicted_tone"]))
        predicted_b.append(int(right["predicted_tone"]))
        probabilities_a.append([float(left[column]) for column in PROBABILITY_COLUMNS])
        probabilities_b.append([float(right[column]) for column in PROBABILITY_COLUMNS])

    probabilities_a = np.asarray(probabilities_a)
    probabilities_b = np.asarray(probabilities_b)
    # Both come from predict_proba and should already sum to 1; checked rather
    # than trusted, because an unnormalised set would silently weight one
    # system more heavily than the other.
    for name, matrix in (("wav2vec2", probabilities_a), ("praat", probabilities_b)):
        sums = matrix.sum(axis=1)
        if not np.allclose(sums, 1.0, atol=1e-3):
            raise RuntimeError(
                f"{name} probabilities do not sum to 1 "
                f"(min {sums.min():.4f}, max {sums.max():.4f}); the fixed "
                f"weight would not mean what it says."
            )

    fused = weight_a * probabilities_a + weight_b * probabilities_b
    return {
        "keys": [key for key, _, _ in paired],
        "truth": np.asarray(truth),
        "predicted_a": np.asarray(predicted_a),
        "predicted_b": np.asarray(predicted_b),
        "predicted": labels[np.argmax(fused, axis=1)],
        "probabilities": fused,
        "rows": [left for _, left, _ in paired],
    }


def complementarity(result: dict) -> str:
    truth = result["truth"]
    correct_a = result["predicted_a"] == truth
    correct_b = result["predicted_b"] == truth
    correct_f = result["predicted"] == truth
    total = len(truth)

    both = correct_a & correct_b
    only_a = correct_a & ~correct_b
    only_b = correct_b & ~correct_a
    neither = ~correct_a & ~correct_b

    def line(label, mask):
        return (f"  {label:<34}{int(mask.sum()):>6}"
                f"{mask.mean() * 100:>8.1f}%"
                f"   fusion right: {int((mask & correct_f).sum()):>4}"
                f"  ({(correct_f[mask].mean() * 100 if mask.any() else 0.0):5.1f}%)")

    return "\n".join([
        "",
        "Complementarity (original systems vs fusion):",
        line("both originally correct", both),
        line("wav2vec2-only correct", only_a),
        line("Praat-only correct", only_b),
        line("neither correct", neither),
        "",
        f"  recovered from Praat-only-correct : {int((only_b & correct_f).sum())}"
        f" of {int(only_b.sum())}",
        f"  lost from wav2vec2-only-correct   : {int((only_a & ~correct_f).sum())}"
        f" of {int(only_a.sum())}",
        f"  net from the disagreement set     : "
        f"{int((only_b & correct_f).sum()) - int((only_a & ~correct_f).sum()):+d}"
        f"  ({(int((only_b & correct_f).sum()) - int((only_a & ~correct_f).sum())) / total * 100:+.1f} pts)",
        f"  lost from both-correct            : {int((both & ~correct_f).sum())}"
        f" of {int(both.sum())}",
        f"  gained from neither-correct       : {int((neither & correct_f).sum())}"
        f" of {int(neither.sum())}",
    ])


def report(result: dict, references: dict) -> tuple[str, dict]:
    truth, predicted = result["truth"], result["predicted"]
    scores = per_class_scores(truth, predicted)
    matrix = confusion(truth, predicted)
    accuracy = float((predicted == truth).mean())
    macro_f1 = float(np.mean([scores[tone]["f1"] for tone in KEEP_TONES]))
    axis = [f"T{tone}" for tone in KEEP_TONES]

    def cell(true_tone, predicted_tone):
        return int(matrix[axis.index(f"T{true_tone}"), axis.index(f"T{predicted_tone}")])

    lines = [
        "=" * 72,
        f"FIXED LATE FUSION  ({WEIGHT_A} x wav2vec2-temporal3 + {WEIGHT_B} x Praat)",
        "=" * 72,
        f"Fusion accuracy: {accuracy * 100:.1f}%",
        f"Fusion macro F1: {macro_f1:.3f}",
        "",
        "Per-tone precision / recall / F1:",
        f"  {'tone':<6}{'precision':>11}{'recall':>9}{'F1':>8}{'n':>6}",
    ]
    for tone in KEEP_TONES:
        score = scores[tone]
        lines.append(f"  T{tone:<5}{score['precision']:>11.3f}{score['recall']:>9.3f}"
                     f"{score['f1']:>8.3f}{score['support']:>6}")

    lines += ["", "Aggregated confusion matrix:", format_confusion(matrix), ""]
    for true_tone, predicted_tone in ((2, 3), (3, 2), (4, 1), (4, 3)):
        lines.append(f"  T{true_tone} -> T{predicted_tone} errors: "
                     f"{cell(true_tone, predicted_tone)}")

    for name, reference in references.items():
        lines += ["", f"Delta vs {name}:",
                  f"  accuracy   {accuracy * 100:>7.1f}%  vs {reference['accuracy'] * 100:>6.1f}%"
                  f"   {(accuracy - reference['accuracy']) * 100:+6.1f} pts",
                  f"  macro F1   {macro_f1:>7.3f}   vs {reference['macro_f1']:>6.3f}"
                  f"   {macro_f1 - reference['macro_f1']:+6.3f}"]
        for tone in KEEP_TONES:
            previous = reference["per_tone_f1"][f"T{tone}"]
            lines.append(
                f"  T{tone} F1      {scores[tone]['f1']:>7.3f}   vs {previous:>6.3f}"
                f"   {scores[tone]['f1'] - previous:+6.3f}"
            )

    summary = {
        "weights": {"wav2vec2_temporal3": WEIGHT_A, "praat_only": WEIGHT_B},
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "per_tone": {f"T{t}": scores[t] for t in KEEP_TONES},
        "per_tone_f1": {f"T{t}": scores[t]["f1"] for t in KEEP_TONES},
        "confusion_matrix": matrix.tolist(),
        "confusion_axis": axis,
        "n": int(len(truth)),
    }
    return "\n".join(lines), summary


def save(result: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "dataset_index", "speaker_id", "pinyin", "syllable_base",
            "true_tone", "predicted_tone_fusion",
            "predicted_tone_wav2vec2", "predicted_tone_praat",
            *[f"probability_t{t}" for t in KEEP_TONES],
            "duration_seconds",
        ])
        for position, key in enumerate(result["keys"]):
            row = result["rows"][position]
            writer.writerow([
                key, row["speaker_id"], row["pinyin"], row["syllable_base"],
                int(result["truth"][position]),
                int(result["predicted"][position]),
                int(result["predicted_a"][position]),
                int(result["predicted_b"][position]),
                *[f"{p:.6f}" for p in result["probabilities"][position]],
                row["duration_seconds"],
            ])
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", default=str(DATA_DIR / "oof_predictions_temporal3.csv"))
    parser.add_argument("--b", default=str(DATA_DIR / "oof_predictions_praat_only.csv"))
    parser.add_argument("--summary-a", default=str(DATA_DIR / "temporal3_summary.json"))
    parser.add_argument("--summary-b", default=str(DATA_DIR / "praat_only_summary.json"))
    parser.add_argument("--expected", type=int, default=879)
    parser.add_argument("--out", default=str(DATA_DIR / "oof_predictions_fusion.csv"))
    args = parser.parse_args()

    first = load_predictions(Path(args.a))
    second = load_predictions(Path(args.b))
    paired = join(first, second, args.expected)
    print(f"joined {len(paired)} samples by dataset_index "
          f"(speaker_id and true tone verified on every row)")

    result = fuse(paired, WEIGHT_A, WEIGHT_B)

    references = {}
    for name, path in (("wav2vec2 temporal-3", args.summary_a),
                       ("Praat-only", args.summary_b)):
        stored = json.loads(Path(path).read_text(encoding="utf-8"))
        references[name] = {
            "accuracy": stored["pooled_accuracy"],
            "macro_f1": float(np.mean(list(stored["per_tone_f1"].values()))),
            "per_tone_f1": stored["per_tone_f1"],
        }

    text, summary = report(result, references)
    print(text)
    print(complementarity(result))

    path = save(result, Path(args.out))
    summary_path = DATA_DIR / "fusion_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nfused predictions : {path}")
    print(f"summary           : {summary_path}")
    print("\nFixed 0.5/0.5 fusion reported. No weights tuned, no models retrained.")


if __name__ == "__main__":
    main()
