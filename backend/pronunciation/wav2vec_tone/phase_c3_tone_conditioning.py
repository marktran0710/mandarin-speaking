"""Phase C3 — does structural tone conditioning rescue the Praat signal?

Phase C2 showed the additive formulation cannot represent the target decision:
expected tone entered as a one-hot shifts the intercept but cannot flip the
sign of an acoustic weight, while a falling contour means "correct" for T4 and
"error" for T2. This phase corrects that structurally and asks whether the
signal already in the frozen Praat features becomes usable.

Selection happens inside TRAIN with speaker-grouped CV. Dev was inspected
heavily in Phase C and is opened exactly once here, after the winner is frozen.
Test is not touched at all.

    python -m pronunciation.wav2vec_tone.phase_c3_tone_conditioning
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

DATA_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
CV_CSV = DATA_DIR / "ompal_phase_c3_train_cv_results.csv"
OOF_CSV = DATA_DIR / "ompal_phase_c3_oof_predictions.csv"
DEV_JSON = DATA_DIR / "ompal_phase_c3_dev_confirmation.json"
PROTOCOL = DATA_DIR / "ompal_phase_c3_protocol_FROZEN.json"
REPORT = REPORTS_DIR / "ompal_phase_c3_tone_conditioning.md"

PRAAT_FEATURES = (
    "rel_f0_start", "rel_f0_25", "rel_f0_50", "rel_f0_75", "rel_f0_end",
    "f0_range_st", "slope_start_to_mid", "slope_mid_to_end",
    "duration_seconds", "voiced_proportion",
)
TONES = ("1", "2", "3", "4")
REFERENCE_TONE = "1"          # reference level for non-redundant coding
C_GRID = (0.01, 0.1, 1.0, 10.0)
CLASS_WEIGHTS = (None, "balanced")
N_FOLDS = 5
SEED = 0
SPLIT_ID = "ompal_speaker_split_v1"


# --------------------------------------------------------------------------
# Design matrices. Order of operations is fixed and identical everywhere:
#   1. median-impute continuous features (fold-train statistics)
#   2. standardise continuous features (fold-train statistics)
#   3. build tone dummies -- never standardised
#   4. build interactions from the ALREADY-SCALED base features
# Building interactions before scaling would make each product carry the raw
# scale of its parent, and the single penalty C would then mean something
# different for every interaction column.
# --------------------------------------------------------------------------

def design(kind: str, scaled: np.ndarray, tones: np.ndarray):
    """Return (matrix, column names) for P0 or P1 from already-scaled features."""
    dummies = np.stack([(tones == t).astype(float)
                        for t in TONES if t != REFERENCE_TONE], axis=1)
    dummy_names = [f"tone_T{t}" for t in TONES if t != REFERENCE_TONE]

    if kind == "P0":
        return (np.hstack([scaled, dummies]),
                list(PRAAT_FEATURES) + dummy_names)

    blocks, names = [scaled, dummies], list(PRAAT_FEATURES) + dummy_names
    for position, tone in enumerate([t for t in TONES if t != REFERENCE_TONE]):
        indicator = dummies[:, position:position + 1]
        blocks.append(scaled * indicator)
        names += [f"{f} x T{tone}" for f in PRAAT_FEATURES]
    return np.hstack(blocks), names


def fit_fold(kind, train_features, train_tones, train_y, class_weight, C, seed):
    """Fit imputer, scaler and model on fold-training speakers only."""
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    imputer = SimpleImputer(strategy="median").fit(train_features)
    scaler = StandardScaler().fit(imputer.transform(train_features))
    matrix, names = design(kind, scaler.transform(imputer.transform(train_features)),
                           train_tones)
    model = LogisticRegression(max_iter=5000, C=C, class_weight=class_weight,
                               random_state=seed).fit(matrix, train_y)
    return {"imputer": imputer, "scaler": scaler, "model": model, "names": names,
            "kind": kind}


def apply_fold(state, features, tones):
    scaled = state["scaler"].transform(state["imputer"].transform(features))
    matrix, _ = design(state["kind"], scaled, tones)
    return state["model"].predict_proba(matrix)[:, 1]


def metrics(y_true, scores, threshold=0.5) -> dict:
    from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
                                 brier_score_loss, f1_score, precision_score,
                                 recall_score, roc_auc_score)
    predicted = (scores >= threshold).astype(int)
    correct, incorrect = y_true == 0, y_true == 1
    return {
        "pr_auc_incorrect": float(average_precision_score(y_true, scores)),
        "roc_auc": float(roc_auc_score(y_true, scores)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predicted)),
        "macro_f1": float(f1_score(y_true, predicted, average="macro")),
        "incorrect_precision": float(precision_score(y_true, predicted, zero_division=0)),
        "incorrect_recall": float(recall_score(y_true, predicted, zero_division=0)),
        "incorrect_f1": float(f1_score(y_true, predicted, zero_division=0)),
        "accuracy": float((predicted == y_true).mean()),
        "false_rejection_rate": float(predicted[correct].mean()) if correct.any() else float("nan"),
        "false_acceptance_rate": float(1 - predicted[incorrect].mean()) if incorrect.any() else float("nan"),
        "brier": float(brier_score_loss(y_true, scores)),
        "prevalence": float(y_true.mean()),
    }


def grouped_folds(speakers, n_folds, seed):
    from sklearn.model_selection import GroupKFold
    return list(GroupKFold(n_splits=n_folds).split(np.zeros(len(speakers)),
                                                   groups=speakers))


def run_cv(kind, features, tones, y, speakers, class_weight, C, seed):
    """Speaker-grouped OOF predictions plus per-fold metrics."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    oof = np.zeros(len(y))
    fold_scores = []
    for train_index, validate_index in grouped_folds(speakers, N_FOLDS, seed):
        state = fit_fold(kind, features[train_index], tones[train_index],
                         y[train_index], class_weight, C, seed)
        oof[validate_index] = apply_fold(state, features[validate_index],
                                         tones[validate_index])
        labels = y[validate_index]
        if labels.sum() and (labels == 0).sum():
            fold_scores.append({
                "pr_auc": float(average_precision_score(labels, oof[validate_index])),
                "roc_auc": float(roc_auc_score(labels, oof[validate_index])),
                "n": int(len(labels)), "n_incorrect": int(labels.sum()),
            })
    return oof, fold_scores


def run_p2(features, tones, y, speakers, class_weight, C, seed):
    """Four independent per-tone models; OOF assembled tone by tone."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    oof = np.full(len(y), np.nan)
    support, fold_scores = {}, []
    for tone in TONES:
        selector = np.flatnonzero(tones == tone)
        tone_speakers = speakers[selector]
        tone_y = y[selector]
        n_speakers = len(set(tone_speakers.tolist()))
        support[f"T{tone}"] = {"n": int(len(selector)),
                               "n_incorrect": int(tone_y.sum()),
                               "n_speakers": n_speakers}
        # Refuse rather than manufacture: with too few minority tokens or too
        # few speakers, grouped CV folds would contain no positives at all.
        if tone_y.sum() < 20 or n_speakers < N_FOLDS:
            support[f"T{tone}"]["status"] = "insufficient support for stable tone-specific model"
            continue
        support[f"T{tone}"]["status"] = "ok"
        for train_index, validate_index in grouped_folds(tone_speakers, N_FOLDS, seed):
            absolute_train = selector[train_index]
            absolute_validate = selector[validate_index]
            if y[absolute_train].sum() == 0 or (y[absolute_train] == 0).sum() == 0:
                continue
            # Tone is constant inside a per-tone model, so P0's design reduces
            # to the base features; the dummies would be all-zero columns.
            state = fit_fold("P0", features[absolute_train], tones[absolute_train],
                             y[absolute_train], class_weight, C, seed)
            oof[absolute_validate] = apply_fold(state, features[absolute_validate],
                                                tones[absolute_validate])
            labels = y[absolute_validate]
            if labels.sum() and (labels == 0).sum():
                fold_scores.append({
                    "tone": f"T{tone}",
                    "pr_auc": float(average_precision_score(labels, oof[absolute_validate])),
                    "roc_auc": float(roc_auc_score(labels, oof[absolute_validate])),
                    "n": int(len(labels)), "n_incorrect": int(labels.sum())})
    return oof, support, fold_scores


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
    features_all, tones_all, y_all = cache["praat"], cache["tone"], cache["y"]
    speakers_all = cache["speaker"]

    features, tones, y = (features_all[train_mask], tones_all[train_mask],
                          y_all[train_mask])
    speakers = speakers_all[train_mask]
    print(f"TRAIN: {len(y)} tokens, {len(set(speakers.tolist()))} speakers, "
          f"{int(y.sum())} Incorrect ({y.mean() * 100:.1f}%)")
    print(f"folds: GroupKFold({N_FOLDS}) grouped by speaker_id")

    results, oof_store = [], {}
    for kind in ("P0", "P1"):
        for class_weight in CLASS_WEIGHTS:
            for C in C_GRID:
                oof, fold_scores = run_cv(kind, features, tones, y, speakers,
                                          class_weight, C, args.seed)
                entry = metrics(y, oof)
                entry.update({"model": kind, "class_weight": str(class_weight),
                              "C": C,
                              "fold_pr_auc_mean": float(np.mean([f["pr_auc"] for f in fold_scores])),
                              "fold_pr_auc_sd": float(np.std([f["pr_auc"] for f in fold_scores], ddof=1)),
                              "fold_roc_mean": float(np.mean([f["roc_auc"] for f in fold_scores])),
                              "n_folds_scored": len(fold_scores)})
                results.append(entry)
                oof_store[(kind, str(class_weight), C)] = oof
                print(f"  {kind}  cw={str(class_weight):<9}C={C:<6}"
                      f"PR-AUC {entry['pr_auc_incorrect']:.3f}  "
                      f"ROC {entry['roc_auc']:.3f}  "
                      f"foldPR {entry['fold_pr_auc_mean']:.3f}±{entry['fold_pr_auc_sd']:.3f}")

    p2_support = None
    for class_weight in CLASS_WEIGHTS:
        for C in C_GRID:
            oof, support, fold_scores = run_p2(features, tones, y, speakers,
                                               class_weight, C, args.seed)
            p2_support = support
            valid = np.isfinite(oof)
            if valid.sum() < 100 or y[valid].sum() < 10:
                continue
            entry = metrics(y[valid], oof[valid])
            entry.update({"model": "P2", "class_weight": str(class_weight), "C": C,
                          "fold_pr_auc_mean": float(np.mean([f["pr_auc"] for f in fold_scores])) if fold_scores else float("nan"),
                          "fold_pr_auc_sd": float(np.std([f["pr_auc"] for f in fold_scores], ddof=1)) if len(fold_scores) > 1 else float("nan"),
                          "fold_roc_mean": float(np.mean([f["roc_auc"] for f in fold_scores])) if fold_scores else float("nan"),
                          "n_folds_scored": len(fold_scores),
                          "coverage": float(valid.mean())})
            results.append(entry)
            oof_store[("P2", str(class_weight), C)] = oof
            print(f"  P2  cw={str(class_weight):<9}C={C:<6}"
                  f"PR-AUC {entry['pr_auc_incorrect']:.3f}  ROC {entry['roc_auc']:.3f}  "
                  f"coverage {valid.mean() * 100:.0f}%")

    fields = ["model", "class_weight", "C", "pr_auc_incorrect", "roc_auc",
              "balanced_accuracy", "macro_f1", "incorrect_precision",
              "incorrect_recall", "incorrect_f1", "accuracy",
              "false_rejection_rate", "false_acceptance_rate", "brier",
              "prevalence", "fold_pr_auc_mean", "fold_pr_auc_sd",
              "fold_roc_mean", "n_folds_scored"]
    with CV_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    best = {kind: max((r for r in results if r["model"] == kind),
                      key=lambda r: r["pr_auc_incorrect"])
            for kind in ("P0", "P1", "P2") if any(r["model"] == kind for r in results)}
    print("\nbest per formulation (Train OOF):")
    for kind, entry in best.items():
        print(f"  {kind}: PR-AUC {entry['pr_auc_incorrect']:.3f}  "
              f"ROC {entry['roc_auc']:.3f}  BalAcc {entry['balanced_accuracy']:.3f}  "
              f"cw={entry['class_weight']} C={entry['C']}")

    # P1 preferred over P2 at similar performance: it pools across tones and is
    # more data-efficient. Selection is by PR-AUC among P0/P1 only for that
    # reason, with P2 reported as a sensitivity analysis.
    winner = max((best[k] for k in ("P0", "P1") if k in best),
                 key=lambda r: r["pr_auc_incorrect"])
    prevalence = float(y.mean())
    print(f"\nSELECTED (Train CV only): {winner['model']} "
          f"cw={winner['class_weight']} C={winner['C']}  "
          f"PR-AUC {winner['pr_auc_incorrect']:.3f} vs prevalence floor {prevalence:.3f}")

    per_tone = {}
    chosen_oof = oof_store[(winner["model"], winner["class_weight"], winner["C"])]
    from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score
    for tone in TONES:
        selector = tones == tone
        labels, scores = y[selector], chosen_oof[selector]
        if labels.sum() < 5 or (labels == 0).sum() < 5:
            per_tone[f"T{tone}"] = {"n": int(selector.sum()),
                                    "n_incorrect": int(labels.sum()),
                                    "note": "denominator too small"}
            continue
        per_tone[f"T{tone}"] = {
            "n": int(selector.sum()), "n_incorrect": int(labels.sum()),
            "pr_auc": float(average_precision_score(labels, scores)),
            "roc_auc": float(roc_auc_score(labels, scores)),
            "balanced_accuracy": float(balanced_accuracy_score(
                labels, (scores >= 0.5).astype(int))),
        }

    coefficients = inspect_coefficients(winner, features, tones, y, args.seed)
    with OOF_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["token_id", "speaker_id", "expected_tone",
                         "tone_correctness", "oof_score_selected"])
        train_rows = [r for r in rows if r["split"] == "train"]
        for row, score in zip(train_rows, chosen_oof):
            writer.writerow([row["token_id"], row["speaker_id"],
                             row["expected_tone"], row["tone_correctness"],
                             f"{score:.6f}"])

    # ---- Dev opened exactly once, after freezing ---------------------------
    protocol = freeze_protocol(winner, best, per_tone, p2_support, coefficients,
                               args.seed, prevalence)
    dev = confirm_on_dev(winner, features_all, tones_all, y_all, train_mask,
                         dev_mask, rows, args.seed)
    DEV_JSON.write_text(json.dumps(dev, indent=2, ensure_ascii=False, default=float),
                        encoding="utf-8")

    print("\n--- one-time Dev confirmation ---")
    for key in ("pr_auc_incorrect", "roc_auc", "balanced_accuracy", "macro_f1",
                "incorrect_precision", "incorrect_recall", "incorrect_f1",
                "accuracy", "false_rejection_rate", "false_acceptance_rate",
                "brier"):
        print(f"  {key:<24}{dev['overall'][key]:.4f}")
    print("  per tone:")
    for tone, entry in dev["per_tone"].items():
        if "roc_auc" in entry:
            print(f"    {tone}: n={entry['n']:>3} inc={entry['n_incorrect']:>2} "
                  f"PR {entry['pr_auc']:.3f} ROC {entry['roc_auc']:.3f}")
        else:
            print(f"    {tone}: {entry.get('note')}")
    print(f"\nprotocol sha256: {protocol['sha256'][:16]}")
    print(f"files: {CV_CSV.name}, {OOF_CSV.name}, {DEV_JSON.name}, {PROTOCOL.name}")
    return winner, best, per_tone, coefficients, dev, p2_support, prevalence


def inspect_coefficients(winner, features, tones, y, seed) -> dict:
    """Refit the winner on all of Train and read the tone-specific slopes."""
    state = fit_fold(winner["model"], features, tones, y,
                     None if winner["class_weight"] == "None" else winner["class_weight"],
                     winner["C"], seed)
    values = dict(zip(state["names"], state["model"].coef_[0]))
    focus = ("slope_mid_to_end", "rel_f0_75", "rel_f0_end")
    table = {}
    for feature in focus:
        base = values.get(feature, float("nan"))
        entry = {"T1_reference": float(base)}
        for tone in TONES:
            if tone == REFERENCE_TONE:
                continue
            interaction = values.get(f"{feature} x T{tone}", 0.0)
            entry[f"T{tone}_effective"] = float(base + interaction)
            entry[f"T{tone}_interaction"] = float(interaction)
        table[feature] = entry
    return {"focus": table, "all": {k: float(v) for k, v in values.items()}}


def confirm_on_dev(winner, features_all, tones_all, y_all, train_mask, dev_mask,
                   rows, seed) -> dict:
    from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score

    state = fit_fold(winner["model"], features_all[train_mask], tones_all[train_mask],
                     y_all[train_mask],
                     None if winner["class_weight"] == "None" else winner["class_weight"],
                     winner["C"], seed)
    scores = apply_fold(state, features_all[dev_mask], tones_all[dev_mask])
    labels = y_all[dev_mask]
    overall = metrics(labels, scores)

    per_tone = {}
    dev_tones = tones_all[dev_mask]
    for tone in TONES:
        selector = dev_tones == tone
        sub_labels, sub_scores = labels[selector], scores[selector]
        if sub_labels.sum() < 5 or (sub_labels == 0).sum() < 5:
            per_tone[f"T{tone}"] = {"n": int(selector.sum()),
                                    "n_incorrect": int(sub_labels.sum()),
                                    "note": "denominator too small"}
            continue
        per_tone[f"T{tone}"] = {
            "n": int(selector.sum()), "n_incorrect": int(sub_labels.sum()),
            "pr_auc": float(average_precision_score(sub_labels, sub_scores)),
            "roc_auc": float(roc_auc_score(sub_labels, sub_scores)),
            "balanced_accuracy": float(balanced_accuracy_score(
                sub_labels, (sub_scores >= 0.5).astype(int))),
        }
    return {"model": {k: winner[k] for k in ("model", "class_weight", "C")},
            "overall": overall, "per_tone": per_tone,
            "opened_once": True,
            "note": "Dev evaluated once after Train-CV freezing; no retuning after."}


def freeze_protocol(winner, best, per_tone, p2_support, coefficients, seed,
                    prevalence) -> dict:
    import sklearn
    payload = {
        "phase": "C3",
        "split_id": SPLIT_ID,
        "candidate_models": {
            "P0": "Praat + expected-tone one-hot (additive; reproduces Phase C)",
            "P1": ("Praat + tone dummies + Praat x tone interactions, "
                   f"reference-coded on T{REFERENCE_TONE} (primary)"),
            "P2": "four independent per-tone logistic models (secondary)",
        },
        "cv_design": {"scheme": "GroupKFold", "group": "speaker_id",
                      "n_folds": N_FOLDS, "scope": "TRAIN only",
                      "token_level_random_cv": False},
        "preprocessing_order": [
            "median impute (fold-train statistics)",
            "standardise continuous Praat features (fold-train statistics)",
            "build tone dummies (never standardised)",
            "build interactions from already-scaled base features",
        ],
        "metrics": {"primary": "PR-AUC for Incorrect",
                    "secondary": ["ROC-AUC", "balanced accuracy", "macro F1",
                                  "Incorrect precision/recall/F1"],
                    "accuracy": "descriptive only"},
        "c_grid": list(C_GRID),
        "class_weight_options": [str(c) for c in CLASS_WEIGHTS],
        "feature_design": {"praat_features": list(PRAAT_FEATURES),
                           "reference_tone": REFERENCE_TONE,
                           "p1_columns": 10 + 3 + 30},
        "selected_model": {k: winner[k] for k in ("model", "class_weight", "C")},
        "selected_train_cv_metrics": {k: winner[k] for k in
                                      ("pr_auc_incorrect", "roc_auc",
                                       "balanced_accuracy", "incorrect_f1",
                                       "fold_pr_auc_mean", "fold_pr_auc_sd")},
        "train_prevalence_floor": prevalence,
        "per_formulation_best": {k: {kk: v[kk] for kk in
                                     ("class_weight", "C", "pr_auc_incorrect",
                                      "roc_auc", "balanced_accuracy")}
                                 for k, v in best.items()},
        "p2_support": p2_support,
        "per_tone_train_oof": per_tone,
        "tone_specific_coefficients": coefficients["focus"],
        "random_seed": seed,
        "software": {"python": platform.python_version(),
                     "numpy": np.__version__, "scikit_learn": sklearn.__version__},
        "test_lock": {"features": False, "predictions": False, "metrics": False,
                      "error_analysis": False},
    }
    payload["sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=float).encode("utf-8")).hexdigest()
    PROTOCOL.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=float),
                        encoding="utf-8")
    return payload


if __name__ == "__main__":
    main()
