"""Phase C4 — calibration and a selective ACCEPTABLE / RETRY / INCORRECT policy.

The acoustic model is frozen. The question is no longer "which threshold gives
the best F1" but "is there a subset of attempts where automated feedback is
substantially safer than a forced binary verdict, and how much coverage does
that safety cost".

UNCERTAIN is abstention, not an error class. The scientific benchmark stays
binary.

Everything is developed on Train with nested speaker-grouped cross-fitting, so
no speaker's own label ever helps fit the model or the calibrator that scores
it. Dev is opened once, after the policy is frozen. Test is untouched.

    python -m pronunciation.wav2vec_tone.phase_c4_selective_policy
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
    PRAAT_FEATURES, TONES, apply_fold, design, fit_fold,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
CALIB_CSV = DATA_DIR / "ompal_phase_c4_calibration_results.csv"
COVERAGE_CSV = DATA_DIR / "ompal_phase_c4_coverage_risk.csv"
OOF_CSV = DATA_DIR / "ompal_phase_c4_train_oof_selective_predictions.csv"
DEV_JSON = DATA_DIR / "ompal_phase_c4_dev_confirmation.json"
POLICY = DATA_DIR / "ompal_phase_c4_policy_FROZEN.json"
REPORT = REPORTS_DIR / "ompal_phase_c4_selective_policy.md"

MODEL = {"kind": "P1", "class_weight": "balanced", "C": 10.0}
SEED = 0
OUTER_FOLDS, INNER_FOLDS = 5, 4

# Pre-specified acceptance rule, fixed before any coverage number was seen.
# A flagged token must be more likely wrong than right, or the feedback is not
# defensible; an accepted token must be right at least 90% of the time, which
# is above the 83.1% base rate so acceptance must actually add information.
MIN_INCORRECT_PRECISION = 0.50
MIN_ACCEPTABLE_PRECISION = 0.90
MIN_DECISIONS_PER_CATEGORY = 10
MIN_SPEAKERS_WITH_DECISION = 20


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def cross_fitted_scores(features, tones, y, speakers, seed):
    """Raw and calibrated OOF probabilities, both speaker-leakage-free.

    Architecture, exactly as specified: for each outer fold a SINGLE base model
    is fitted on the outer-training speakers, and a SINGLE sigmoid is fitted on
    inner speaker-grouped out-of-fold scores from those same speakers. The
    outer speakers touch neither.

    Using sklearn's CalibratedClassifierCV here would instead average k inner
    *models*, so its output is not a monotone transform of the outer model's
    score -- measured on this data it moved ROC from 0.586 to 0.428, i.e. the
    ensemble inverted at this signal level. A single monotone calibrator keeps
    the ranking intact, which is what calibration is supposed to do.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold

    raw = np.zeros(len(y))
    calibrated = np.zeros(len(y))
    outer = GroupKFold(n_splits=OUTER_FOLDS)

    for train_index, test_index in outer.split(np.zeros(len(y)), groups=speakers):
        # Inner OOF scores, used only to learn the probability mapping.
        inner_scores = np.zeros(len(train_index))
        inner_speakers = speakers[train_index]
        for inner_train, inner_test in GroupKFold(n_splits=INNER_FOLDS).split(
                np.zeros(len(train_index)), groups=inner_speakers):
            absolute_train = train_index[inner_train]
            absolute_test = train_index[inner_test]
            inner_state = fit_fold(MODEL["kind"], features[absolute_train],
                                   tones[absolute_train], y[absolute_train],
                                   MODEL["class_weight"], MODEL["C"], seed)
            inner_scores[inner_test] = apply_fold(inner_state,
                                                  features[absolute_test],
                                                  tones[absolute_test])
        sigmoid = LogisticRegression(max_iter=2000).fit(
            logit(inner_scores).reshape(-1, 1), y[train_index])

        state = fit_fold(MODEL["kind"], features[train_index], tones[train_index],
                         y[train_index], MODEL["class_weight"], MODEL["C"], seed)
        outer_raw = apply_fold(state, features[test_index], tones[test_index])
        raw[test_index] = outer_raw
        calibrated[test_index] = sigmoid.predict_proba(
            logit(outer_raw).reshape(-1, 1))[:, 1]
    return raw, calibrated


def calibration_report(y, scores, label) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

    slope_model = LogisticRegression(max_iter=2000).fit(logit(scores).reshape(-1, 1), y)
    edges = np.quantile(scores, np.linspace(0, 1, 9))
    edges[-1] += 1e-9
    bins = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (scores >= low) & (scores < high)
        if mask.sum():
            bins.append({"n": int(mask.sum()),
                         "mean_predicted": float(scores[mask].mean()),
                         "observed": float(y[mask].mean())})
    return {
        "which": label,
        "brier": float(brier_score_loss(y, scores)),
        "log_loss": float(log_loss(y, scores, labels=[0, 1])),
        "calibration_slope": float(slope_model.coef_[0][0]),
        "calibration_intercept": float(slope_model.intercept_[0]),
        "mean_predicted": float(scores.mean()),
        "observed_prevalence": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, scores)),
        "bins": bins,
    }


def binary_curve(y, scores) -> list[dict]:
    rows = []
    for threshold in np.round(np.arange(0.05, 0.96, 0.05), 2):
        predicted = (scores >= threshold).astype(int)
        correct, incorrect = y == 0, y == 1
        flagged = predicted == 1
        rows.append({
            "threshold": float(threshold),
            "incorrect_precision": float(y[flagged].mean()) if flagged.any() else float("nan"),
            "incorrect_recall": float(predicted[incorrect].mean()),
            "incorrect_f1": float(2 * predicted[incorrect].mean() * (y[flagged].mean() if flagged.any() else 0)
                                  / max(predicted[incorrect].mean() + (y[flagged].mean() if flagged.any() else 0), 1e-9)),
            "correct_specificity": float(1 - predicted[correct].mean()),
            "false_rejection_rate": float(predicted[correct].mean()),
            "false_acceptance_rate": float(1 - predicted[incorrect].mean()),
            "balanced_accuracy": float(0.5 * (predicted[incorrect].mean()
                                              + (1 - predicted[correct].mean()))),
            "pct_predicted_incorrect": float(flagged.mean() * 100),
            "pct_predicted_correct": float((~flagged).mean() * 100),
        })
    return rows


def evaluate_policy(y, scores, tones, speakers, t_accept, t_incorrect,
                    t2_safe=False) -> dict:
    """Three-way outcome. UNCERTAIN is abstention and never counted as error."""
    accept = scores <= t_accept
    flag = scores >= t_incorrect
    if t2_safe:
        # T2 has no demonstrated discrimination, so no automatic Incorrect
        # verdict may be issued for it; those cases become RETRY.
        flag = flag & (tones != "2")
    uncertain = ~(accept | flag)

    automatic = accept | flag
    accepted_correct = int((accept & (y == 0)).sum())
    accepted_incorrect = int((accept & (y == 1)).sum())
    flagged_incorrect = int((flag & (y == 1)).sum())
    flagged_correct = int((flag & (y == 0)).sum())
    errors = accepted_incorrect + flagged_correct

    return {
        "t_accept": float(t_accept), "t_incorrect": float(t_incorrect),
        "t2_safe": bool(t2_safe),
        "n": int(len(y)),
        "n_acceptable": int(accept.sum()), "n_uncertain": int(uncertain.sum()),
        "n_incorrect": int(flag.sum()),
        "coverage": float(automatic.mean()),
        "abstention_rate": float(uncertain.mean()),
        "acceptable_precision": (accepted_correct / accept.sum()) if accept.sum() else float("nan"),
        "accepted_correct": accepted_correct, "accepted_incorrect": accepted_incorrect,
        "incorrect_precision": (flagged_incorrect / flag.sum()) if flag.sum() else float("nan"),
        "flagged_incorrect": flagged_incorrect, "flagged_correct": flagged_correct,
        "incorrect_recall_of_all": float(flagged_incorrect / max((y == 1).sum(), 1)),
        "selective_error": (errors / automatic.sum()) if automatic.sum() else float("nan"),
        "false_acceptance_among_accepted": (accepted_incorrect / accept.sum()) if accept.sum() else float("nan"),
        "false_rejection_among_flagged": (flagged_correct / flag.sum()) if flag.sum() else float("nan"),
        "speakers_with_any_decision": len({s for s, a in zip(speakers, automatic) if a}),
        "speakers_with_5plus": sum(1 for _, count in
                                   Counter(s for s, a in zip(speakers, automatic) if a).items()
                                   if count >= 5),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    rows = [r for r in csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8"))
            if r["split"] in ("train", "dev")]
    if any(r["split"] == "test" for r in rows):
        sys.exit("TEST LOCK VIOLATION")
    cache = dict(np.load(CACHE, allow_pickle=True))
    if "test" in set(cache["split"].tolist()):
        sys.exit("TEST LOCK VIOLATION in cache")
    order = {t: i for i, t in enumerate(cache["token_ids"].tolist())}
    rows = sorted(rows, key=lambda r: order[r["token_id"]])

    split = cache["split"]
    train_mask, dev_mask = split == "train", split == "dev"
    features, tones, y = cache["praat"], cache["tone"], cache["y"]
    speakers = cache["speaker"]

    print(f"TRAIN: {int(train_mask.sum())} tokens, "
          f"{len(set(speakers[train_mask].tolist()))} speakers, "
          f"{int(y[train_mask].sum())} Incorrect")
    print("cross-fitting: outer GroupKFold(5) by speaker, inner GroupKFold(4) "
          "for sigmoid calibration")

    raw, calibrated = cross_fitted_scores(features[train_mask], tones[train_mask],
                                          y[train_mask], speakers[train_mask],
                                          args.seed)
    train_y = y[train_mask]
    train_tones, train_speakers = tones[train_mask], speakers[train_mask]

    calibration = [calibration_report(train_y, raw, "raw_P1"),
                   calibration_report(train_y, calibrated, "calibrated_sigmoid")]
    with CALIB_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[k for k in calibration[0]
                                                    if k != "bins"])
        writer.writeheader()
        for entry in calibration:
            writer.writerow({k: v for k, v in entry.items() if k != "bins"})
    print("\ncalibration (Train OOF):")
    for entry in calibration:
        print(f"  {entry['which']:<20}Brier {entry['brier']:.4f}  "
              f"logloss {entry['log_loss']:.4f}  slope {entry['calibration_slope']:.3f}  "
              f"intercept {entry['calibration_intercept']:+.3f}  "
              f"meanP {entry['mean_predicted']:.3f} vs prev {entry['observed_prevalence']:.3f}  "
              f"ROC {entry['roc_auc']:.3f}")

    curve = binary_curve(train_y, calibrated)

    # --- three-way policy grid ---------------------------------------------
    grid = []
    accept_grid = np.round(np.arange(0.02, 0.31, 0.01), 3)
    flag_grid = np.round(np.arange(0.20, 0.86, 0.01), 3)
    for t_accept in accept_grid:
        for t_incorrect in flag_grid:
            if t_incorrect <= t_accept:
                continue
            for t2_safe in (False, True):
                grid.append(evaluate_policy(train_y, calibrated, train_tones,
                                            train_speakers, t_accept,
                                            t_incorrect, t2_safe))
    with COVERAGE_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(grid[0].keys()))
        writer.writeheader()
        writer.writerows(grid)

    print(f"\npolicy grid: {len(grid)} (t_accept, t_incorrect, T2 mode) combinations")

    # --- coverage-risk frontier --------------------------------------------
    frontier = {}
    for target in (0.25, 0.50, 0.75, 0.90):
        candidates = [g for g in grid if not g["t2_safe"]
                      and abs(g["coverage"] - target) <= 0.03]
        if candidates:
            frontier[f"{int(target * 100)}%"] = min(
                candidates, key=lambda g: g["selective_error"])
    print("\ncoverage-risk frontier (global policy):")
    for name, entry in frontier.items():
        print(f"  ~{name:<5} coverage {entry['coverage'] * 100:5.1f}%  "
              f"selective error {entry['selective_error'] * 100:5.1f}%  "
              f"IncPrec {entry['incorrect_precision']:.3f} (n={entry['n_incorrect']})  "
              f"AccPrec {entry['acceptable_precision']:.3f} (n={entry['n_acceptable']})")

    # --- high-precision incorrect feedback ---------------------------------
    precision_points = {}
    for target in (0.60, 0.70, 0.80, 0.90):
        candidates = [c for c in curve
                      if np.isfinite(c["incorrect_precision"])
                      and c["incorrect_precision"] >= target]
        if candidates:
            best = max(candidates, key=lambda c: c["pct_predicted_incorrect"])
            precision_points[f"{target:.2f}"] = best
    print("\nhigh-precision Incorrect operating points (binary, Train OOF):")
    if not precision_points:
        print("  none reachable at any threshold")
    for target, entry in precision_points.items():
        print(f"  precision>={target}: thr {entry['threshold']:.2f}  "
              f"prec {entry['incorrect_precision']:.3f}  "
              f"recall {entry['incorrect_recall']:.3f}  "
              f"flagged {entry['pct_predicted_incorrect']:.1f}% of tokens")

    # --- safe acceptance ---------------------------------------------------
    accept_points = {}
    for target in (0.90, 0.95, 0.975):
        candidates = [g for g in grid if not g["t2_safe"] and g["n_acceptable"] >= 20
                      and np.isfinite(g["acceptable_precision"])
                      and g["acceptable_precision"] >= target]
        if candidates:
            accept_points[f"{target:.3f}"] = max(
                candidates, key=lambda g: g["n_acceptable"])
    print("\nsafe-acceptance operating points:")
    if not accept_points:
        print("  none reachable with >=20 accepted tokens")
    for target, entry in accept_points.items():
        print(f"  accept precision>={target}: t_accept {entry['t_accept']:.2f}  "
              f"prec {entry['acceptable_precision']:.3f}  "
              f"accepted {entry['n_acceptable']} "
              f"({entry['n_acceptable'] / entry['n'] * 100:.1f}% of tokens)  "
              f"missed Incorrect {entry['accepted_incorrect']}")

    # --- policy selection under the pre-specified rule ----------------------
    def admissible(entry):
        return (np.isfinite(entry["incorrect_precision"])
                and entry["incorrect_precision"] >= MIN_INCORRECT_PRECISION
                and np.isfinite(entry["acceptable_precision"])
                and entry["acceptable_precision"] >= MIN_ACCEPTABLE_PRECISION
                and entry["n_incorrect"] >= MIN_DECISIONS_PER_CATEGORY
                and entry["n_acceptable"] >= MIN_DECISIONS_PER_CATEGORY
                and entry["speakers_with_any_decision"] >= MIN_SPEAKERS_WITH_DECISION)

    viable_global = [g for g in grid if not g["t2_safe"] and admissible(g)]
    viable_t2safe = [g for g in grid if g["t2_safe"] and admissible(g)]
    print(f"\nadmissible policies (IncPrec>={MIN_INCORRECT_PRECISION}, "
          f"AccPrec>={MIN_ACCEPTABLE_PRECISION}, >={MIN_DECISIONS_PER_CATEGORY} per "
          f"category, >={MIN_SPEAKERS_WITH_DECISION} speakers):")
    print(f"  POLICY G (global) : {len(viable_global)}")
    print(f"  POLICY T (T2-safe): {len(viable_t2safe)}")

    chosen = None
    if viable_global or viable_t2safe:
        pool = viable_t2safe if viable_t2safe else viable_global
        chosen = max(pool, key=lambda g: g["coverage"])

    tone_coverage = per_group(train_y, calibrated, train_tones, chosen, "tone") if chosen else {}
    speaker_coverage = per_group(train_y, calibrated, train_speakers, chosen, "speaker") if chosen else {}
    concentration = error_concentration(train_y, calibrated, chosen) if chosen else {}

    with OOF_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["token_id", "speaker_id", "expected_tone",
                         "tone_correctness", "raw_score", "calibrated_p_incorrect",
                         "decision"])
        train_rows = [r for r in rows if r["split"] == "train"]
        for row, raw_score, probability in zip(train_rows, raw, calibrated):
            decision = ""
            if chosen:
                decision = decide(probability, row["expected_tone"], chosen)
            writer.writerow([row["token_id"], row["speaker_id"],
                             row["expected_tone"], row["tone_correctness"],
                             f"{raw_score:.6f}", f"{probability:.6f}", decision])

    dev = None
    frozen = None
    if chosen:
        frozen = freeze(chosen, calibration, frontier, args.seed)
        dev = confirm_dev(chosen, cache, train_mask, dev_mask, rows, args.seed)
        DEV_JSON.write_text(json.dumps(dev, indent=2, ensure_ascii=False, default=float),
                            encoding="utf-8")
        print(f"\nFROZEN POLICY: t_accept={chosen['t_accept']:.2f} "
              f"t_incorrect={chosen['t_incorrect']:.2f} T2-safe={chosen['t2_safe']}")
        print(f"  Train coverage {chosen['coverage'] * 100:.1f}%  "
              f"selective error {chosen['selective_error'] * 100:.1f}%")
        print("\n--- one-time Dev confirmation ---")
        for key in ("coverage", "abstention_rate", "acceptable_precision",
                    "incorrect_precision", "selective_error"):
            print(f"  {key:<26}{dev['overall'][key]:.4f}")
        print(f"  counts: acceptable {dev['overall']['n_acceptable']}, "
              f"uncertain {dev['overall']['n_uncertain']}, "
              f"incorrect {dev['overall']['n_incorrect']}")
    else:
        print("\nNO ADMISSIBLE POLICY under the pre-specified rule. "
              "Dev was NOT opened.")

    payload = {"calibration": calibration, "frontier": frontier,
               "precision_points": precision_points, "accept_points": accept_points,
               "n_admissible_global": len(viable_global),
               "n_admissible_t2safe": len(viable_t2safe),
               "chosen": chosen, "tone_coverage": tone_coverage,
               "speaker_coverage": speaker_coverage,
               "error_concentration": concentration,
               "binary_curve": curve, "dev": dev}
    (DATA_DIR / "ompal_phase_c4_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=float),
        encoding="utf-8")
    print(f"\nfiles: {CALIB_CSV.name}, {COVERAGE_CSV.name}, {OOF_CSV.name}"
          + (f", {DEV_JSON.name}, {POLICY.name}" if chosen else ""))


def decide(probability, tone, policy) -> str:
    if probability <= policy["t_accept"]:
        return "ACCEPTABLE"
    if probability >= policy["t_incorrect"] and not (policy["t2_safe"] and tone == "2"):
        return "INCORRECT"
    return "UNCERTAIN"


def per_group(y, scores, groups, policy, label) -> dict:
    out = {}
    for value in sorted(set(groups.tolist())):
        mask = groups == value
        decisions = np.asarray([decide(p, t, policy) for p, t in
                                zip(scores[mask], groups[mask] if label == "tone"
                                    else np.full(mask.sum(), "x"))])
        automatic = decisions != "UNCERTAIN"
        errors = sum(1 for d, label_value in zip(decisions, y[mask])
                     if (d == "ACCEPTABLE" and label_value == 1)
                     or (d == "INCORRECT" and label_value == 0))
        out[str(value)] = {
            "n": int(mask.sum()), "automatic": int(automatic.sum()),
            "abstained": int((~automatic).sum()),
            "coverage": float(automatic.mean()),
            "selective_error": float(errors / automatic.sum()) if automatic.sum() else None,
        }
    return out


def error_concentration(y, scores, policy) -> dict:
    decisions = np.asarray([decide(p, "x", policy) for p in scores])
    automatic = decisions != "UNCERTAIN"
    wrong = np.asarray([(d == "ACCEPTABLE" and t == 1) or (d == "INCORRECT" and t == 0)
                        for d, t in zip(decisions, y)])
    return {
        "median_confidence_correct_decisions": float(np.median(
            np.abs(scores[automatic & ~wrong] - 0.5))) if (automatic & ~wrong).any() else None,
        "median_confidence_wrong_decisions": float(np.median(
            np.abs(scores[automatic & wrong] - 0.5))) if (automatic & wrong).any() else None,
        "median_confidence_abstained": float(np.median(
            np.abs(scores[~automatic] - 0.5))) if (~automatic).any() else None,
        "error_rate_automatic": float(wrong[automatic].mean()) if automatic.any() else None,
        "error_rate_if_abstained_were_forced": float(
            np.mean([(p >= 0.5) != (t == 1) for p, t in
                     zip(scores[~automatic], y[~automatic])])) if (~automatic).any() else None,
    }


def confirm_dev(policy, cache, train_mask, dev_mask, rows, seed) -> dict:
    """Same architecture as development: one base model, one sigmoid, fitted on
    Train with inner speaker-grouped OOF scores. Dev touches neither."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold

    features, tones, y = cache["praat"], cache["tone"], cache["y"]
    speakers = cache["speaker"]
    train_index = np.flatnonzero(train_mask)

    inner_scores = np.zeros(len(train_index))
    for inner_train, inner_test in GroupKFold(n_splits=INNER_FOLDS).split(
            np.zeros(len(train_index)), groups=speakers[train_index]):
        absolute_train, absolute_test = train_index[inner_train], train_index[inner_test]
        state = fit_fold(MODEL["kind"], features[absolute_train], tones[absolute_train],
                         y[absolute_train], MODEL["class_weight"], MODEL["C"], seed)
        inner_scores[inner_test] = apply_fold(state, features[absolute_test],
                                              tones[absolute_test])
    sigmoid = LogisticRegression(max_iter=2000).fit(
        logit(inner_scores).reshape(-1, 1), y[train_index])

    state = fit_fold(MODEL["kind"], features[train_mask], tones[train_mask],
                     y[train_mask], MODEL["class_weight"], MODEL["C"], seed)
    dev_raw = apply_fold(state, features[dev_mask], tones[dev_mask])
    probabilities = sigmoid.predict_proba(logit(dev_raw).reshape(-1, 1))[:, 1]

    dev_y, dev_tones, dev_speakers = y[dev_mask], tones[dev_mask], speakers[dev_mask]
    overall = evaluate_policy(dev_y, probabilities, dev_tones, dev_speakers,
                              policy["t_accept"], policy["t_incorrect"],
                              policy["t2_safe"])
    by_tone, by_speaker = {}, {}
    for tone in TONES:
        mask = dev_tones == tone
        if mask.sum():
            by_tone[f"T{tone}"] = evaluate_policy(
                dev_y[mask], probabilities[mask], dev_tones[mask],
                dev_speakers[mask], policy["t_accept"], policy["t_incorrect"],
                policy["t2_safe"])
    for speaker in sorted(set(dev_speakers.tolist())):
        mask = dev_speakers == speaker
        by_speaker[speaker] = evaluate_policy(
            dev_y[mask], probabilities[mask], dev_tones[mask], dev_speakers[mask],
            policy["t_accept"], policy["t_incorrect"], policy["t2_safe"])
    return {"policy": policy, "overall": overall, "by_tone": by_tone,
            "by_speaker": by_speaker, "opened_once": True}


def freeze(policy, calibration, frontier, seed) -> dict:
    import sklearn
    base_hash = hashlib.sha256(json.dumps(
        {"model": MODEL, "features": list(PRAAT_FEATURES)},
        sort_keys=True).encode()).hexdigest()
    payload = {
        "phase": "C4",
        "base_model": MODEL, "base_model_hash": base_hash,
        "praat_features": list(PRAAT_FEATURES),
        "calibration_method": ("sigmoid (Platt), nested speaker-grouped: outer "
                               "GroupKFold(5), inner GroupKFold(4) within outer "
                               "training speakers"),
        "t_accept": policy["t_accept"], "t_incorrect": policy["t_incorrect"],
        "t2_policy": ("automatic INCORRECT verdict disabled for expected T2; "
                      "such cases route to UNCERTAIN"
                      if policy["t2_safe"] else "same thresholds for all tones"),
        "selection_rule": {
            "min_incorrect_precision": MIN_INCORRECT_PRECISION,
            "min_acceptable_precision": MIN_ACCEPTABLE_PRECISION,
            "min_decisions_per_category": MIN_DECISIONS_PER_CATEGORY,
            "min_speakers_with_decision": MIN_SPEAKERS_WITH_DECISION,
            "objective": "maximise coverage subject to the above",
            "fixed_before_results": True,
        },
        "train_oof_expected": {k: policy[k] for k in
                               ("coverage", "abstention_rate", "selective_error",
                                "acceptable_precision", "incorrect_precision",
                                "n_acceptable", "n_uncertain", "n_incorrect",
                                "speakers_with_any_decision")},
        "calibration_quality": {c["which"]: {k: c[k] for k in
                                             ("brier", "log_loss",
                                              "calibration_slope",
                                              "calibration_intercept")}
                                for c in calibration},
        "random_seed": seed,
        "software": {"python": platform.python_version(), "numpy": np.__version__,
                     "scikit_learn": sklearn.__version__},
        "feedback_constraints": [
            "binary pedagogical claim only: tone appears acceptable / likely "
            "needs another attempt",
            "no produced-tone confusion claims -- OMPAL has no produced-tone labels",
            "raw probability must not be shown to learners",
        ],
        "test_lock": {"features": False, "probabilities": False,
                      "predictions": False, "metrics": False,
                      "error_analysis": False},
    }
    payload["sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=float).encode()).hexdigest()
    POLICY.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=float),
                      encoding="utf-8")
    return payload


if __name__ == "__main__":
    main()
