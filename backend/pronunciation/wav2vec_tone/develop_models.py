"""Phase C: Train/Dev development of the three acoustic systems.

MODEL_A wav2vec2 · MODEL_B Praat · MODEL_C concatenation, all behind the same
L2 logistic regression, so the comparison is between representations rather
than between classifiers.

Test is sealed. Features are extracted for train and dev only -- not merely
"not evaluated" but not computed, so no Test prediction can exist by accident.

The framing that shapes every metric here: this is a component-selection
experiment inside a deployment question, not a leaderboard. Incorrect
prevalence is 17%, so Accuracy is nearly uninformative and is reported last.
False rejection and false acceptance are reported for every configuration
because they, not Accuracy, are what a learner would experience.

    python -m pronunciation.wav2vec_tone.develop_models
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DATA_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
RESULTS_CSV = DATA_DIR / "ompal_model_development_results.csv"
PROTOCOL_LOCK = DATA_DIR / "ompal_model_protocol_FROZEN.json"

PROTOCOL_VERSION = "ompal_model_protocol_v1"
SPLIT_ID = "ompal_speaker_split_v1"
SPLIT_SHA = "853aa9d0a2c3a449900f8797f8aabd780b7505d0cdbacce250b131058a532468"

# Pre-specified grid. Not to be widened after seeing results.
POOLINGS = ("mean", "temporal3")
CLASS_WEIGHTS = (None, "balanced")
C_VALUES = (0.01, 0.1, 1.0, 10.0)

# Expected tone: option B, explicit encoding. Option A (one model per tone)
# would cut 241 training Incorrect tokens into four groups of ~60, which
# cannot support the minority-class metrics this project reports. The
# deployment input always includes the known target, so encoding it is also
# the faithful representation.
EXPECTED_TONE_POLICY = "B: acoustic features + one-hot expected-tone encoding"

# Frozen Praat pronunciation feature set, as already defined in
# praat_baseline.py. Every value is relative: per-syllable semitone
# normalisation against the token's own median F0 removes speaker register.
PRAAT_FEATURES = (
    "rel_f0_start", "rel_f0_25", "rel_f0_50", "rel_f0_75", "rel_f0_end",
    "f0_range_st", "slope_start_to_mid", "slope_mid_to_end",
    "duration_seconds", "voiced_proportion",
)
POSITIVE = 0          # "Incorrect" is the positive class throughout
SAMPLE_RATE = 16000


def semitones(high, low):
    if not (np.isfinite(high) and np.isfinite(low)) or high <= 0 or low <= 0:
        return float("nan")
    return 12.0 * np.log2(high / low)


def load_rows():
    rows = [r for r in csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8"))
            if r["split"] in ("train", "dev")]
    if any(r["split"] == "test" for r in rows):
        sys.exit("TEST LOCK VIOLATION: test rows entered the development set")
    return rows


def praat_matrix(rows):
    """The frozen relative-contour features, recomputed from stored segments."""
    from pronunciation.wav2vec_tone.praat_features import extract_one
    import soundfile as sf

    matrix = np.full((len(rows), len(PRAAT_FEATURES)), np.nan)
    for index, row in enumerate(rows):
        audio, _ = sf.read(str(DATA_DIR / row["extracted_token_path"]), dtype="float32")
        features = extract_one(np.asarray(audio, dtype=np.float32))
        reference = features.get("median_f0_hz", float("nan"))
        values = {
            "rel_f0_start": semitones(features["f0_start"], reference),
            "rel_f0_25": semitones(features["f0_25"], reference),
            "rel_f0_50": semitones(features["f0_50"], reference),
            "rel_f0_75": semitones(features["f0_75"], reference),
            "rel_f0_end": semitones(features["f0_end"], reference),
            "f0_range_st": semitones(features["max_f0_hz"], features["min_f0_hz"]),
            "slope_start_to_mid": features["slope_start_to_mid"],
            "slope_mid_to_end": features["slope_mid_to_end"],
            "duration_seconds": features["duration_seconds"],
            "voiced_proportion": features["voiced_proportion"],
        }
        for column, name in enumerate(PRAAT_FEATURES):
            matrix[index, column] = values[name]
    return matrix


def wav2vec_matrices(rows):
    """Mean and temporal-3 pooled embeddings from the frozen encoder."""
    from pronunciation.wav2vec_tone.cache_embeddings import mean_pool, temporal3_pool
    from pronunciation.wav2vec_tone.extract_embeddings import FrozenWav2Vec2
    import soundfile as sf

    encoder = FrozenWav2Vec2()
    if encoder.trainable_parameters != 0:
        sys.exit("encoder is not frozen")
    mean_rows, temporal_rows = [], []
    for index, row in enumerate(rows):
        audio, _ = sf.read(str(DATA_DIR / row["extracted_token_path"]), dtype="float32")
        inputs = encoder.processor(np.asarray(audio, dtype=np.float32),
                                   sampling_rate=SAMPLE_RATE, return_tensors="pt")
        with encoder._torch.no_grad():
            hidden = encoder.model(**inputs).last_hidden_state[0].numpy()
        mean_rows.append(mean_pool(hidden))
        temporal_rows.append(temporal3_pool(hidden))
        if (index + 1) % 250 == 0:
            print(f"    {index + 1}/{len(rows)}")
    return np.vstack(mean_rows), np.vstack(temporal_rows)


def build_cache(rows):
    if CACHE.exists():
        stored = np.load(CACHE, allow_pickle=True)
        if list(stored["token_ids"]) == [r["token_id"] for r in rows]:
            print("[cache] reusing extracted features")
            return {k: stored[k] for k in stored.files}
    print("[1] Praat features…")
    praat = praat_matrix(rows)
    print("[2] wav2vec2 embeddings (frozen)…")
    mean_matrix, temporal_matrix = wav2vec_matrices(rows)
    payload = {
        "praat": praat, "mean": mean_matrix, "temporal3": temporal_matrix,
        "token_ids": np.asarray([r["token_id"] for r in rows], dtype=object),
        "split": np.asarray([r["split"] for r in rows], dtype=object),
        "speaker": np.asarray([r["speaker_id"] for r in rows], dtype=object),
        "tone": np.asarray([r["expected_tone"] for r in rows], dtype=object),
        # y = 1 means Incorrect: the minority, and the class of interest.
        "y": np.asarray([1 if r["tone_correctness"] == "0" else 0 for r in rows]),
    }
    np.savez_compressed(CACHE, **payload)
    return payload


def tone_onehot(tones):
    return np.stack([(tones == t).astype(float) for t in ("1", "2", "3", "4")], axis=1)


def make_pipeline(class_weight, C, seed=0):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline as chain
    from sklearn.preprocessing import StandardScaler

    return chain(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(max_iter=5000, C=C, class_weight=class_weight,
                           random_state=seed),
    )


def metrics(y_true, probabilities, threshold) -> dict:
    from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
                                 f1_score, precision_score, recall_score,
                                 roc_auc_score)

    predicted = (probabilities >= threshold).astype(int)
    correct_mask = y_true == 0
    incorrect_mask = y_true == 1
    return {
        "pr_auc_incorrect": float(average_precision_score(y_true, probabilities)),
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predicted)),
        "macro_f1": float(f1_score(y_true, predicted, average="macro")),
        "incorrect_precision": float(precision_score(y_true, predicted, zero_division=0)),
        "incorrect_recall": float(recall_score(y_true, predicted, zero_division=0)),
        "incorrect_f1": float(f1_score(y_true, predicted, zero_division=0)),
        "accuracy": float((predicted == y_true).mean()),
        # A learner's experience: good speech rejected, bad speech waved through.
        "false_rejection_rate": float(predicted[correct_mask].mean())
        if correct_mask.any() else float("nan"),
        "false_acceptance_rate": float(1 - predicted[incorrect_mask].mean())
        if incorrect_mask.any() else float("nan"),
        "threshold": float(threshold),
    }


def best_f1_threshold(y_true, probabilities):
    """Pre-specified selection rule: maximise Incorrect F1 on Dev."""
    from sklearn.metrics import f1_score

    candidates = np.unique(np.round(probabilities, 4))
    best, best_score = 0.5, -1.0
    for threshold in candidates:
        score = f1_score(y_true, (probabilities >= threshold).astype(int),
                         zero_division=0)
        if score > best_score:
            best, best_score = float(threshold), score
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rows = load_rows()
    print(f"development rows: {len(rows)} "
          f"({sum(1 for r in rows if r['split'] == 'train')} train / "
          f"{sum(1 for r in rows if r['split'] == 'dev')} dev)")
    cache = build_cache(rows)

    split = cache["split"]
    train_mask, dev_mask = split == "train", split == "dev"
    y = cache["y"]
    tones = tone_onehot(cache["tone"])

    representations = {
        "MODEL_B_praat": {"praat": None},
    }
    blocks = {
        "MODEL_A_wav2vec2": lambda pooling: cache[pooling],
        "MODEL_B_praat": lambda pooling: cache["praat"],
        "MODEL_C_fusion": lambda pooling: np.hstack([cache[pooling], cache["praat"]]),
    }

    results = []
    for model in ("MODEL_A_wav2vec2", "MODEL_B_praat", "MODEL_C_fusion"):
        pooling_options = POOLINGS if model != "MODEL_B_praat" else ("n/a",)
        for pooling in pooling_options:
            base = blocks[model](pooling if pooling != "n/a" else "mean")
            features = np.hstack([base, tones])      # expected-tone encoding
            for class_weight in CLASS_WEIGHTS:
                for C in C_VALUES:
                    pipeline = make_pipeline(class_weight, C, args.seed)
                    pipeline.fit(features[train_mask], y[train_mask])
                    probabilities = pipeline.predict_proba(features[dev_mask])[:, 1]
                    threshold = best_f1_threshold(y[dev_mask], probabilities)
                    entry = metrics(y[dev_mask], probabilities, threshold)
                    entry.update({
                        "model": model, "pooling": pooling,
                        "class_weight": str(class_weight), "C": C,
                        "n_features": features.shape[1],
                    })
                    results.append(entry)
                    print(f"  {model:<18}{pooling:<11}cw={str(class_weight):<9}"
                          f"C={C:<6} PR-AUC {entry['pr_auc_incorrect']:.3f}  "
                          f"IncF1 {entry['incorrect_f1']:.3f}  "
                          f"FRR {entry['false_rejection_rate']:.3f}  "
                          f"FAR {entry['false_acceptance_rate']:.3f}")

    fields = ["model", "pooling", "class_weight", "C", "n_features",
              "pr_auc_incorrect", "roc_auc", "balanced_accuracy", "macro_f1",
              "incorrect_precision", "incorrect_recall", "incorrect_f1",
              "accuracy", "false_rejection_rate", "false_acceptance_rate",
              "threshold"]
    with RESULTS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for entry in results:
            writer.writerow({k: entry[k] for k in fields})

    winners = {}
    for model in ("MODEL_A_wav2vec2", "MODEL_B_praat", "MODEL_C_fusion"):
        subset = [r for r in results if r["model"] == model]
        winners[model] = max(subset, key=lambda r: r["pr_auc_incorrect"])
    overall = max(winners.values(), key=lambda r: r["pr_auc_incorrect"])

    print("\nbest per model (Dev PR-AUC for Incorrect):")
    for model, entry in winners.items():
        print(f"  {model:<18}PR-AUC {entry['pr_auc_incorrect']:.3f}  "
              f"ROC {entry['roc_auc']:.3f}  BalAcc {entry['balanced_accuracy']:.3f}  "
              f"IncF1 {entry['incorrect_f1']:.3f}  pooling={entry['pooling']}  "
              f"cw={entry['class_weight']}  C={entry['C']}")
    print(f"\nSELECTED: {overall['model']} pooling={overall['pooling']} "
          f"cw={overall['class_weight']} C={overall['C']}")

    deep = deep_analysis(cache, rows, overall, args.seed)
    freeze(overall, winners, deep, args.seed)
    print(f"\nresults : {RESULTS_CSV}")
    print(f"protocol: {PROTOCOL_LOCK}")


def deep_analysis(cache, rows, chosen, seed) -> dict:
    """Calibration, thresholds, uncertainty, and per-speaker/tone/quality views."""
    from sklearn.calibration import calibration_curve
    from sklearn.metrics import balanced_accuracy_score, brier_score_loss

    split = cache["split"]
    train_mask, dev_mask = split == "train", split == "dev"
    y = cache["y"]
    tones = tone_onehot(cache["tone"])
    pooling = chosen["pooling"] if chosen["pooling"] != "n/a" else "mean"
    base = (cache["praat"] if chosen["model"] == "MODEL_B_praat"
            else cache[pooling] if chosen["model"] == "MODEL_A_wav2vec2"
            else np.hstack([cache[pooling], cache["praat"]]))
    features = np.hstack([base, tones])

    class_weight = None if chosen["class_weight"] == "None" else chosen["class_weight"]
    pipeline = make_pipeline(class_weight, chosen["C"], seed)
    pipeline.fit(features[train_mask], y[train_mask])
    probabilities = pipeline.predict_proba(features[dev_mask])[:, 1]
    dev_y = y[dev_mask]
    threshold = chosen["threshold"]

    grid = []
    for candidate in np.round(np.arange(0.05, 0.96, 0.05), 2):
        entry = metrics(dev_y, probabilities, candidate)
        predicted = (probabilities >= candidate).astype(int)
        entry["pct_classified_incorrect"] = float(predicted.mean() * 100)
        entry["pct_classified_correct"] = float((1 - predicted).mean() * 100)
        grid.append(entry)

    fraction, mean_predicted = calibration_curve(dev_y, probabilities, n_bins=8,
                                                 strategy="quantile")
    calibration = {
        "brier": float(brier_score_loss(dev_y, probabilities)),
        "brier_baseline_prevalence": float(np.mean(
            (dev_y - dev_y.mean()) ** 2)),
        "bins": [{"mean_predicted": float(p), "observed": float(o)}
                 for p, o in zip(mean_predicted, fraction)],
        "mean_predicted_probability": float(probabilities.mean()),
        "observed_prevalence": float(dev_y.mean()),
    }

    predicted = (probabilities >= threshold).astype(int)
    errors = predicted != dev_y
    margin = np.abs(probabilities - threshold)
    uncertainty = {
        "error_margin_median": float(np.median(margin[errors])) if errors.any() else None,
        "correct_margin_median": float(np.median(margin[~errors])),
        "bands": [],
    }
    for width in (0.05, 0.10, 0.15, 0.20):
        band = margin < width
        uncertainty["bands"].append({
            "margin": width,
            "pct_dev_in_band": float(band.mean() * 100),
            "pct_of_errors_captured": float(errors[band].sum() / max(errors.sum(), 1) * 100),
            "accuracy_outside_band": float((predicted[~band] == dev_y[~band]).mean())
            if (~band).any() else None,
        })

    dev_rows = [r for r, keep in zip(rows, dev_mask) if keep]
    by_speaker = {}
    for speaker in sorted({r["speaker_id"] for r in dev_rows}):
        mask = np.asarray([r["speaker_id"] == speaker for r in dev_rows])
        by_speaker[speaker] = speaker_block(dev_y[mask], predicted[mask])
    by_tone = {}
    for tone in ("1", "2", "3", "4"):
        mask = np.asarray([r["expected_tone"] == tone for r in dev_rows])
        by_tone[f"T{tone}"] = speaker_block(dev_y[mask], predicted[mask])

    quality = {}
    for name in ("duration_seconds", "voiced_proportion", "alignment_score",
                 "rms_relative_db", "local_snr_db"):
        values = np.asarray([float(r[name]) if r[name] else np.nan
                             for r in dev_rows])
        finite = np.isfinite(values)
        if finite.sum() < 20:
            continue
        quality[name] = {
            "median_when_correct_prediction":
                float(np.median(values[finite & ~errors])),
            "median_when_error": float(np.median(values[finite & errors]))
            if (finite & errors).any() else None,
            "n_errors": int((finite & errors).sum()),
        }

    return {"threshold_grid": grid, "calibration": calibration,
            "uncertainty": uncertainty, "by_speaker": by_speaker,
            "by_tone": by_tone, "error_vs_quality": quality,
            "dev_probabilities_summary": {
                "min": float(probabilities.min()), "median": float(np.median(probabilities)),
                "max": float(probabilities.max())}}


def speaker_block(y_true, predicted) -> dict:
    from sklearn.metrics import balanced_accuracy_score

    incorrect = y_true == 1
    correct = y_true == 0
    return {
        "n": int(len(y_true)), "n_incorrect": int(incorrect.sum()),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predicted))
        if incorrect.any() and correct.any() else None,
        "incorrect_recall": float(predicted[incorrect].mean()) if incorrect.any() else None,
        "incorrect_precision": float(y_true[predicted == 1].mean())
        if (predicted == 1).any() else None,
        "false_rejection_rate": float(predicted[correct].mean()) if correct.any() else None,
        "false_acceptance_rate": float(1 - predicted[incorrect].mean())
        if incorrect.any() else None,
    }


def freeze(chosen, winners, deep, seed) -> None:
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "split_id": SPLIT_ID, "split_sha256": SPLIT_SHA,
        "phase": "C complete; D (sealed Test) next",
        "seed": seed,
        "expected_tone_policy": EXPECTED_TONE_POLICY,
        "praat_feature_set": list(PRAAT_FEATURES),
        "search_grid": {"pooling": list(POOLINGS),
                        "class_weight": [str(c) for c in CLASS_WEIGHTS],
                        "C": list(C_VALUES)},
        "selection_metric": "Dev PR-AUC for the Incorrect class",
        "threshold_rule": "maximise Incorrect F1 on Dev; frozen before Test",
        "selected_model": {k: chosen[k] for k in
                           ("model", "pooling", "class_weight", "C", "threshold")},
        "selected_dev_metrics": {k: chosen[k] for k in
                                 ("pr_auc_incorrect", "roc_auc", "balanced_accuracy",
                                  "macro_f1", "incorrect_precision",
                                  "incorrect_recall", "incorrect_f1", "accuracy",
                                  "false_rejection_rate", "false_acceptance_rate")},
        "per_model_best": {k: {kk: v[kk] for kk in
                               ("pooling", "class_weight", "C", "pr_auc_incorrect",
                                "roc_auc", "balanced_accuracy", "incorrect_f1",
                                "false_rejection_rate", "false_acceptance_rate")}
                           for k, v in winners.items()},
        "calibration": deep["calibration"],
        "uncertainty": deep["uncertainty"],
        "test_procedure": {
            "predictions_generated_in_phase_C": False,
            "features_extracted_for_test": False,
            "uncertainty_method": (
                "speaker-cluster bootstrap: resample the 7 Test speakers with "
                "replacement 2000 times, recompute every metric within each "
                "resample, report 2.5/97.5 percentiles. Tokens are clustered "
                "within speakers, so token-level bootstrap would understate "
                "the interval."),
            "run_once": True,
            "no_refit_or_retune_after_test": True,
        },
        "frozen_note": ("Model, hyperparameters and threshold are frozen. Test "
                        "is evaluated once and must not inform any further "
                        "modelling choice."),
    }
    PROTOCOL_LOCK.write_text(json.dumps(payload, indent=2, ensure_ascii=False,
                                        default=float), encoding="utf-8")
    (DATA_DIR / "ompal_dev_deep_analysis.json").write_text(
        json.dumps(deep, indent=2, ensure_ascii=False, default=float),
        encoding="utf-8")


if __name__ == "__main__":
    main()
