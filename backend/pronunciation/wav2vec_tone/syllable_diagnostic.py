"""How much of the tone accuracy is syllable identity rather than tone?

93.5% of test samples share a syllable_base with training data, so a model
could score well by recognising which syllable it is hearing and recalling
that syllable's usual tone. That would not transfer to a student pronouncing
a familiar word with the wrong tone -- which is the entire application.

Four parts: a lexical-only predictor that uses no audio at all, a measurement
of how deterministic the syllable-to-tone mapping is, a subset restricted to
syllables that genuinely occur with more than one tone, and a table putting
the numbers side by side.

Nothing is retrained on the subset; the existing out-of-fold predictions are
re-scored on it, so the models never saw it as a target.

    python -m pronunciation.wav2vec_tone.syllable_diagnostic
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone import feature_fusion
from pronunciation.wav2vec_tone.prepare_dataset import KEEP_TONES
from pronunciation.wav2vec_tone.train_baseline import (
    confusion,
    format_confusion,
    make_folds,
    per_class_scores,
)

DATA_DIR = Path(__file__).resolve().parent / "data"


def syllable_only_predict(bases, tones, train_index, test_index) -> np.ndarray:
    """Predict each syllable's most frequent training tone. No audio involved.

    Ties break toward the training-fold majority tone when it is among the
    tied options, otherwise the lowest tone number -- an arbitrary but fixed
    rule, so the baseline is reproducible rather than dependent on dict order.
    """
    counts: dict[str, Counter] = defaultdict(Counter)
    for base, tone in zip(bases[train_index], tones[train_index]):
        counts[str(base)][int(tone)] += 1
    global_majority = Counter(tones[train_index].tolist()).most_common(1)[0][0]

    lookup = {}
    for base, tally in counts.items():
        best = max(tally.values())
        tied = sorted(tone for tone, count in tally.items() if count == best)
        lookup[base] = global_majority if global_majority in tied else tied[0]

    # An unseen syllable falls back to the majority tone: the best a purely
    # lexical predictor can do without ever hearing the recording.
    return np.asarray(
        [lookup.get(str(base), global_majority) for base in bases[test_index]],
        dtype=int,
    )


def score_block(tones, predicted) -> dict:
    scores = per_class_scores(tones, predicted)
    return {
        "accuracy": float((predicted == tones).mean()),
        "macro_f1": float(np.mean([scores[t]["f1"] for t in KEEP_TONES])),
        "per_tone_f1": {f"T{t}": scores[t]["f1"] for t in KEEP_TONES},
        "per_tone": {f"T{t}": scores[t] for t in KEEP_TONES},
        "n": int(len(tones)),
    }


def part_a(bases, tones, speakers, folds) -> tuple[str, dict, np.ndarray]:
    predicted = np.zeros(len(tones), dtype=int)
    fold_accuracies = []
    for train_index, test_index in folds:
        guesses = syllable_only_predict(bases, tones, train_index, test_index)
        predicted[test_index] = guesses
        fold_accuracies.append(float((guesses == tones[test_index]).mean()))

    result = score_block(tones, predicted)
    result["fold_accuracies"] = fold_accuracies
    matrix = confusion(tones, predicted)

    lines = [
        "=" * 74,
        "PART A -- syllable-only baseline (no audio, no speaker, no duration)",
        "=" * 74,
        f"Accuracy: {result['accuracy'] * 100:.1f}%   (folds: "
        + ", ".join(f"{a * 100:.1f}" for a in fold_accuracies) + ")",
        f"Macro F1: {result['macro_f1']:.3f}",
        "",
        "Per-tone F1:",
    ]
    for tone in KEEP_TONES:
        entry = result["per_tone"][f"T{tone}"]
        lines.append(f"  T{tone}: {entry['f1']:.3f}   (precision {entry['precision']:.3f}, "
                     f"recall {entry['recall']:.3f}, n={entry['support']})")
    lines += ["", "Confusion matrix:", format_confusion(matrix)]
    result["confusion_matrix"] = matrix.tolist()
    return "\n".join(lines), result, predicted


def part_b(bases, tones) -> tuple[str, dict]:
    by_base: dict[str, Counter] = defaultdict(Counter)
    for base, tone in zip(bases, tones):
        by_base[str(base)][int(tone)] += 1

    tone_counts = Counter(len(tally) for tally in by_base.values())
    single_tone_bases = {b for b, t in by_base.items() if len(t) == 1}
    single_tone_samples = sum(
        sum(by_base[b].values()) for b in single_tone_bases
    )
    dominance = np.asarray([
        max(tally.values()) / sum(tally.values()) for tally in by_base.values()
    ])

    lines = [
        "",
        "=" * 74,
        "PART B -- how deterministic is syllable -> tone?",
        "=" * 74,
        f"Syllable bases in total: {len(by_base)}",
        "",
        "Bases appearing with:",
    ]
    for count in (1, 2, 3, 4):
        bases_at = tone_counts.get(count, 0)
        lines.append(f"  exactly {count} tone{'s' if count > 1 else ' '}: {bases_at:>4}"
                     f"  ({bases_at / len(by_base) * 100:5.1f}% of bases)")
    lines += [
        "",
        f"Samples belonging to single-tone bases: {single_tone_samples} "
        f"({single_tone_samples / len(tones) * 100:.1f}%)",
        "",
        "Dominant-tone proportion (max_tone_count / total for that base):",
        f"  mean   : {dominance.mean():.3f}",
        f"  median : {np.median(dominance):.3f}",
        f"  p75    : {np.percentile(dominance, 75):.3f}",
        f"  p90    : {np.percentile(dominance, 90):.3f}",
        f"  bases with proportion = 1.0 : {int((dominance >= 1.0).sum())}"
        f"  ({(dominance >= 1.0).mean() * 100:.1f}% of bases)",
    ]
    return "\n".join(lines), {
        "n_bases": len(by_base),
        "bases_by_tone_count": {str(k): tone_counts.get(k, 0) for k in (1, 2, 3, 4)},
        "single_tone_samples": single_tone_samples,
        "single_tone_sample_share": single_tone_samples / len(tones),
        "dominance_mean": float(dominance.mean()),
        "dominance_median": float(np.median(dominance)),
        "dominance_p75": float(np.percentile(dominance, 75)),
        "dominance_p90": float(np.percentile(dominance, 90)),
        "bases_fully_determined": int((dominance >= 1.0).sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temporal",
                        default=str(DATA_DIR / "embeddings_frozen_temporal3.npz"))
    parser.add_argument("--praat", default=str(DATA_DIR / "praat_feature_matrix.npz"))
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    wav = np.load(args.temporal, allow_pickle=True)
    praat = np.load(args.praat, allow_pickle=True)
    if not np.array_equal(wav["dataset_indices"], praat["dataset_indices"]):
        raise RuntimeError("Caches are not row-aligned.")

    tones = wav["tones"]
    speakers = wav["speakers"]
    bases = wav["syllable_bases"]
    indices = wav["dataset_indices"]
    folds, _ = make_folds(tones, speakers, args.folds, args.seed)

    text_a, result_a, predicted_a = part_a(bases, tones, speakers, folds)
    print(text_a)
    text_b, result_b = part_b(bases, tones)
    print(text_b)

    # Re-derive both models' out-of-fold predictions under the same folds. The
    # pipelines are deterministic, so this reproduces the published runs.
    wav_features, praat_features = wav["embeddings"], praat["embeddings"]
    wav_width, praat_width = wav_features.shape[1], praat_features.shape[1]
    fused_features = np.hstack([wav_features, praat_features])

    control = feature_fusion.evaluate(
        wav_features, tones, speakers, folds,
        lambda: feature_fusion.build_control(wav_width, args.seed), "temporal3")
    fusion = feature_fusion.evaluate(
        fused_features, tones, speakers, folds,
        lambda: feature_fusion.build_fusion(wav_width, praat_width, args.seed), "fusion")

    # Part C: syllables that genuinely occur with more than one tone.
    tone_sets: dict[str, set] = defaultdict(set)
    for base, tone in zip(bases, tones):
        tone_sets[str(base)].add(int(tone))
    multi = np.asarray([len(tone_sets[str(b)]) >= 2 for b in bases], dtype=bool)

    subset_tones = tones[multi]
    print("\n" + "=" * 74)
    print("PART C -- multi-tone syllable subset (syllable identity cannot decide)")
    print("=" * 74)
    print(f"Samples               : {int(multi.sum())} "
          f"({multi.mean() * 100:.1f}% of 879)")
    print(f"Unique syllable bases : {len({str(b) for b in bases[multi]})}")
    print("Tone distribution     : "
          + ", ".join(f"T{t}={int((subset_tones == t).sum())}" for t in KEEP_TONES))
    print(f"Unique speakers       : {len({str(s) for s in speakers[multi]})}")

    subset_scores = {}
    for label, result in (("temporal-3", control), ("feature fusion", fusion)):
        block = score_block(subset_tones, result["predicted"][multi])
        subset_scores[label] = block
        print(f"\n{label} on multi-tone subset:")
        print(f"  accuracy : {block['accuracy'] * 100:.1f}%")
        print(f"  macro F1 : {block['macro_f1']:.3f}")
        for tone in KEEP_TONES:
            print(f"  T{tone} F1    : {block['per_tone_f1'][f'T{tone}']:.3f}")

    syllable_subset = score_block(subset_tones, predicted_a[multi])
    majority_full = max(Counter(tones.tolist()).values()) / len(tones)
    majority_subset = max(Counter(subset_tones.tolist()).values()) / len(subset_tones)

    print("\n" + "=" * 74)
    print("PART D -- interpretation")
    print("=" * 74)
    print(f"  {'':<34}{'accuracy':>10}{'macro F1':>10}{'vs syllable-only':>19}")
    print(f"  {'FULL DATASET (n=879)':<34}")
    rows_full = (
        ("majority-class baseline", majority_full, None),
        ("syllable-only baseline", result_a["accuracy"], result_a["macro_f1"]),
        ("Wav2Vec2 temporal-3", control["accuracy"], control["macro_f1"]),
        ("feature fusion", fusion["accuracy"], fusion["macro_f1"]),
    )
    for label, accuracy, macro in rows_full:
        delta = f"{(accuracy - result_a['accuracy']) * 100:+.1f} pts" \
            if label != "syllable-only baseline" else "--"
        print(f"    {label:<32}{accuracy * 100:>9.1f}%"
              + (f"{macro:>10.3f}" if macro is not None else f"{'--':>10}")
              + f"{delta:>19}")

    print(f"  {'MULTI-TONE SUBSET (n=' + str(int(multi.sum())) + ')':<34}")
    rows_subset = (
        ("majority-class baseline", majority_subset, None),
        ("syllable-only baseline", syllable_subset["accuracy"],
         syllable_subset["macro_f1"]),
        ("Wav2Vec2 temporal-3", subset_scores["temporal-3"]["accuracy"],
         subset_scores["temporal-3"]["macro_f1"]),
        ("feature fusion", subset_scores["feature fusion"]["accuracy"],
         subset_scores["feature fusion"]["macro_f1"]),
    )
    for label, accuracy, macro in rows_subset:
        delta = f"{(accuracy - syllable_subset['accuracy']) * 100:+.1f} pts" \
            if label != "syllable-only baseline" else "--"
        print(f"    {label:<32}{accuracy * 100:>9.1f}%"
              + (f"{macro:>10.3f}" if macro is not None else f"{'--':>10}")
              + f"{delta:>19}")

    print("\n  Headroom above the syllable-only baseline:")
    print(f"    full dataset : temporal-3 "
          f"{(control['accuracy'] - result_a['accuracy']) * 100:+.1f} pts, "
          f"fusion {(fusion['accuracy'] - result_a['accuracy']) * 100:+.1f} pts")
    print(f"    multi-tone   : temporal-3 "
          f"{(subset_scores['temporal-3']['accuracy'] - syllable_subset['accuracy']) * 100:+.1f} pts, "
          f"fusion {(subset_scores['feature fusion']['accuracy'] - syllable_subset['accuracy']) * 100:+.1f} pts")

    out = DATA_DIR / "oof_predictions_feature_fusion.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["dataset_index", "speaker_id", "syllable_base", "true_tone",
                         "predicted_fusion", "predicted_temporal3",
                         "predicted_syllable_only", "multi_tone_base"])
        for position, index in enumerate(indices):
            writer.writerow([
                int(index), speakers[position], bases[position],
                int(tones[position]), int(fusion["predicted"][position]),
                int(control["predicted"][position]), int(predicted_a[position]),
                int(multi[position]),
            ])

    summary = {
        "part_a_syllable_only": {k: v for k, v in result_a.items() if k != "per_tone"},
        "part_b_determinism": result_b,
        "part_c_subset": {
            "n": int(multi.sum()),
            "n_bases": len({str(b) for b in bases[multi]}),
            "n_speakers": len({str(s) for s in speakers[multi]}),
            "tone_distribution": {f"T{t}": int((subset_tones == t).sum())
                                  for t in KEEP_TONES},
            "temporal3": {k: v for k, v in subset_scores["temporal-3"].items()
                          if k != "per_tone"},
            "fusion": {k: v for k, v in subset_scores["feature fusion"].items()
                       if k != "per_tone"},
            "syllable_only": {k: v for k, v in syllable_subset.items()
                              if k != "per_tone"},
        },
    }
    path = DATA_DIR / "syllable_diagnostic_summary.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\npredictions : {out}")
    print(f"summary     : {path}")
    print("\nDiagnostic only. Nothing retrained, nothing tuned.")


if __name__ == "__main__":
    main()
