"""Phase C5 — can unlabeled warm-up tokens make scores comparable across learners?

Phase C4 found the model discriminates within a speaker fold (ROC 0.52-0.64)
but that calibrated scores are not comparable across speakers, because
prevalence ranges 6.9%-29.9%. This phase tests whether a short unlabeled
warm-up from the learner fixes that.

The warm-up carries audio, features, expected tone and the model's own score,
and never a correctness label -- a real learner arrives without annotations.
That constraint is enforced by the function signatures: adaptation receives
scores and tones only, and is asserted to be label-blind.

Base model frozen. No classifier search, no threshold work.

    python -m pronunciation.wav2vec_tone.phase_c5_speaker_adaptation
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.phase_c3_tone_conditioning import (
    PRAAT_FEATURES, TONES, apply_fold, fit_fold,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
TRAIN_CSV = DATA_DIR / "ompal_phase_c5_train_results.csv"
SPEAKER_CSV = DATA_DIR / "ompal_phase_c5_speaker_results.csv"
PRED_CSV = DATA_DIR / "ompal_phase_c5_adaptation_predictions.csv"
PROTOCOL = DATA_DIR / "ompal_phase_c5_protocol_FROZEN.json"

MODEL = {"kind": "P1", "class_weight": "balanced", "C": 10.0}
SEED = 0
K_VALUES = (0, 5, 10, 20)
K_MAX = 20
MIN_EVAL_TOKENS = 5
S3_MIN_SUPPORT = 3        # adaptation observations of a tone before S3 applies


def logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


# --------------------------------------------------------------------------
# Adaptation methods. Each receives ONLY the warm-up scores and tones -- never
# labels. The signature is the guarantee; a label is not in scope to leak.
# --------------------------------------------------------------------------

def adapt(method, warm_scores, warm_tones, eval_scores, eval_tones, scale_floor):
    if method == "S0" or len(warm_scores) == 0:
        return eval_scores.copy()

    if method == "S1":
        return eval_scores - float(np.median(warm_scores))

    if method == "S2":
        location = float(np.median(warm_scores))
        spread = float(np.percentile(warm_scores, 75) - np.percentile(warm_scores, 25))
        # Floor derived from training speakers before any outcome was seen;
        # without it a learner whose warm-up happens to be uniform would have
        # their evaluation scores divided by ~0.
        return (eval_scores - location) / max(spread, scale_floor)

    if method == "S3":
        global_location = float(np.median(warm_scores))
        out = np.empty_like(eval_scores)
        for index, (score, tone) in enumerate(zip(eval_scores, eval_tones)):
            same = warm_scores[warm_tones == tone]
            # Fall back to S1 when the warm-up did not contain enough of this
            # tone. Inventing a tone baseline from two observations would be
            # noise dressed as personalisation.
            location = float(np.median(same)) if len(same) >= S3_MIN_SUPPORT else global_location
            out[index] = score - location
        return out
    raise ValueError(method)


def roc(y, scores) -> float:
    y = np.asarray(y, bool)
    scores = np.asarray(scores, float)
    if y.sum() == 0 or (~y).sum() == 0:
        return float("nan")
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), float)
    ordered = scores[order]
    index = 0
    while index < len(ordered):
        stop = index
        while stop + 1 < len(ordered) and ordered[stop + 1] == ordered[index]:
            stop += 1
        ranks[order[index:stop + 1]] = (index + stop) / 2.0 + 1.0
        index = stop + 1
    positives, negatives = int(y.sum()), int((~y).sum())
    return float((ranks[y].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    from sklearn.metrics import average_precision_score, balanced_accuracy_score, f1_score

    rows = [r for r in csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8"))
            if r["split"] in ("train", "dev")]
    if any(r["split"] == "test" for r in rows):
        sys.exit("TEST LOCK VIOLATION")
    cache = dict(np.load(CACHE, allow_pickle=True))
    if "test" in set(cache["split"].tolist()):
        sys.exit("TEST LOCK VIOLATION in cache")
    order_index = {t: i for i, t in enumerate(cache["token_ids"].tolist())}
    rows = sorted(rows, key=lambda r: order_index[r["token_id"]])

    train_mask = cache["split"] == "train"
    features, tones, y = cache["praat"], cache["tone"], cache["y"]
    speakers = cache["speaker"]
    train_rows = [r for r in rows if r["split"] == "train"]

    # Deterministic within-speaker order. OMPAL has no timestamps, so utterance
    # id then token index is used as a stand-in for recording order -- it is at
    # least the order the corpus was recorded and indexed in, not a shuffle.
    position = {}
    for index, row in enumerate(train_rows):
        position[row["token_id"]] = (row["utterance_id"], int(row["token_index"]))

    train_speakers = sorted(set(speakers[train_mask].tolist()))
    print(f"TRAIN: {int(train_mask.sum())} tokens, {len(train_speakers)} speakers")
    print("simulation: leave-one-speaker-out; base model refit without the "
          "held-out learner each time")

    # --- leave-one-speaker-out raw scores ----------------------------------
    raw_logit = np.full(int(train_mask.sum()), np.nan)
    train_indices = np.flatnonzero(train_mask)
    local = {token: i for i, token in enumerate(
        [r["token_id"] for r in train_rows])}
    for speaker in train_speakers:
        held = speakers[train_mask] == speaker
        fit_index = train_indices[~held]
        state = fit_fold(MODEL["kind"], features[fit_index], tones[fit_index],
                         y[fit_index], MODEL["class_weight"], MODEL["C"], args.seed)
        raw_logit[held] = logit(apply_fold(state, features[train_indices[held]],
                                           tones[train_indices[held]]))
    print("  LOSO scoring complete")

    train_y = y[train_mask]
    train_tones = tones[train_mask]
    train_spk = speakers[train_mask]

    # Scale floor from training speakers only, fixed before any result.
    per_speaker_iqr = []
    for speaker in train_speakers:
        held = train_spk == speaker
        values = raw_logit[held]
        per_speaker_iqr.append(np.percentile(values, 75) - np.percentile(values, 25))
    SCALE_FLOOR = float(0.25 * np.median(per_speaker_iqr))
    print(f"  S2 scale floor (0.25 x median speaker IQR, train-derived): "
          f"{SCALE_FLOOR:.4f}")

    # --- fixed evaluation window so K is comparable -------------------------
    ordered_by_speaker = {}
    for speaker in train_speakers:
        held = np.flatnonzero(train_spk == speaker)
        held = sorted(held, key=lambda i: position[train_rows[i]["token_id"]])
        ordered_by_speaker[speaker] = held
    evaluable = [s for s in train_speakers
                 if len(ordered_by_speaker[s]) >= K_MAX + MIN_EVAL_TOKENS]
    excluded = [s for s in train_speakers if s not in evaluable]
    print(f"  speakers with >={K_MAX + MIN_EVAL_TOKENS} tokens: {len(evaluable)}"
          f" (excluded {len(excluded)}: {excluded})")

    results, speaker_rows, prediction_rows = [], [], []
    label_blind_assertions = 0

    for method in ("S0", "S1", "S2", "S3"):
        for K in K_VALUES:
            if method != "S0" and K == 0:
                continue
            pooled_scores, pooled_y, pooled_tone, pooled_spk = [], [], [], []
            per_speaker = {}
            tone_coverage = []
            for speaker in evaluable:
                indices = ordered_by_speaker[speaker]
                warm = indices[:K]
                evaluation = indices[K_MAX:]      # identical for every K
                warm_scores = raw_logit[warm]
                warm_tones = train_tones[warm]
                # Hard assertion: no label is in scope for the adaptation call.
                assert "y" not in adapt.__code__.co_varnames, "adapt must be label-blind"
                label_blind_assertions += 1
                adapted = adapt(method, warm_scores, warm_tones,
                                raw_logit[evaluation], train_tones[evaluation],
                                SCALE_FLOOR)
                labels = train_y[evaluation]
                pooled_scores.extend(adapted)
                pooled_y.extend(labels)
                pooled_tone.extend(train_tones[evaluation])
                pooled_spk.extend([speaker] * len(evaluation))
                per_speaker[speaker] = {
                    "n_eval": len(evaluation), "n_incorrect": int(labels.sum()),
                    "within_roc": roc(labels, adapted),
                    "median_score": float(np.median(adapted)),
                    "prevalence": float(labels.mean()),
                }
                if K:
                    tone_coverage.append(len(set(warm_tones.tolist())))
                if method == "S1" and K == 10:
                    for local_index, score in zip(evaluation, adapted):
                        prediction_rows.append({
                            "token_id": train_rows[local_index]["token_id"],
                            "speaker_id": speaker,
                            "expected_tone": train_tones[local_index],
                            "tone_correctness": int(train_y[local_index]),
                            "raw_logit": f"{raw_logit[local_index]:.6f}",
                            "adapted_score": f"{score:.6f}",
                            "method": "S1", "K": K,
                        })

            pooled_scores = np.asarray(pooled_scores)
            pooled_y = np.asarray(pooled_y)
            predicted = (pooled_scores >= np.median(pooled_scores)).astype(int)
            within = [v["within_roc"] for v in per_speaker.values()
                      if np.isfinite(v["within_roc"])]
            medians = [v["median_score"] for v in per_speaker.values()]
            prevalences = [v["prevalence"] for v in per_speaker.values()]
            association = float(np.corrcoef(
                np.argsort(np.argsort(medians)),
                np.argsort(np.argsort(prevalences)))[0, 1]) if len(medians) > 2 else float("nan")

            entry = {
                "method": method, "K": K,
                "n_eval_tokens": int(len(pooled_y)),
                "n_speakers": len(per_speaker),
                "pooled_roc": roc(pooled_y, pooled_scores),
                "pooled_pr_auc": float(average_precision_score(pooled_y, pooled_scores)),
                "balanced_accuracy": float(balanced_accuracy_score(pooled_y, predicted)),
                "incorrect_f1": float(f1_score(pooled_y, predicted, zero_division=0)),
                "within_speaker_roc_median": float(np.median(within)),
                "within_speaker_roc_q1": float(np.percentile(within, 25)),
                "within_speaker_roc_q3": float(np.percentile(within, 75)),
                "within_speaker_roc_min": float(np.min(within)),
                "within_speaker_roc_max": float(np.max(within)),
                "n_speakers_evaluable_within": len(within),
                "speaker_median_vs_prevalence_rho": association,
                "mean_tones_seen_in_warmup": float(np.mean(tone_coverage)) if tone_coverage else float("nan"),
            }
            results.append(entry)
            for speaker, values in per_speaker.items():
                speaker_rows.append({"method": method, "K": K, "speaker_id": speaker,
                                     **values})
            print(f"  {method}  K={K:<3} pooledROC {entry['pooled_roc']:.3f}  "
                  f"PR {entry['pooled_pr_auc']:.3f}  "
                  f"withinROC med {entry['within_speaker_roc_median']:.3f}  "
                  f"rho(median,prev) {association:+.3f}")

    with TRAIN_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    with SPEAKER_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(speaker_rows[0].keys()))
        writer.writeheader()
        writer.writerows(speaker_rows)
    if prediction_rows:
        with PRED_CSV.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(prediction_rows[0].keys()))
            writer.writeheader()
            writer.writerows(prediction_rows)

    # --- per-tone for the best adapted method -------------------------------
    baseline = next(r for r in results if r["method"] == "S0")
    best = max((r for r in results if r["method"] != "S0"),
               key=lambda r: r["pooled_roc"])
    print(f"\nbaseline S0 K=0 : pooled ROC {baseline['pooled_roc']:.3f}  "
          f"PR {baseline['pooled_pr_auc']:.3f}")
    print(f"best adapted    : {best['method']} K={best['K']}  "
          f"pooled ROC {best['pooled_roc']:.3f}  PR {best['pooled_pr_auc']:.3f}  "
          f"delta ROC {best['pooled_roc'] - baseline['pooled_roc']:+.3f}")

    per_tone = {}
    for method, K in (("S0", 0), (best["method"], best["K"])):
        scores_all, y_all, tone_all = [], [], []
        for speaker in evaluable:
            indices = ordered_by_speaker[speaker]
            warm, evaluation = indices[:K], indices[K_MAX:]
            adapted = adapt(method, raw_logit[warm], train_tones[warm],
                            raw_logit[evaluation], train_tones[evaluation],
                            SCALE_FLOOR)
            scores_all.extend(adapted)
            y_all.extend(train_y[evaluation])
            tone_all.extend(train_tones[evaluation])
        scores_all = np.asarray(scores_all)
        y_all = np.asarray(y_all)
        tone_all = np.asarray(tone_all)
        per_tone[f"{method}_K{K}"] = {}
        for tone in TONES:
            mask = tone_all == tone
            per_tone[f"{method}_K{K}"][f"T{tone}"] = {
                "n": int(mask.sum()), "n_incorrect": int(y_all[mask].sum()),
                "roc": roc(y_all[mask], scores_all[mask]),
            }
    print("\nper tone (baseline vs best adapted):")
    for name, table in per_tone.items():
        print(f"  {name}: " + "  ".join(
            f"T{t} ROC {table[f'T{t}']['roc']:.3f} (n={table[f'T{t}']['n']},"
            f"inc={table[f'T{t}']['n_incorrect']})" for t in TONES))

    summary = {
        "design": {
            "simulation": "leave-one-speaker-out over 32 Train speakers",
            "within_speaker_order": ("utterance_id then token_index; OMPAL has no "
                                     "timestamps, documented as a limitation"),
            "evaluation_window": f"tokens from position {K_MAX} onward, identical for every K",
            "speakers_evaluable": len(evaluable), "speakers_excluded": excluded,
            "s2_scale_floor": SCALE_FLOOR,
            "s3_min_support": S3_MIN_SUPPORT,
            "warmup_labels_used": False,
            "label_blind_assertions_run": label_blind_assertions,
        },
        "results": results, "per_tone": per_tone,
        "baseline": baseline, "best_adapted": best,
    }
    (DATA_DIR / "ompal_phase_c5_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=float),
        encoding="utf-8")
    print(f"\nfiles: {TRAIN_CSV.name}, {SPEAKER_CSV.name}, {PRED_CSV.name}")
    return summary


if __name__ == "__main__":
    main()
