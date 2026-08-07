"""First baseline: frozen wav2vec2 mean-pooled embedding -> 4-way tone.

A linear probe on frozen features, evaluated speaker-independently. The
question this answers is not "how good can tone classification get" but "how
much tone information does the frozen mean-pooled representation already
carry" -- so the classifier is deliberately simple and untuned. A stronger
model would blur that reading by contributing structure of its own.

Every speaker appears in exactly one test fold, and the overlap is asserted
rather than assumed: a classifier that heard a voice during training can
recognise the voice instead of the tone, which does not lower the reported
accuracy -- it invalidates it while still producing a good-looking number.

    python -m pronunciation.wav2vec_tone.train_baseline
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.cache_embeddings import DEFAULT_OUT as DEFAULT_CACHE
from pronunciation.wav2vec_tone.prepare_dataset import KEEP_TONES
from pronunciation.wav2vec_tone.train_classifier import (
    assert_no_speaker_overlap,
    build_classifier,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
MODELS_DIR = Path(__file__).resolve().parent / "models"
N_SPLITS = 5
SEED = 0


def make_folds(tones, speakers, n_splits: int, seed: int):
    """Speaker-disjoint folds, tone-stratified where the library allows it.

    StratifiedGroupKFold keeps the tone balance comparable across folds while
    still moving whole speakers together. GroupKFold is the fallback: it
    guarantees the disjointness, which is the part that cannot be compromised,
    and only loses the balancing.
    """
    try:
        from sklearn.model_selection import StratifiedGroupKFold

        splitter = StratifiedGroupKFold(
            n_splits=n_splits, shuffle=True, random_state=seed
        )
        return list(splitter.split(np.zeros(len(tones)), tones, speakers)), \
            "StratifiedGroupKFold"
    except ImportError:  # pragma: no cover - very old scikit-learn
        from sklearn.model_selection import GroupKFold

        splitter = GroupKFold(n_splits=n_splits)
        return list(splitter.split(np.zeros(len(tones)), tones, speakers)), \
            "GroupKFold"


def per_class_scores(true, predicted) -> dict:
    """Precision/recall/F1 per tone, computed explicitly.

    Zero-division is reported as 0.0 rather than raising: a fold where a tone
    is never predicted is a real, informative outcome for this baseline.
    """
    scores = {}
    for tone in KEEP_TONES:
        true_positive = int(((predicted == tone) & (true == tone)).sum())
        predicted_positive = int((predicted == tone).sum())
        actual_positive = int((true == tone).sum())
        precision = true_positive / predicted_positive if predicted_positive else 0.0
        recall = true_positive / actual_positive if actual_positive else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) else 0.0
        )
        scores[tone] = {
            "precision": precision, "recall": recall, "f1": f1,
            "support": actual_positive,
        }
    return scores


def confusion(true, predicted) -> np.ndarray:
    matrix = np.zeros((len(KEEP_TONES), len(KEEP_TONES)), dtype=int)
    for row, actual in enumerate(KEEP_TONES):
        for column, guess in enumerate(KEEP_TONES):
            matrix[row, column] = int(((true == actual) & (predicted == guess)).sum())
    return matrix


def format_confusion(matrix: np.ndarray, indent: str = "  ") -> str:
    lines = [
        indent + "true\\pred" + "".join(f"{f'T{t}':>7}" for t in KEEP_TONES)
        + f"{'recall':>9}"
    ]
    for row, tone in enumerate(KEEP_TONES):
        total = matrix[row].sum()
        recall = matrix[row, row] / total if total else 0.0
        lines.append(
            indent + f"T{tone:<8}" + "".join(f"{v:>7}" for v in matrix[row])
            + f"{recall:>9.3f}"
        )
    return "\n".join(lines)


def syllable_overlap_rate(bases, train_index, test_index) -> float:
    """Share of test samples whose syllable_base also appears in training.

    A speaker-disjoint split says nothing about words. If the same syllable
    sits on both sides, the probe can succeed by recognising that syllable's
    segmental identity rather than its tone -- which would not transfer to a
    student saying a word the model never saw.
    """
    seen = set(bases[train_index].tolist())
    test_bases = bases[test_index]
    if not len(test_bases):
        return 0.0
    return float(np.mean([base in seen for base in test_bases.tolist()]))


def run(cache_path: Path, n_splits: int, seed: int, save_models: bool,
        make_model=build_classifier, title: str = "frozen wav2vec2") -> dict:
    stored = np.load(cache_path, allow_pickle=True)
    embeddings = stored["embeddings"]
    tones = stored["tones"]
    speakers = stored["speakers"]
    bases = stored["syllable_bases"]
    pinyin = stored["pinyin"]
    durations = stored["durations"]
    # Carried through to the predictions file so runs can be joined on a
    # stable key rather than on row position.
    indices = stored["dataset_indices"]

    print("=" * 72)
    print(f"BASELINE: {title} -> logistic regression")
    print("=" * 72)
    print(f"\ncache      : {cache_path.name}")
    print(f"encoder    : {stored['model_name']}  (pooling: {stored['pooling']})")
    print(f"samples    : {len(tones)}   dim: {embeddings.shape[1]}   "
          f"speakers: {len(set(speakers.tolist()))}")
    print("tones      : "
          + ", ".join(f"T{t}={int((tones == t).sum())}" for t in KEEP_TONES))

    folds, splitter_name = make_folds(tones, speakers, n_splits, seed)
    print(f"splitter   : {splitter_name}, {n_splits} folds, seed {seed}")

    predicted_tone = np.zeros(len(tones), dtype=int)
    probabilities = np.zeros((len(tones), len(KEEP_TONES)), dtype=np.float64)
    covered = np.zeros(len(tones), dtype=bool)

    fold_reports, overlap_violations, models = [], 0, []

    for number, (train_index, test_index) in enumerate(folds, start=1):
        train_speakers = sorted({str(s) for s in speakers[train_index]})
        test_speakers = sorted({str(s) for s in speakers[test_index]})
        try:
            overlap = assert_no_speaker_overlap(
                speakers[train_index], speakers[test_index]
            )
        except AssertionError as error:
            overlap_violations += 1
            raise RuntimeError(f"fold {number}: {error}") from error

        model = make_model(seed)
        model.fit(embeddings[train_index], tones[train_index])
        models.append(model)

        guesses = model.predict(embeddings[test_index])
        predicted_tone[test_index] = guesses
        covered[test_index] = True
        # Map probability columns through classes_ rather than assuming the
        # order is 1,2,3,4; a mismatch would silently relabel every column.
        for column, tone in enumerate(KEEP_TONES):
            position = list(model.classes_).index(tone)
            probabilities[test_index, column] = model.predict_proba(
                embeddings[test_index]
            )[:, position]

        truth = tones[test_index]
        accuracy = float((guesses == truth).mean())
        scores = per_class_scores(truth, guesses)
        macro_f1 = float(np.mean([scores[t]["f1"] for t in KEEP_TONES]))
        overlap_rate = syllable_overlap_rate(bases, train_index, test_index)

        fold_reports.append({
            "fold": number,
            "n_train": len(train_index), "n_test": len(test_index),
            "train_speakers": len(train_speakers),
            "test_speakers": len(test_speakers),
            "speaker_overlap": overlap,
            "accuracy": accuracy, "macro_f1": macro_f1,
            "per_tone": scores,
            "confusion": confusion(truth, guesses).tolist(),
            "syllable_overlap_rate": overlap_rate,
            "held_out_speakers": test_speakers,
        })

        print(f"\n--- fold {number} " + "-" * 56)
        print(f"  train {len(train_index):>4} samples / {len(train_speakers):>2} speakers"
              f"     test {len(test_index):>4} samples / {len(test_speakers):>2} speakers")
        print(f"  speaker overlap: {overlap}  (asserted)")
        print(f"  accuracy {accuracy * 100:5.1f}%     macro F1 {macro_f1:.3f}")
        print(f"  {'tone':<6}{'prec':>8}{'recall':>8}{'F1':>8}{'n':>6}")
        for tone in KEEP_TONES:
            score = scores[tone]
            print(f"  T{tone:<5}{score['precision']:>8.3f}{score['recall']:>8.3f}"
                  f"{score['f1']:>8.3f}{score['support']:>6}")
        print(format_confusion(confusion(truth, guesses)))
        print(f"  syllable_base overlap with train: {overlap_rate * 100:.1f}% "
              f"of test samples")

    if not covered.all():
        raise RuntimeError(
            f"{int((~covered).sum())} samples never appeared in a test fold; "
            f"out-of-fold predictions would be incomplete."
        )

    return {
        "tones": tones, "speakers": speakers, "bases": bases, "pinyin": pinyin,
        "durations": durations, "dataset_indices": indices,
        "predicted": predicted_tone,
        "probabilities": probabilities, "folds": fold_reports,
        "splitter": splitter_name, "overlap_violations": overlap_violations,
        "models": models if save_models else [],
        "encoder": str(stored["model_name"]),
    }


def summarise(result: dict) -> tuple[str, dict]:
    tones, predicted = result["tones"], result["predicted"]
    folds = result["folds"]

    accuracies = np.array([f["accuracy"] for f in folds])
    macro_f1s = np.array([f["macro_f1"] for f in folds])
    overlap_rates = np.array([f["syllable_overlap_rate"] for f in folds])

    # Pooled over all out-of-fold predictions, not an average of fold scores:
    # folds differ in size, and the pooled figure is what the saved
    # predictions actually support.
    pooled_scores = per_class_scores(tones, predicted)
    pooled_matrix = confusion(tones, predicted)
    pooled_accuracy = float((predicted == tones).mean())

    counts = Counter(tones.tolist())
    majority_tone, majority_count = counts.most_common(1)[0]
    majority_accuracy = majority_count / len(tones)

    off_diagonal = [
        (int(pooled_matrix[r, c]), KEEP_TONES[r], KEEP_TONES[c])
        for r in range(len(KEEP_TONES))
        for c in range(len(KEEP_TONES))
        if r != c
    ]
    off_diagonal.sort(reverse=True)

    lines = [
        "",
        "=" * 72,
        "BASELINE SUMMARY",
        "=" * 72,
        f"5-fold CV accuracy: {accuracies.mean() * 100:.1f}% "
        f"+/- {accuracies.std(ddof=1) * 100:.1f}   "
        f"(folds: {', '.join(f'{a * 100:.1f}' for a in accuracies)})",
        f"5-fold CV macro F1: {macro_f1s.mean():.3f} "
        f"+/- {macro_f1s.std(ddof=1):.3f}   "
        f"(folds: {', '.join(f'{m:.3f}' for m in macro_f1s)})",
        "",
        "Per-tone F1 (pooled out-of-fold):",
    ]
    for tone in KEEP_TONES:
        score = pooled_scores[tone]
        lines.append(
            f"  T{tone}: {score['f1']:.3f}"
            f"   (precision {score['precision']:.3f}, "
            f"recall {score['recall']:.3f}, n={score['support']})"
        )

    lines += [
        "",
        f"Random four-class chance     : 25.0%",
        f"Majority baseline accuracy   : {majority_accuracy * 100:.1f}%  "
        f"(always predict T{majority_tone}, n={majority_count})",
        f"Pooled out-of-fold accuracy  : {pooled_accuracy * 100:.1f}%",
        f"  vs chance   : {(pooled_accuracy - 0.25) * 100:+.1f} pts",
        f"  vs majority : {(pooled_accuracy - majority_accuracy) * 100:+.1f} pts",
        "",
        "Aggregated confusion matrix (all out-of-fold predictions):",
        format_confusion(pooled_matrix),
        "",
        f"Speaker overlap violations: {result['overlap_violations']}",
        f"Syllable-base overlap rate: {overlap_rates.mean() * 100:.1f}% "
        f"(per fold: "
        + ", ".join(f"{r * 100:.1f}%" for r in overlap_rates) + ")",
        "",
        f"Most common confusion       : T{off_diagonal[0][1]} -> T{off_diagonal[0][2]}"
        f"  ({off_diagonal[0][0]} samples)",
        f"Second most common confusion: T{off_diagonal[1][1]} -> T{off_diagonal[1][2]}"
        f"  ({off_diagonal[1][0]} samples)",
        "=" * 72,
    ]

    summary = {
        "cv_accuracy_mean": float(accuracies.mean()),
        "cv_accuracy_sd": float(accuracies.std(ddof=1)),
        "cv_macro_f1_mean": float(macro_f1s.mean()),
        "cv_macro_f1_sd": float(macro_f1s.std(ddof=1)),
        "pooled_accuracy": pooled_accuracy,
        "per_tone_f1": {f"T{t}": pooled_scores[t]["f1"] for t in KEEP_TONES},
        "per_tone": {f"T{t}": pooled_scores[t] for t in KEEP_TONES},
        "confusion_matrix": pooled_matrix.tolist(),
        "confusion_axis": [f"T{t}" for t in KEEP_TONES],
        "chance_accuracy": 0.25,
        "majority_accuracy": majority_accuracy,
        "majority_tone": int(majority_tone),
        "speaker_overlap_violations": result["overlap_violations"],
        "syllable_overlap_rate_mean": float(overlap_rates.mean()),
        "syllable_overlap_rate_per_fold": [float(r) for r in overlap_rates],
        "top_confusions": [
            {"true": f"T{t}", "predicted": f"T{p}", "count": n}
            for n, t, p in off_diagonal[:5]
        ],
        "splitter": result["splitter"],
        "encoder": result["encoder"],
        "folds": result["folds"],
    }
    return "\n".join(lines), summary


def compare_with(summary: dict, previous_path: Path) -> str:
    """Report deltas against an earlier run, refusing to compare unlike folds.

    A pooling change is only attributable if everything else held still. If the
    folds differ, the two accuracies were measured on different test sets and
    subtracting them would produce a number that looks like an effect but is
    partly a resampling difference.
    """
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    lines = ["", "=" * 72, f"COMPARISON vs {previous_path.name}", "=" * 72]

    now_folds = [f["held_out_speakers"] for f in summary["folds"]]
    was_folds = [f["held_out_speakers"] for f in previous["folds"]]
    identical = now_folds == was_folds
    lines.append(
        f"identical folds / speaker grouping: {identical}"
        + ("" if identical else "   -- DELTAS ARE NOT ATTRIBUTABLE TO POOLING")
    )

    def delta(label, new, old, scale=1.0, unit=""):
        return (f"  {label:<14} {new * scale:>7.3f}{unit}  vs {old * scale:>7.3f}{unit}"
                f"   delta {(new - old) * scale:+7.3f}{unit}")

    lines += [
        "",
        delta("accuracy", summary["cv_accuracy_mean"],
              previous["cv_accuracy_mean"], 100, "%"),
        delta("macro F1", summary["cv_macro_f1_mean"], previous["cv_macro_f1_mean"]),
    ]
    for tone in KEEP_TONES:
        key = f"T{tone}"
        lines.append(delta(f"{key} F1", summary["per_tone_f1"][key],
                           previous["per_tone_f1"][key]))

    axis = [f"T{t}" for t in KEEP_TONES]
    now_matrix = np.asarray(summary["confusion_matrix"])
    was_matrix = np.asarray(previous["confusion_matrix"])
    lines += ["", "  confusion cells of interest:"]
    for true_tone, predicted_tone in ((2, 3), (3, 2)):
        row, column = axis.index(f"T{true_tone}"), axis.index(f"T{predicted_tone}")
        lines.append(
            f"    T{true_tone} -> T{predicted_tone}: {now_matrix[row, column]:>4}"
            f"  vs {was_matrix[row, column]:>4}"
            f"   delta {now_matrix[row, column] - was_matrix[row, column]:+d}"
        )
    lines.append("=" * 72)
    return "\n".join(lines)


def save_predictions(result: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "dataset_index",
            "speaker_id", "pinyin", "syllable_base", "true_tone", "predicted_tone",
            "probability_t1", "probability_t2", "probability_t3", "probability_t4",
            "duration_seconds",
        ])
        for index in range(len(result["tones"])):
            writer.writerow([
                int(result["dataset_indices"][index]),
                result["speakers"][index], result["pinyin"][index],
                result["bases"][index], int(result["tones"][index]),
                int(result["predicted"][index]),
                *[f"{p:.6f}" for p in result["probabilities"][index]],
                f"{result['durations'][index]:.3f}",
            ])
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--tag", default="baseline",
                        help="suffix for output files, so runs do not overwrite")
    parser.add_argument("--compare", help="summary JSON of a previous run")
    parser.add_argument("--folds", type=int, default=N_SPLITS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--no-save-models", action="store_true")
    args = parser.parse_args()

    result = run(Path(args.cache), args.folds, args.seed, not args.no_save_models)
    report, summary = summarise(result)
    print(report)
    if args.compare:
        print(compare_with(summary, Path(args.compare)))

    predictions = save_predictions(
        result, DATA_DIR / f"oof_predictions_{args.tag}.csv")
    summary_path = DATA_DIR / f"{args.tag}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nout-of-fold predictions : {predictions}")
    print(f"evaluation summary      : {summary_path}")

    if result["models"]:
        import joblib

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        model_path = MODELS_DIR / f"{args.tag}_fold_models.joblib"
        joblib.dump(
            {
                "models": result["models"],
                "tone_labels": list(KEEP_TONES),
                "folds": [f["held_out_speakers"] for f in result["folds"]],
                "encoder": result["encoder"],
                "pooling": "mean",
            },
            model_path,
        )
        print(f"fold models             : {model_path}")

    print("\nBaseline reported. Pooling unchanged; nothing integrated.")


if __name__ == "__main__":
    main()
