"""Praat-only tone baseline: 10 speaker-robust contour features -> tone.

The counterpart to the wav2vec2 probes, on the same 879 samples and the same
folds, so the two are directly comparable.

Everything here is relative. Speaker mean F0 in this corpus spans 133-283 Hz,
13.1 semitones -- larger than any tone contour in the data -- so a raw F0 level
would let the classifier separate voices instead of tones, and that would
collapse the moment a new speaker appeared. Each syllable is therefore
expressed in semitones against its own median F0:

    relative_f0 = 12 * log2(F0 / median_F0_of_this_syllable)

That removes the speaker's register and the utterance's absolute height in one
step, leaving the shape of the contour, which is what tone actually is.

Raw mean F0 and speaker_id are excluded as predictors by construction.

    python -m pronunciation.wav2vec_tone.praat_baseline
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone import train_baseline
from pronunciation.wav2vec_tone.praat_features import DEFAULT_OUT as PRAAT_CSV
from pronunciation.wav2vec_tone.praat_features import semitones
from pronunciation.wav2vec_tone.prepare_dataset import KEEP_TONES

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_MATRIX = DATA_DIR / "praat_feature_matrix.npz"

FEATURE_ORDER = (
    "rel_f0_start", "rel_f0_25", "rel_f0_50", "rel_f0_75", "rel_f0_end",
    "f0_range_st", "slope_start_to_mid", "slope_mid_to_end",
    "duration_seconds", "voiced_proportion",
)


def read_float(row: dict, name: str) -> float:
    """Empty cell -> NaN. The CSV writes missing measurements as blank, never 0."""
    value = row.get(name, "")
    if value is None or str(value).strip() == "":
        return float("nan")
    try:
        return float(value)
    except ValueError:
        return float("nan")


def build_features(csv_path: Path) -> dict:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    matrix = np.full((len(rows), len(FEATURE_ORDER)), np.nan, dtype=np.float64)

    for index, row in enumerate(rows):
        reference = read_float(row, "median_f0_hz")
        values = {
            "rel_f0_start": semitones(read_float(row, "f0_start"), reference),
            "rel_f0_25": semitones(read_float(row, "f0_25"), reference),
            "rel_f0_50": semitones(read_float(row, "f0_50"), reference),
            "rel_f0_75": semitones(read_float(row, "f0_75"), reference),
            "rel_f0_end": semitones(read_float(row, "f0_end"), reference),
            # Range as a log ratio too, so a 40 Hz swing counts the same for a
            # 130 Hz voice as for a 280 Hz one.
            "f0_range_st": semitones(
                read_float(row, "max_f0_hz"), read_float(row, "min_f0_hz")
            ),
            # Already semitones per second from the extractor.
            "slope_start_to_mid": read_float(row, "slope_start_to_mid"),
            "slope_mid_to_end": read_float(row, "slope_mid_to_end"),
            "duration_seconds": read_float(row, "duration_seconds"),
            "voiced_proportion": read_float(row, "voiced_proportion"),
        }
        for column, name in enumerate(FEATURE_ORDER):
            matrix[index, column] = values[name]

    return {
        "embeddings": matrix,
        "tones": np.asarray([int(r["tone"]) for r in rows], dtype=int),
        "speakers": np.asarray([r["speaker_id"] for r in rows], dtype=object),
        "syllable_bases": np.asarray([r["syllable_base"] for r in rows], dtype=object),
        "pinyin": np.asarray([r["pinyin"] for r in rows], dtype=object),
        "durations": np.asarray(
            [read_float(r, "duration_seconds") for r in rows], dtype=np.float64
        ),
        "dataset_indices": np.asarray([int(r["dataset_index"]) for r in rows], dtype=int),
        "flags": np.asarray([r.get("flags", "") for r in rows], dtype=object),
        "model_name": np.asarray("praat/parselmouth"),
        "pooling": np.asarray("relative-semitone-contour"),
        "feature_names": np.asarray(FEATURE_ORDER, dtype=object),
    }


def build_praat_classifier(seed: int = 0):
    """Impute -> standardise -> logistic regression, all fitted inside a fold.

    The imputer is part of the pipeline rather than applied beforehand, which
    is what keeps its median fitted on training data only. Imputing across the
    whole dataset first would leak held-out information into training -- a
    small leak here, with one missing sample, but the kind that is invisible
    once it is larger.
    """
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(
        # Median, not mean: several features are skewed by tracking outliers
        # that are deliberately still in the data.
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed),
    )


def assert_same_order(matrix: dict, reference_npz: Path) -> None:
    """Fail unless the rows line up with the wav2vec2 caches.

    The comparison is only meaningful if both systems saw the same samples in
    the same order -- the folds are built from position, so a different
    ordering would silently produce different folds and an unattributable
    delta.
    """
    stored = np.load(reference_npz, allow_pickle=True)
    if not np.array_equal(matrix["dataset_indices"], stored["dataset_indices"]):
        raise RuntimeError(
            "Praat rows are not in the same order as the wav2vec2 cache; the "
            "folds would differ and the comparison would be invalid."
        )
    if not np.array_equal(matrix["tones"], stored["tones"]):
        raise RuntimeError("Tone labels disagree between Praat and wav2vec2 caches.")


def flag_breakdown(result: dict, flags: np.ndarray) -> str:
    """Accuracy on flagged vs unflagged samples. Error analysis only.

    Reported to show whether the pitch-tracking flags mark samples the model
    actually gets wrong. Nothing is removed on the strength of it -- flagged
    samples were kept deliberately, and a difference here would be a reason to
    investigate the tracker, not to delete data.
    """
    flagged = np.asarray([bool(f) for f in flags], dtype=bool)
    correct = result["predicted"] == result["tones"]
    lines = ["", "Error analysis: flagged vs unflagged (nothing removed)",
             f"  {'group':<22}{'n':>6}{'accuracy':>11}{'macro F1':>11}"]
    for label, mask in (("unflagged", ~flagged), ("flagged", flagged),
                        ("all", np.ones_like(flagged))):
        if not mask.any():
            continue
        scores = train_baseline.per_class_scores(
            result["tones"][mask], result["predicted"][mask]
        )
        macro = float(np.mean([scores[t]["f1"] for t in KEEP_TONES]))
        lines.append(f"  {label:<22}{int(mask.sum()):>6}"
                     f"{correct[mask].mean() * 100:>10.1f}%{macro:>11.3f}")

    from collections import Counter

    counts = Counter(
        flag for value in flags for flag in str(value).split("|") if flag
    )
    for flag, count in counts.most_common():
        mask = np.asarray([flag in str(v).split("|") for v in flags], dtype=bool)
        lines.append(f"    {flag:<20}{count:>6}{correct[mask].mean() * 100:>10.1f}%")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--praat-csv", default=str(PRAAT_CSV))
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--tag", default="praat_only")
    parser.add_argument("--compare", default=str(DATA_DIR / "temporal3_summary.json"))
    parser.add_argument("--reference-cache",
                        default=str(DATA_DIR / "embeddings_frozen_temporal3.npz"))
    parser.add_argument("--folds", type=int, default=train_baseline.N_SPLITS)
    parser.add_argument("--seed", type=int, default=train_baseline.SEED)
    args = parser.parse_args()

    matrix = build_features(Path(args.praat_csv))
    assert_same_order(matrix, Path(args.reference_cache))

    missing = np.isnan(matrix["embeddings"])
    print(f"features   : {len(FEATURE_ORDER)} -> {', '.join(FEATURE_ORDER)}")
    print(f"rows       : {len(matrix['tones'])}")
    print(f"missing    : {int(missing.any(axis=1).sum())} rows have at least one NaN "
          f"({int(missing.sum())} cells); imputed inside each fold only")
    print("excluded as predictors: speaker_id, raw mean F0, anything tone-derived")

    path = Path(args.matrix)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **matrix)

    result = train_baseline.run(
        path, args.folds, args.seed, save_models=True,
        make_model=build_praat_classifier, title="Praat relative-contour features",
    )
    report, summary = train_baseline.summarise(result)
    print(report)
    print(flag_breakdown(result, matrix["flags"]))
    print(train_baseline.compare_with(summary, Path(args.compare)))

    summary["feature_names"] = list(FEATURE_ORDER)
    predictions = train_baseline.save_predictions(
        result, DATA_DIR / f"oof_predictions_{args.tag}.csv"
    )
    summary_path = DATA_DIR / f"{args.tag}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nfeature matrix          : {path}")
    print(f"out-of-fold predictions : {predictions}")
    print(f"evaluation summary      : {summary_path}")
    print("\nPraat-only baseline reported. Not combined with wav2vec2; nothing "
          "removed; nothing tuned.")


if __name__ == "__main__":
    main()
