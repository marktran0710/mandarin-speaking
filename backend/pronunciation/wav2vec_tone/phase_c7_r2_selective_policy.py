"""Phase C7 — selective decision policy on the frozen R2 trajectory model.

A re-run of the C4 decision-policy question against a stronger representation.
Nothing about R2 is searched or retuned. Test is sealed.

Two rules carried in from earlier phases and applied here:

* A token whose F0 trajectory could not be extracted may never receive an
  automatic verdict. That is a deployment safety rule, not a data exclusion --
  the token stays in every denominator and routes to RETRY.
* Calibration is nested and speaker-grouped with a SINGLE base model and a
  SINGLE sigmoid per outer fold. sklearn's CalibratedClassifierCV averages k
  inner models, so its output is not a monotone transform of the outer score;
  in C4 that alone moved ROC from 0.586 to 0.428.

    python -m pronunciation.wav2vec_tone.phase_c7_r2_selective_policy
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

from pronunciation.wav2vec_tone.phase_c6_f0_trajectory import (
    N_POINTS, TONES, design, fit_predict, normalise,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
TRAJ_CACHE = DATA_DIR / "phase_c6_trajectories.npz"
CALIB_CSV = DATA_DIR / "ompal_phase_c7_calibration_results.csv"
CURVE_CSV = DATA_DIR / "ompal_phase_c7_binary_operating_curve.csv"
COVERAGE_CSV = DATA_DIR / "ompal_phase_c7_coverage_risk.csv"
OOF_CSV = DATA_DIR / "ompal_phase_c7_train_oof_predictions.csv"
SUMMARY = DATA_DIR / "ompal_phase_c7_summary.json"
POLICY = DATA_DIR / "ompal_phase_c7_policy_FROZEN.json"

C_VALUE, CLASS_WEIGHT, N_FOLDS, INNER_FOLDS, SEED = 0.1, "balanced", 5, 4, 0

# C4's admission rules, unchanged. The task specifies 0.60 for Incorrect
# precision; C4's own frozen rule was 0.50, so both are evaluated for
# continuity and neither is weakened because R2 might fail it.
MIN_INCORRECT_PRECISION = 0.60
C4_ORIGINAL_INCORRECT_PRECISION = 0.50
MIN_ACCEPTABLE_PRECISION = 0.90
MIN_DECISIONS = 10


def logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def cross_fitted(base, tones, y, speakers, seed):
    """Raw and calibrated OOF scores; one base model + one sigmoid per fold."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold

    raw = np.zeros(len(y))
    calibrated = np.zeros(len(y))
    fold_id = np.zeros(len(y), int)
    for number, (train_index, test_index) in enumerate(
            GroupKFold(n_splits=N_FOLDS).split(np.zeros(len(y)), groups=speakers), 1):
        inner = np.zeros(len(train_index))
        for inner_train, inner_test in GroupKFold(n_splits=INNER_FOLDS).split(
                np.zeros(len(train_index)), groups=speakers[train_index]):
            a, b = train_index[inner_train], train_index[inner_test]
            inner[inner_test], _ = fit_predict(base[a], tones[a], y[a],
                                               base[b], tones[b], C_VALUE, seed)
        sigmoid = LogisticRegression(max_iter=2000).fit(
            logit(inner).reshape(-1, 1), y[train_index])
        scores, _ = fit_predict(base[train_index], tones[train_index], y[train_index],
                                base[test_index], tones[test_index], C_VALUE, seed)
        raw[test_index] = scores
        calibrated[test_index] = sigmoid.predict_proba(
            logit(scores).reshape(-1, 1))[:, 1]
        fold_id[test_index] = number
    return raw, calibrated, fold_id


def calibration_report(y, scores, label) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

    fit = LogisticRegression(max_iter=2000).fit(logit(scores).reshape(-1, 1), y)
    edges = np.quantile(scores, np.linspace(0, 1, 9))
    edges[-1] += 1e-9
    bins = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (scores >= low) & (scores < high)
        if mask.sum():
            bins.append({"n": int(mask.sum()),
                         "mean_predicted": float(scores[mask].mean()),
                         "observed": float(y[mask].mean())})
    return {"which": label, "brier": float(brier_score_loss(y, scores)),
            "log_loss": float(log_loss(y, scores, labels=[0, 1])),
            "calibration_slope": float(fit.coef_[0][0]),
            "calibration_intercept": float(fit.intercept_[0]),
            "mean_predicted": float(scores.mean()),
            "observed_prevalence": float(y.mean()),
            "pooled_roc": float(roc_auc_score(y, scores)), "bins": bins}


def policy_outcome(scores, tones, available, t_accept, t_incorrect, t2_safe):
    """ACCEPTABLE / UNCERTAIN / INCORRECT, with the availability safety rule."""
    accept = (scores <= t_accept) & available
    flag = (scores >= t_incorrect) & available
    if t2_safe:
        flag = flag & (tones != "2")
    return accept, flag, ~(accept | flag)


def evaluate_policy(y, scores, tones, speakers, available, t_accept,
                    t_incorrect, t2_safe) -> dict:
    accept, flag, uncertain = policy_outcome(scores, tones, available,
                                             t_accept, t_incorrect, t2_safe)
    automatic = accept | flag
    accepted_correct = int((accept & (y == 0)).sum())
    accepted_incorrect = int((accept & (y == 1)).sum())
    flagged_incorrect = int((flag & (y == 1)).sum())
    flagged_correct = int((flag & (y == 0)).sum())
    errors = accepted_incorrect + flagged_correct
    by_speaker = Counter(s for s, a in zip(speakers, automatic) if a)
    return {
        "t_accept": float(t_accept), "t_incorrect": float(t_incorrect),
        "t2_safe": bool(t2_safe), "n": int(len(y)),
        "n_acceptable": int(accept.sum()), "n_uncertain": int(uncertain.sum()),
        "n_incorrect": int(flag.sum()),
        "coverage": float(automatic.mean()),
        "abstention_rate": float(uncertain.mean()),
        "acceptable_precision": (accepted_correct / accept.sum()) if accept.sum() else float("nan"),
        "incorrect_precision": (flagged_incorrect / flag.sum()) if flag.sum() else float("nan"),
        "incorrect_recall": float(flagged_incorrect / max(int((y == 1).sum()), 1)),
        "selective_error": (errors / automatic.sum()) if automatic.sum() else float("nan"),
        "false_acceptance_among_accepted": (accepted_incorrect / accept.sum()) if accept.sum() else float("nan"),
        "false_rejection_among_flagged": (flagged_correct / flag.sum()) if flag.sum() else float("nan"),
        "accepted_correct": accepted_correct, "accepted_incorrect": accepted_incorrect,
        "flagged_incorrect": flagged_incorrect, "flagged_correct": flagged_correct,
        "speakers_any": len(by_speaker),
        "speakers_5plus": sum(1 for v in by_speaker.values() if v >= 5),
        "speakers_with_incorrect": len({s for s, f in zip(speakers, flag) if f}),
        "speakers_with_acceptable": len({s for s, a in zip(speakers, accept) if a}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    from sklearn.metrics import average_precision_score, roc_auc_score

    rows = [r for r in csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8"))
            if r["split"] in ("train", "dev")]
    if any(r["split"] == "test" for r in rows):
        sys.exit("TEST LOCK VIOLATION")
    cache = dict(np.load(CACHE, allow_pickle=True))
    if "test" in set(cache["split"].tolist()):
        sys.exit("TEST LOCK VIOLATION in cache")
    stored = np.load(TRAJ_CACHE, allow_pickle=True)
    order = {t: i for i, t in enumerate(cache["token_ids"].tolist())}
    rows = sorted(rows, key=lambda r: order[r["token_id"]])

    trajectory = normalise(stored["learner"], "N2")
    status = list(stored["status"])
    available_all = np.asarray([s.startswith("ok") for s in status])

    split = cache["split"]
    train_mask, dev_mask = split == "train", split == "dev"
    tones, y, speakers = cache["tone"], cache["y"], cache["speaker"]

    print(f"TRAIN {int(train_mask.sum())} tokens / "
          f"{len(set(speakers[train_mask].tolist()))} speakers; R2 frozen "
          f"(C={C_VALUE}, {CLASS_WEIGHT})")
    raw, calibrated, fold_id = cross_fitted(trajectory[train_mask], tones[train_mask],
                                            y[train_mask], speakers[train_mask],
                                            args.seed)
    train_y = y[train_mask]
    train_tones, train_speakers = tones[train_mask], speakers[train_mask]
    train_available = available_all[train_mask]
    print(f"  trajectory available in Train: {int(train_available.sum())}/"
          f"{len(train_available)} ({int((~train_available).sum())} route to RETRY)")

    calibration = [calibration_report(train_y, raw, "CAL0_raw"),
                   calibration_report(train_y, calibrated, "CAL1_sigmoid")]
    with CALIB_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[k for k in calibration[0]
                                                    if k != "bins"])
        writer.writeheader()
        for entry in calibration:
            writer.writerow({k: v for k, v in entry.items() if k != "bins"})

    within = {}
    for label, scores in (("CAL0_raw", raw), ("CAL1_sigmoid", calibrated)):
        values = [roc_auc_score(train_y[fold_id == k], scores[fold_id == k])
                  for k in range(1, N_FOLDS + 1)
                  if train_y[fold_id == k].sum() and (train_y[fold_id == k] == 0).sum()]
        within[label] = {"mean": float(np.mean(values)),
                         "per_fold": [float(v) for v in values]}
    print("\ncalibration:")
    for entry in calibration:
        print(f"  {entry['which']:<14}Brier {entry['brier']:.4f}  "
              f"logloss {entry['log_loss']:.4f}  slope {entry['calibration_slope']:+.3f}  "
              f"meanP {entry['mean_predicted']:.3f} vs prev {entry['observed_prevalence']:.3f}  "
              f"pooledROC {entry['pooled_roc']:.3f}  withinROC {within[entry['which']]['mean']:.3f}")

    # Choose the scoring mode by whether calibration preserved pooled ranking.
    use_calibrated = calibration[1]["pooled_roc"] >= calibration[0]["pooled_roc"] - 0.01
    score = calibrated if use_calibrated else raw
    mode = "calibrated_probability" if use_calibrated else "raw_ranking_score"
    print(f"\nscoring mode for the policy: {mode}"
          + ("" if use_calibrated else
             "  (calibration degraded pooled ranking; raw score used for RANKING "
             "only and must never be shown as a percentage)"))

    # --- binary operating curve --------------------------------------------
    grid = (np.round(np.arange(0.05, 0.96, 0.05), 2) if use_calibrated
            else np.round(np.quantile(score, np.linspace(0.05, 0.95, 19)), 4))
    curve = []
    for threshold in grid:
        predicted = (score >= threshold).astype(int)
        flagged = predicted == 1
        correct, incorrect = train_y == 0, train_y == 1
        curve.append({
            "threshold": float(threshold),
            "incorrect_precision": float(train_y[flagged].mean()) if flagged.any() else float("nan"),
            "incorrect_recall": float(predicted[incorrect].mean()),
            "incorrect_f1": float(2 * train_y[flagged].mean() * predicted[incorrect].mean()
                                  / max(train_y[flagged].mean() + predicted[incorrect].mean(), 1e-9))
            if flagged.any() else 0.0,
            "false_rejection_rate": float(predicted[correct].mean()),
            "false_acceptance_rate": float(1 - predicted[incorrect].mean()),
            "balanced_accuracy": float(0.5 * (predicted[incorrect].mean()
                                              + 1 - predicted[correct].mean())),
            "n_flagged": int(flagged.sum()),
            "pct_flagged": float(flagged.mean() * 100),
        })
    with CURVE_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(curve[0].keys()))
        writer.writeheader()
        writer.writerows(curve)

    # --- policy grid --------------------------------------------------------
    low = np.quantile(score, np.linspace(0.02, 0.60, 30))
    high = np.quantile(score, np.linspace(0.40, 0.995, 40))
    combos = []
    for t_accept in np.round(low, 5):
        for t_incorrect in np.round(high, 5):
            if t_incorrect <= t_accept:
                continue
            for t2_safe in (False, True):
                combos.append(evaluate_policy(train_y, score, train_tones,
                                              train_speakers, train_available,
                                              t_accept, t_incorrect, t2_safe))
    with COVERAGE_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(combos[0].keys()))
        writer.writeheader()
        writer.writerows(combos)
    print(f"policy grid: {len(combos)} combinations")

    # --- barriers -----------------------------------------------------------
    def best_at(precision_key, target, count_key):
        pool = [c for c in combos if np.isfinite(c[precision_key])
                and c[precision_key] >= target and c[count_key] >= MIN_DECISIONS]
        return max(pool, key=lambda c: c[count_key]) if pool else None

    incorrect_points = {f"{t:.2f}": best_at("incorrect_precision", t, "n_incorrect")
                        for t in (0.60, 0.70, 0.80, 0.90)}
    accept_points = {f"{t:.3f}": best_at("acceptable_precision", t, "n_acceptable")
                     for t in (0.90, 0.95, 0.975)}
    crossed_incorrect = incorrect_points["0.60"] is not None
    crossed_accept = accept_points["0.900"] is not None
    c4_bar = best_at("incorrect_precision", C4_ORIGINAL_INCORRECT_PRECISION, "n_incorrect")

    print(f"\nC4 barrier crossing:")
    print(f"  Incorrect precision >=0.60 reachable: {crossed_incorrect}")
    print(f"  Incorrect precision >=0.50 (C4's own bar) reachable: {c4_bar is not None}")
    print(f"  Acceptable precision >=0.90 reachable: {crossed_accept}")
    for target, entry in incorrect_points.items():
        if entry:
            print(f"    IncPrec>={target}: n={entry['n_incorrect']} "
                  f"({entry['n_incorrect'] / entry['n'] * 100:.1f}% of tokens), "
                  f"prec {entry['incorrect_precision']:.3f}, "
                  f"recall {entry['incorrect_recall']:.3f}, "
                  f"{entry['speakers_with_incorrect']} speakers")
    for target, entry in accept_points.items():
        if entry:
            print(f"    AccPrec>={target}: n={entry['n_acceptable']} "
                  f"({entry['n_acceptable'] / entry['n'] * 100:.1f}%), "
                  f"prec {entry['acceptable_precision']:.3f}, "
                  f"{entry['speakers_with_acceptable']} speakers")

    frontier = {}
    for target in (0.25, 0.50, 0.75, 0.90):
        pool = [c for c in combos if not c["t2_safe"]
                and abs(c["coverage"] - target) <= 0.03]
        if pool:
            frontier[f"{int(target * 100)}%"] = min(pool, key=lambda c: c["selective_error"])
    print("\ncoverage-risk frontier:")
    for name, entry in frontier.items():
        print(f"  ~{name:<5} cov {entry['coverage'] * 100:5.1f}%  selErr "
              f"{entry['selective_error'] * 100:5.1f}%  AccPrec "
              f"{entry['acceptable_precision']:.3f} (n={entry['n_acceptable']})  "
              f"IncPrec {entry['incorrect_precision'] if np.isfinite(entry['incorrect_precision']) else float('nan'):.3f} "
              f"(n={entry['n_incorrect']})")

    # --- admission ----------------------------------------------------------
    def admissible(entry):
        return (np.isfinite(entry["incorrect_precision"])
                and entry["incorrect_precision"] >= MIN_INCORRECT_PRECISION
                and np.isfinite(entry["acceptable_precision"])
                and entry["acceptable_precision"] >= MIN_ACCEPTABLE_PRECISION
                and entry["n_incorrect"] >= MIN_DECISIONS
                and entry["n_acceptable"] >= MIN_DECISIONS)

    viable_g = [c for c in combos if not c["t2_safe"] and admissible(c)]
    viable_t2 = [c for c in combos if c["t2_safe"] and admissible(c)]
    print(f"\nadmissible (IncPrec>={MIN_INCORRECT_PRECISION}, "
          f"AccPrec>={MIN_ACCEPTABLE_PRECISION}, >={MIN_DECISIONS} each):")
    print(f"  POLICY G      : {len(viable_g)}")
    print(f"  POLICY T2SAFE : {len(viable_t2)}")

    chosen = None
    if viable_g or viable_t2:
        chosen = max(viable_g or viable_t2, key=lambda c: c["coverage"])

    # --- error confidence ---------------------------------------------------
    accept, flag, uncertain = policy_outcome(
        score, train_tones, train_available,
        chosen["t_accept"] if chosen else np.quantile(score, 0.3),
        chosen["t_incorrect"] if chosen else np.quantile(score, 0.9),
        chosen["t2_safe"] if chosen else False)
    automatic = accept | flag
    wrong = (accept & (train_y == 1)) | (flag & (train_y == 0))
    midpoint = float(np.median(score))
    confidence = {
        "median_abs_dev_correct_decisions": float(np.median(
            np.abs(score[automatic & ~wrong] - midpoint))) if (automatic & ~wrong).any() else None,
        "median_abs_dev_wrong_decisions": float(np.median(
            np.abs(score[automatic & wrong] - midpoint))) if (automatic & wrong).any() else None,
        "median_abs_dev_uncertain": float(np.median(
            np.abs(score[uncertain] - midpoint))) if uncertain.any() else None,
        "note": "reference operating point used when no policy was admissible",
    }

    per_tone = {}
    for tone in TONES:
        mask = train_tones == tone
        per_tone[f"T{tone}"] = evaluate_policy(
            train_y[mask], score[mask], train_tones[mask], train_speakers[mask],
            train_available[mask],
            chosen["t_accept"] if chosen else np.quantile(score, 0.3),
            chosen["t_incorrect"] if chosen else np.quantile(score, 0.9),
            chosen["t2_safe"] if chosen else False)

    with OOF_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["token_id", "speaker_id", "expected_tone", "tone_correctness",
                         "trajectory_available", "raw_score", "calibrated_p"])
        train_rows = [r for r, m in zip(rows, train_mask) if m]
        for row, ok, raw_score, probability in zip(train_rows, train_available,
                                                   raw, calibrated):
            writer.writerow([row["token_id"], row["speaker_id"], row["expected_tone"],
                             row["tone_correctness"], int(ok),
                             f"{raw_score:.6f}", f"{probability:.6f}"])

    summary = {
        "representation": "R2 frozen (20-pt median-centred semitone trajectory)",
        "scoring_mode": mode, "use_calibrated": bool(use_calibrated),
        "calibration": calibration, "within_fold_roc": within,
        "trajectory_available_train": int(train_available.sum()),
        "trajectory_unavailable_train": int((~train_available).sum()),
        "binary_curve": curve, "frontier": frontier,
        "incorrect_points": incorrect_points, "accept_points": accept_points,
        "crossed_incorrect_060": crossed_incorrect,
        "crossed_incorrect_050_c4_bar": c4_bar is not None,
        "crossed_acceptable_090": crossed_accept,
        "n_admissible_global": len(viable_g), "n_admissible_t2safe": len(viable_t2),
        "chosen_policy": chosen, "per_tone_reference": per_tone,
        "error_confidence": confidence,
        "admission_rule": {"min_incorrect_precision": MIN_INCORRECT_PRECISION,
                           "c4_original_bar": C4_ORIGINAL_INCORRECT_PRECISION,
                           "min_acceptable_precision": MIN_ACCEPTABLE_PRECISION,
                           "min_decisions": MIN_DECISIONS},
        "test_lock": {"trajectories": False, "features": False, "calibration": False,
                      "predictions": False, "metrics": False},
    }
    if chosen:
        payload = {**summary, "seed": args.seed,
                   "software": {"python": platform.python_version(),
                                "numpy": np.__version__}}
        payload["sha256"] = hashlib.sha256(
            json.dumps({k: v for k, v in payload.items() if k != "binary_curve"},
                       sort_keys=True, default=float).encode()).hexdigest()
        POLICY.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=float),
                          encoding="utf-8")
        print(f"\nFROZEN POLICY: t_accept={chosen['t_accept']:.4f} "
              f"t_incorrect={chosen['t_incorrect']:.4f} T2safe={chosen['t2_safe']}")
    else:
        print("\nNO ADMISSIBLE POLICY. Dev NOT opened; nothing frozen.")

    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=float),
                       encoding="utf-8")
    print(f"\nfiles: {CALIB_CSV.name}, {CURVE_CSV.name}, {COVERAGE_CSV.name}, "
          f"{OOF_CSV.name}, {SUMMARY.name}")


if __name__ == "__main__":
    main()
