"""Phase C2 — why does acoustic information fail to separate the OMPAL labels?

A protocol amendment, motivated by near-chance Dev performance. No Test data is
read, no split changes, no threshold tuning, no model search. The question is
diagnostic: is the target label wrong for the task, or is the signal absent
from the representations?

    python -m pronunciation.wav2vec_tone.phase_c2_diagnostics
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

DATA_DIR = Path(__file__).resolve().parent / "data"
OMPAL_DIR = Path(__file__).resolve().parents[2] / "private-data" / "ompal"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
OUT_JSON = DATA_DIR / "ompal_phase_c2_diagnostics.json"
OUT_CSV = DATA_DIR / "ompal_phase_c2_feature_diagnostics.csv"

PRAAT_FEATURES = (
    "rel_f0_start", "rel_f0_25", "rel_f0_50", "rel_f0_75", "rel_f0_end",
    "f0_range_st", "slope_start_to_mid", "slope_mid_to_end",
    "duration_seconds", "voiced_proportion",
)
# Small, pre-specified layer probe. Not a sweep: early / middle / final only.
LAYERS = {"early_L1": 1, "middle_L6": 6, "final_L12": 12}


def assert_test_sealed(rows):
    if any(r["split"] == "test" for r in rows):
        sys.exit("TEST LOCK VIOLATION: test rows present")
    stored = np.load(CACHE, allow_pickle=True)
    if "test" in set(stored["split"].tolist()):
        sys.exit("TEST LOCK VIOLATION: test rows in feature cache")
    return {"test_features": False, "test_embeddings": False,
            "test_predictions": False, "test_metrics": False,
            "test_error_analysis": False}


def auc(values, labels) -> float:
    values = np.asarray(values, float)
    labels = np.asarray(labels, bool)
    keep = np.isfinite(values)
    values, labels = values[keep], labels[keep]
    positives, negatives = int(labels.sum()), int((~labels).sum())
    if not positives or not negatives:
        return float("nan")
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values))
    ordered = values[order]
    index = 0
    while index < len(ordered):
        stop = index
        while stop + 1 < len(ordered) and ordered[stop + 1] == ordered[index]:
            stop += 1
        ranks[order[index:stop + 1]] = (index + stop) / 2.0 + 1.0
        index = stop + 1
    return float((ranks[labels].sum() - positives * (positives + 1) / 2)
                 / (positives * negatives))


def cohens_d(a, b) -> float:
    a = np.asarray([x for x in a if np.isfinite(x)], float)
    b = np.asarray([x for x in b if np.isfinite(x)], float)
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    pooled = np.sqrt(((len(a) - 1) * a.var(ddof=1)
                      + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
    return float((a.mean() - b.mean()) / pooled) if pooled > 0 else float("nan")


def overlap_coefficient(a, b, bins=40) -> float:
    """Share of the two score distributions that coincides. 1.0 = identical."""
    a = np.asarray([x for x in a if np.isfinite(x)], float)
    b = np.asarray([x for x in b if np.isfinite(x)], float)
    if not len(a) or not len(b):
        return float("nan")
    edges = np.linspace(min(a.min(), b.min()), max(a.max(), b.max()), bins + 1)
    pa, _ = np.histogram(a, bins=edges, density=False)
    pb, _ = np.histogram(b, bins=edges, density=False)
    pa = pa / pa.sum()
    pb = pb / pb.sum()
    return float(np.minimum(pa, pb).sum())


def label_provenance(rows) -> dict:
    """What an OMPAL 'Incorrect' actually is, from the annotation files."""
    payload = json.loads((OMPAL_DIR / "non-native_scores-detail.json")
                         .read_text(encoding="utf-8"))

    def majority(values):
        return 1 if sum(1 for v in values if v == "1") * 2 >= len(values) else 0

    combos = Counter()
    for row in rows:
        word = payload[row["utterance_id"]]["words"][int(row["token_index"])]
        combos[(majority(word["tone"]), majority(word["phoneme_consonant"]),
                majority(word["phoneme_vowel"]))] += 1
    incorrect = sum(n for k, n in combos.items() if k[0] == 0)
    isolated = combos.get((0, 1, 1), 0)
    whole_token = combos.get((0, 0, 0), 0)
    return {
        "source_file": "non-native_scores-detail.json",
        "field_used": "words[i].tone",
        "sibling_fields_not_used": ["phoneme_consonant", "phoneme_vowel"],
        "transformation": ("three rater strings '1'/'0' -> majority (>=2 of 3) "
                           "-> majority_tone_correct -> Correct/Incorrect"),
        "combination_counts": {f"tone={k[0]},cons={k[1]},vowel={k[2]}": n
                               for k, n in sorted(combos.items(), reverse=True)},
        "incorrect_total": incorrect,
        "isolated_tone_error": isolated,
        "isolated_tone_error_pct": isolated / incorrect * 100,
        "whole_token_failure": whole_token,
        "whole_token_failure_pct": whole_token / incorrect * 100,
        "any_segmental_co_error": incorrect - isolated,
        "any_segmental_co_error_pct": (incorrect - isolated) / incorrect * 100,
        "is_tone_correctness_label": "YES (with a small documented contamination)",
    }


def model_b_scores(cache, seed=0):
    """Refit the selected MODEL_B exactly as frozen; Train and Dev only."""
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    split = cache["split"]
    train, dev = split == "train", split == "dev"
    tones = np.stack([(cache["tone"] == t).astype(float)
                      for t in ("1", "2", "3", "4")], axis=1)
    features = np.hstack([cache["praat"], tones])
    pipeline = make_pipeline(
        SimpleImputer(strategy="median"), StandardScaler(),
        LogisticRegression(max_iter=5000, C=0.01, class_weight=None,
                           random_state=seed))
    pipeline.fit(features[train], cache["y"][train])
    return (pipeline.predict_proba(features[train])[:, 1],
            pipeline.predict_proba(features[dev])[:, 1], train, dev)


def layer_probe(rows, cache, seed=0) -> dict:
    """Does an earlier wav2vec2 layer retain signal the final layer discards?"""
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from pronunciation.wav2vec_tone.extract_embeddings import FrozenWav2Vec2
    import soundfile as sf

    encoder = FrozenWav2Vec2()
    pooled = {name: [] for name in LAYERS}
    for index, row in enumerate(rows):
        audio, _ = sf.read(str(DATA_DIR / row["extracted_token_path"]),
                           dtype="float32")
        inputs = encoder.processor(np.asarray(audio, dtype=np.float32),
                                   sampling_rate=16000, return_tensors="pt")
        with encoder._torch.no_grad():
            output = encoder.model(**inputs, output_hidden_states=True)
        for name, layer in LAYERS.items():
            pooled[name].append(
                output.hidden_states[layer][0].numpy().mean(axis=0))
        if (index + 1) % 400 == 0:
            print(f"    layer probe {index + 1}/{len(rows)}")

    split = cache["split"]
    train, dev = split == "train", split == "dev"
    tones = np.stack([(cache["tone"] == t).astype(float)
                      for t in ("1", "2", "3", "4")], axis=1)
    results = {}
    for name in LAYERS:
        features = np.hstack([np.vstack(pooled[name]), tones])
        pipeline = make_pipeline(
            SimpleImputer(strategy="median"), StandardScaler(),
            LogisticRegression(max_iter=5000, C=0.01, random_state=seed))
        pipeline.fit(features[train], cache["y"][train])
        probabilities = pipeline.predict_proba(features[dev])[:, 1]
        results[name] = {
            "layer_index": LAYERS[name],
            "dev_pr_auc": float(average_precision_score(cache["y"][dev], probabilities)),
            "dev_roc_auc": float(roc_auc_score(cache["y"][dev], probabilities)),
        }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-layers", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rows = [r for r in csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8"))
            if r["split"] in ("train", "dev")]
    lock = assert_test_sealed(rows)
    print(f"test lock verified: {lock}")

    cache = dict(np.load(CACHE, allow_pickle=True))
    order = {t: i for i, t in enumerate(cache["token_ids"].tolist())}
    rows = sorted(rows, key=lambda r: order[r["token_id"]])

    provenance = label_provenance(rows)
    print(f"\nlabel: {provenance['isolated_tone_error']}/{provenance['incorrect_total']} "
          f"({provenance['isolated_tone_error_pct']:.1f}%) of Incorrect are isolated "
          f"tone errors")

    train_scores, dev_scores, train_mask, dev_mask = model_b_scores(cache, args.seed)
    y = cache["y"]
    tones = cache["tone"]

    # --- score distributions ------------------------------------------------
    distributions = {}
    for name, scores, mask in (("train", train_scores, train_mask),
                               ("dev", dev_scores, dev_mask)):
        labels = y[mask]
        good, bad = scores[labels == 0], scores[labels == 1]
        distributions[name] = {
            "correct": {"n": int(len(good)), "mean": float(good.mean()),
                        "median": float(np.median(good)),
                        "iqr": [float(np.percentile(good, 25)),
                                float(np.percentile(good, 75))]},
            "incorrect": {"n": int(len(bad)), "mean": float(bad.mean()),
                          "median": float(np.median(bad)),
                          "iqr": [float(np.percentile(bad, 25)),
                                  float(np.percentile(bad, 75))]},
            "cohens_d": cohens_d(bad, good),
            "overlap_coefficient": overlap_coefficient(good, bad),
            "auc": auc(scores, labels == 1),
        }

    # --- within-tone separability ------------------------------------------
    from sklearn.metrics import average_precision_score
    within_tone = {}
    for tone in ("1", "2", "3", "4"):
        entry = {}
        for name, scores, mask in (("train", train_scores, train_mask),
                                   ("dev", dev_scores, dev_mask)):
            selector = tones[mask] == tone
            labels = y[mask][selector]
            values = scores[selector]
            if labels.sum() < 5 or (labels == 0).sum() < 5:
                entry[name] = {"n": int(len(labels)),
                               "n_incorrect": int(labels.sum()),
                               "note": "denominator too small"}
                continue
            entry[name] = {
                "n": int(len(labels)), "n_incorrect": int(labels.sum()),
                "prevalence": float(labels.mean()),
                "roc_auc": auc(values, labels == 1),
                "pr_auc": float(average_precision_score(labels, values)),
                "cohens_d": cohens_d(values[labels == 1], values[labels == 0]),
            }
        within_tone[f"T{tone}"] = entry

    # --- univariate Praat features, Train direction vs Dev replication ------
    feature_rows = []
    for column, name in enumerate(PRAAT_FEATURES):
        values = cache["praat"][:, column]
        entry = {"feature": name}
        for phase, mask in (("train", train_mask), ("dev", dev_mask)):
            labels = y[mask]
            subset = values[mask]
            entry[f"{phase}_auc"] = auc(subset, labels == 1)
            entry[f"{phase}_d"] = cohens_d(subset[labels == 1], subset[labels == 0])
        # Replication means the same direction AND a Dev effect that is not
        # merely noise around zero; a sign flip is the clearest failure.
        train_direction = np.sign(entry["train_auc"] - 0.5)
        dev_direction = np.sign(entry["dev_auc"] - 0.5)
        entry["train_direction"] = "higher->incorrect" if train_direction > 0 else "lower->incorrect"
        entry["dev_direction"] = "higher->incorrect" if dev_direction > 0 else "lower->incorrect"
        entry["replicates"] = bool(train_direction == dev_direction
                                   and abs(entry["dev_auc"] - 0.5) >= 0.03)
        feature_rows.append(entry)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(feature_rows[0].keys()))
        writer.writeheader()
        writer.writerows(feature_rows)

    layers = {} if args.skip_layers else layer_probe(rows, cache, args.seed)

    diagnostics = {
        "phase": "C2",
        "amendment_reason": ("near-chance Dev performance across all three "
                             "systems; diagnose task/label/signal before any "
                             "reformulation"),
        "test_lock": lock,
        "label_provenance": provenance,
        "score_distributions_model_b": distributions,
        "within_tone_separability_model_b": within_tone,
        "praat_univariate": feature_rows,
        "wav2vec2_layer_probe": layers,
        "model_inputs": {
            "MODEL_A": {
                "checkpoint": "TencentGameMate/chinese-wav2vec2-base",
                "pretraining": "Mandarin (Chinese) self-supervised, adult native speech",
                "layer": "final hidden state (layer 12)",
                "pooling": "mean or temporal-3",
                "dimension": "768 (mean) / 2304 (temporal-3)",
                "expected_tone_encoding": "one-hot, 4 dims, concatenated",
                "frozen": True,
            },
            "MODEL_B": {
                "features": list(PRAAT_FEATURES),
                "groups": {
                    "f0_tone_shape": ["rel_f0_start", "rel_f0_25", "rel_f0_50",
                                      "rel_f0_75", "rel_f0_end", "f0_range_st",
                                      "slope_start_to_mid", "slope_mid_to_end"],
                    "duration": ["duration_seconds"],
                    "voicing": ["voiced_proportion"],
                    "intensity": [],
                    "segment_audio_quality": [],
                    "other": [],
                },
                "normalisation": "per-syllable semitones vs the token's own median F0",
            },
            "MODEL_C": "MODEL_A representation concatenated with MODEL_B vector",
        },
    }
    OUT_JSON.write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False,
                                   default=float), encoding="utf-8")

    print("\nscore distributions (MODEL_B):")
    for name, entry in distributions.items():
        print(f"  {name}: correct median {entry['correct']['median']:.4f} vs "
              f"incorrect {entry['incorrect']['median']:.4f}  d={entry['cohens_d']:.3f}  "
              f"overlap={entry['overlap_coefficient']:.3f}  AUC={entry['auc']:.3f}")
    print("\nwithin-tone (Dev):")
    for tone, entry in within_tone.items():
        dev = entry.get("dev", {})
        if "roc_auc" in dev:
            print(f"  {tone}: n={dev['n']} inc={dev['n_incorrect']} "
                  f"ROC={dev['roc_auc']:.3f} PR={dev['pr_auc']:.3f} d={dev['cohens_d']:.3f}")
        else:
            print(f"  {tone}: {dev.get('note')} (n={dev.get('n')}, "
                  f"inc={dev.get('n_incorrect')})")
    print("\npraat univariate (train AUC -> dev AUC, replicates?):")
    for entry in feature_rows:
        print(f"  {entry['feature']:<22}{entry['train_auc']:.3f} -> "
              f"{entry['dev_auc']:.3f}   {'YES' if entry['replicates'] else 'no'}")
    if layers:
        print("\nwav2vec2 layer probe (Dev):")
        for name, entry in layers.items():
            print(f"  {name:<12}PR-AUC {entry['dev_pr_auc']:.3f}  "
                  f"ROC {entry['dev_roc_auc']:.3f}")
    print(f"\nsaved: {OUT_JSON}\n       {OUT_CSV}")


if __name__ == "__main__":
    main()
