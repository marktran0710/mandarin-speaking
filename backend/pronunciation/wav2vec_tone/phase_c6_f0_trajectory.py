"""Phase C6 — does a time-normalised F0 trajectory beat the 10 summary features?

A representation experiment, nothing else. Classifier, split, alignment, pitch
settings and labels are all frozen; the only thing that changes is how the
contour is described.

The motivating observation: the features that replicated across Train and Dev
were all late-contour measures, which suggests trajectory shape carries the
signal and eight summary statistics discard most of it.

Test is sealed -- trajectories are extracted for train, dev and the native
reference tokens only.

    python -m pronunciation.wav2vec_tone.phase_c6_f0_trajectory
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
TRAJ_CACHE = DATA_DIR / "phase_c6_trajectories.npz"
CV_CSV = DATA_DIR / "ompal_phase_c6_train_cv_results.csv"
OOF_CSV = DATA_DIR / "ompal_phase_c6_oof_predictions.csv"
AUDIT_JSON = DATA_DIR / "ompal_phase_c6_trajectory_audit.json"
PROTOCOL = DATA_DIR / "ompal_phase_c6_protocol_FROZEN.json"

N_POINTS = 20                 # frozen for this phase; no search over point counts
# ``trajectory_from_segment`` applies 12*log2(Hz) before returning.  The
# persisted phase_c6_trajectories.npz cache therefore stores semitones, never
# Hz.  Consumers must centre these values directly and must not apply log2 a
# second time.
TRAJECTORY_CACHE_SCHEMA_VERSION = "phase_c6_f0_trajectory.v1"
TRAJECTORY_CACHE_UNIT = "semitones_re_1hz"
TONES = ("1", "2", "3", "4")
REFERENCE_TONE = "1"
C_GRID = (0.01, 0.1, 1.0, 10.0)
CLASS_WEIGHT = "balanced"     # fixed from C3, not reopened
N_FOLDS = 5
SEED = 0
MIN_VOICED_FRAMES = 3

# Frozen pitch settings, identical to praat_features.py.
PITCH_FLOOR, PITCH_CEILING, PITCH_STEP = 60.0, 500.0, 0.005
SAMPLE_RATE = 16000

PRAAT_SUMMARY = (
    "rel_f0_start", "rel_f0_25", "rel_f0_50", "rel_f0_75", "rel_f0_end",
    "f0_range_st", "slope_start_to_mid", "slope_mid_to_end",
    "duration_seconds", "voiced_proportion",
)


def trajectory_from_segment(audio) -> tuple[np.ndarray | None, str]:
    """20-point semitone trajectory, or (None, reason).

    Missing handling, fixed in advance: keep voiced observations, interpolate
    interior gaps that are bounded by voiced values, extend the nearest voiced
    value across edge gaps, and declare the token unavailable only when there
    is too little pitch to anchor any of that.
    """
    import parselmouth

    if len(audio) < int(0.03 * SAMPLE_RATE):
        return None, "too_short_for_pitch"
    try:
        pitch = parselmouth.Sound(audio.astype(np.float64), SAMPLE_RATE).to_pitch(
            time_step=PITCH_STEP, pitch_floor=PITCH_FLOOR, pitch_ceiling=PITCH_CEILING)
    except Exception:  # noqa: BLE001
        return None, "praat_error"

    frequencies = pitch.selected_array["frequency"]
    times = np.asarray(pitch.xs(), dtype=float)
    voiced = np.isfinite(frequencies) & (frequencies > 0)
    if int(voiced.sum()) < MIN_VOICED_FRAMES:
        return None, "insufficient_voiced_frames"

    voiced_times, voiced_values = times[voiced], frequencies[voiced]
    # This conversion is intentionally the sole Hz -> semitone conversion in
    # the Phase C6 representation.  Cached trajectories retain these values
    # in semitones; downstream models only centre/impute/scale them.
    semitones = 12.0 * np.log2(voiced_values)
    # Normalised time runs across the VOICED span, so the contour is the tone
    # rather than the surrounding silence.
    span = voiced_times[-1] - voiced_times[0]
    if span <= 0:
        return np.full(N_POINTS, float(semitones.mean())), "ok_flat"
    grid = voiced_times[0] + np.linspace(0.0, 1.0, N_POINTS) * span
    # np.interp interpolates interior gaps and holds the edge values outside
    # the observed range, which is exactly the specified edge rule.
    return np.interp(grid, voiced_times, semitones), "ok"


def build_trajectories(rows):
    import soundfile as sf

    matrix = np.full((len(rows), N_POINTS), np.nan)
    status = []
    for index, row in enumerate(rows):
        audio, _ = sf.read(str(DATA_DIR / row["extracted_token_path"]), dtype="float32")
        trajectory, reason = trajectory_from_segment(np.asarray(audio, dtype=np.float32))
        status.append(reason)
        if trajectory is not None:
            matrix[index] = trajectory
        if (index + 1) % 400 == 0:
            print(f"    {index + 1}/{len(rows)}")
    return matrix, status


def normalise(matrix, method):
    """N1 onset-relative or N2 token-median-centred, both in semitones."""
    if method == "N1":
        return matrix - matrix[:, :1]
    if method == "N2":
        return matrix - np.nanmedian(matrix, axis=1, keepdims=True)
    raise ValueError(method)


def design(base, tones):
    """Base block + reference-coded tone dummies + their interactions."""
    dummies = np.stack([(tones == t).astype(float)
                        for t in TONES if t != REFERENCE_TONE], axis=1)
    blocks = [base, dummies]
    for position, _ in enumerate([t for t in TONES if t != REFERENCE_TONE]):
        blocks.append(base * dummies[:, position:position + 1])
    return np.hstack(blocks)


def fit_predict(train_base, train_tones, train_y, test_base, test_tones, C, seed):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    imputer = SimpleImputer(strategy="median").fit(train_base)
    scaler = StandardScaler().fit(imputer.transform(train_base))
    train_matrix = design(scaler.transform(imputer.transform(train_base)), train_tones)
    test_matrix = design(scaler.transform(imputer.transform(test_base)), test_tones)
    model = LogisticRegression(max_iter=8000, C=C, class_weight=CLASS_WEIGHT,
                               random_state=seed).fit(train_matrix, train_y)
    return model.predict_proba(test_matrix)[:, 1], model


def evaluate(base, tones, y, speakers, C, seed):
    from sklearn.model_selection import GroupKFold
    from sklearn.metrics import average_precision_score, roc_auc_score

    oof = np.zeros(len(y))
    folds = []
    for train_index, test_index in GroupKFold(n_splits=N_FOLDS).split(
            np.zeros(len(y)), groups=speakers):
        scores, _ = fit_predict(base[train_index], tones[train_index], y[train_index],
                                base[test_index], tones[test_index], C, seed)
        oof[test_index] = scores
        labels = y[test_index]
        if labels.sum() and (labels == 0).sum():
            folds.append({"pr": float(average_precision_score(labels, scores)),
                          "roc": float(roc_auc_score(labels, scores))})
    return oof, folds


def metrics(y, scores) -> dict:
    from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
                                 f1_score, roc_auc_score)
    predicted = (scores >= 0.5).astype(int)
    return {
        "pr_auc": float(average_precision_score(y, scores)),
        "roc_auc": float(roc_auc_score(y, scores)),
        "balanced_accuracy": float(balanced_accuracy_score(y, predicted)),
        "macro_f1": float(f1_score(y, predicted, average="macro")),
        "incorrect_f1": float(f1_score(y, predicted, zero_division=0)),
        "accuracy": float((predicted == y).mean()),
    }


def per_tone(y, scores, tones) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score
    out = {}
    for tone in TONES:
        mask = tones == tone
        labels, values = y[mask], scores[mask]
        if labels.sum() < 5 or (labels == 0).sum() < 5:
            out[f"T{tone}"] = {"n": int(mask.sum()), "n_incorrect": int(labels.sum()),
                               "note": "denominator too small"}
            continue
        out[f"T{tone}"] = {"n": int(mask.sum()), "n_incorrect": int(labels.sum()),
                           "pr_auc": float(average_precision_score(labels, values)),
                           "roc_auc": float(roc_auc_score(labels, values))}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    all_rows = list(csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8")))
    if any(r["split"] == "test" for r in all_rows if r["split"] == "test") and False:
        pass
    learner = [r for r in all_rows if r["split"] in ("train", "dev")]
    native = [r for r in all_rows if r["split"] == "native_reference"]
    if any(r["split"] == "test" for r in learner):
        sys.exit("TEST LOCK VIOLATION")

    cache = dict(np.load(CACHE, allow_pickle=True))
    if "test" in set(cache["split"].tolist()):
        sys.exit("TEST LOCK VIOLATION in cache")
    order = {t: i for i, t in enumerate(cache["token_ids"].tolist())}
    learner = sorted(learner, key=lambda r: order[r["token_id"]])

    if TRAJ_CACHE.exists():
        stored = np.load(TRAJ_CACHE, allow_pickle=True)
        raw_traj, status = stored["learner"], list(stored["status"])
        native_traj, native_status = stored["native"], list(stored["native_status"])
        print("[cache] reusing trajectories")
    else:
        print(f"[1] extracting {N_POINTS}-point trajectories for "
              f"{len(learner)} learner tokens…")
        raw_traj, status = build_trajectories(learner)
        print(f"[2] native reference ({len(native)} tokens)…")
        native_traj, native_status = build_trajectories(native)
        np.savez_compressed(TRAJ_CACHE, learner=raw_traj,
                            status=np.asarray(status, dtype=object),
                            native=native_traj,
                            native_status=np.asarray(native_status, dtype=object))

    available = np.asarray([s.startswith("ok") for s in status])
    audit = {
        "n_tokens": len(learner),
        "trajectory_available": int(available.sum()),
        "trajectory_unavailable": int((~available).sum()),
        "unavailable_reasons": dict(Counter(s for s in status if not s.startswith("ok"))),
        "unavailable_by_label": dict(Counter(
            ("Incorrect" if r["tone_correctness"] == "0" else "Correct")
            for r, ok in zip(learner, available) if not ok)),
        "points": N_POINTS,
        "missing_handling": ("interior gaps interpolated between voiced values; "
                             "edge gaps hold the nearest voiced value; token "
                             "declared unavailable only below "
                             f"{MIN_VOICED_FRAMES} voiced frames; unavailable "
                             "rows kept and median-imputed inside each fold"),
    }
    print(f"    available {audit['trajectory_available']}/{audit['n_tokens']}, "
          f"unavailable {audit['trajectory_unavailable']} "
          f"{audit['unavailable_reasons']}")

    split = cache["split"]
    train_mask, dev_mask = split == "train", split == "dev"
    tones, y, speakers = cache["tone"], cache["y"], cache["speaker"]
    summary = cache["praat"]

    representations = {
        "R0_summary": summary,
        "R1_trajectory_N1": normalise(raw_traj, "N1"),
        "R2_trajectory_N2": normalise(raw_traj, "N2"),
    }

    results, oof_store = [], {}
    for name, base in representations.items():
        for C in C_GRID:
            oof, folds = evaluate(base[train_mask], tones[train_mask], y[train_mask],
                                  speakers[train_mask], C, args.seed)
            entry = metrics(y[train_mask], oof)
            entry.update({"representation": name, "C": C,
                          "n_features": design(base[train_mask][:2],
                                               tones[train_mask][:2]).shape[1],
                          "fold_pr_mean": float(np.mean([f["pr"] for f in folds])),
                          "fold_pr_sd": float(np.std([f["pr"] for f in folds], ddof=1)),
                          "fold_roc_mean": float(np.mean([f["roc"] for f in folds]))})
            results.append(entry)
            oof_store[(name, C)] = oof
            print(f"  {name:<20}C={C:<6}PR {entry['pr_auc']:.3f}  "
                  f"ROC {entry['roc_auc']:.3f}  foldPR {entry['fold_pr_mean']:.3f}"
                  f"±{entry['fold_pr_sd']:.3f}")

    best = {name: max((r for r in results if r["representation"] == name),
                      key=lambda r: r["pr_auc"])
            for name in representations}
    best_traj_name = max(("R1_trajectory_N1", "R2_trajectory_N2"),
                         key=lambda n: best[n]["pr_auc"])

    # R3 uses whichever trajectory normalisation won inside Train.
    fusion_base = np.hstack([representations[best_traj_name], summary])
    for C in C_GRID:
        oof, folds = evaluate(fusion_base[train_mask], tones[train_mask],
                              y[train_mask], speakers[train_mask], C, args.seed)
        entry = metrics(y[train_mask], oof)
        entry.update({"representation": "R3_trajectory_plus_summary", "C": C,
                      "n_features": design(fusion_base[train_mask][:2],
                                           tones[train_mask][:2]).shape[1],
                      "fold_pr_mean": float(np.mean([f["pr"] for f in folds])),
                      "fold_pr_sd": float(np.std([f["pr"] for f in folds], ddof=1)),
                      "fold_roc_mean": float(np.mean([f["roc"] for f in folds]))})
        results.append(entry)
        oof_store[("R3_trajectory_plus_summary", C)] = oof
        print(f"  {'R3_traj+summary':<20}C={C:<6}PR {entry['pr_auc']:.3f}  "
              f"ROC {entry['roc_auc']:.3f}  foldPR {entry['fold_pr_mean']:.3f}"
              f"±{entry['fold_pr_sd']:.3f}")
    best["R3_trajectory_plus_summary"] = max(
        (r for r in results if r["representation"] == "R3_trajectory_plus_summary"),
        key=lambda r: r["pr_auc"])

    with CV_CSV.open("w", newline="", encoding="utf-8") as handle:
        fields = ["representation", "C", "n_features", "pr_auc", "roc_auc",
                  "balanced_accuracy", "macro_f1", "incorrect_f1", "accuracy",
                  "fold_pr_mean", "fold_pr_sd", "fold_roc_mean"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print("\nbest per representation (Train OOF):")
    for name, entry in best.items():
        print(f"  {name:<28}PR {entry['pr_auc']:.3f}  ROC {entry['roc_auc']:.3f}  "
              f"C={entry['C']}  dims={entry['n_features']}")

    baseline = best["R0_summary"]
    winner = max(best.values(), key=lambda r: r["pr_auc"])
    delta = {k: winner[k] - baseline[k] for k in
             ("pr_auc", "roc_auc", "balanced_accuracy", "incorrect_f1")}
    print(f"\nR0 -> {winner['representation']}: "
          + "  ".join(f"Δ{k} {v:+.3f}" for k, v in delta.items()))

    tone_tables = {name: per_tone(y[train_mask],
                                  oof_store[(name, best[name]["C"])],
                                  tones[train_mask])
                   for name in best}
    print("\nper tone (Train OOF ROC):")
    for name, table in tone_tables.items():
        print(f"  {name:<28}" + "  ".join(
            f"T{t} {table[f'T{t}'].get('roc_auc', float('nan')):.3f}" for t in TONES))

    template = native_template_diagnostic(native, native_traj, native_status,
                                          raw_traj, learner, train_mask, y, tones)
    coefficients = trajectory_weights(representations[best_traj_name], tones, y,
                                      train_mask, best[best_traj_name]["C"], args.seed)

    with OOF_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["token_id", "speaker_id", "expected_tone",
                         "tone_correctness"] + [f"oof_{n}" for n in best])
        train_rows = [r for r, m in zip(learner, train_mask) if m]
        columns = [oof_store[(n, best[n]["C"])] for n in best]
        for index, row in enumerate(train_rows):
            writer.writerow([row["token_id"], row["speaker_id"], row["expected_tone"],
                             row["tone_correctness"]]
                            + [f"{c[index]:.6f}" for c in columns])

    audit.update({"per_tone": tone_tables, "native_template": template,
                  "trajectory_weights": coefficients,
                  "baseline": baseline, "winner": winner, "delta_vs_R0": delta})
    AUDIT_JSON.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=float),
                          encoding="utf-8")

    # Dev opens only on a meaningful Train improvement.
    meaningful = delta["pr_auc"] >= 0.02 and winner["representation"] != "R0_summary"
    dev = None
    if meaningful:
        dev = confirm_dev(winner, representations, summary, best_traj_name,
                          cache, train_mask, dev_mask, args.seed)
        audit["dev_confirmation"] = dev
        AUDIT_JSON.write_text(json.dumps(audit, indent=2, ensure_ascii=False,
                                         default=float), encoding="utf-8")
        freeze(winner, best_traj_name, audit, args.seed)
        print("\n--- one-time Dev confirmation ---")
        for key in ("pr_auc", "roc_auc", "balanced_accuracy", "incorrect_f1"):
            print(f"  {key:<22}{dev['overall'][key]:.4f}")
        for tone, entry in dev["per_tone"].items():
            print(f"    {tone}: n={entry['n']} inc={entry['n_incorrect']} "
                  f"ROC {entry.get('roc_auc', float('nan')):.3f}")
    else:
        print(f"\nNo meaningful Train improvement (ΔPR-AUC {delta['pr_auc']:+.3f} "
              f"< 0.02). Dev NOT opened; no representation frozen.")
    print(f"\nfiles: {CV_CSV.name}, {OOF_CSV.name}, {AUDIT_JSON.name}")


def native_template_diagnostic(native, native_traj, native_status, learner_traj,
                               learner, train_mask, y, tones) -> dict:
    """Distance of each learner contour to native tone prototypes.

    Native tokens are an external reference and never enter learner training
    labels. Prototypes are built only where enough native tokens exist per tone.
    """
    native_tones = np.asarray([r["expected_tone"] for r in native])
    available = np.asarray([s.startswith("ok") for s in native_status])
    counts = Counter(native_tones[available].tolist())
    if any(counts.get(t, 0) < 5 for t in TONES):
        return {"usable": False,
                "reason": "fewer than 5 usable native tokens for some tone",
                "counts": {t: counts.get(t, 0) for t in TONES}}

    prototypes = {}
    for tone in TONES:
        mask = available & (native_tones == tone)
        centred = native_traj[mask] - np.nanmedian(native_traj[mask], axis=1,
                                                   keepdims=True)
        prototypes[tone] = np.nanmean(centred, axis=0)

    centred_learner = learner_traj - np.nanmedian(learner_traj, axis=1, keepdims=True)
    expected_distance, margin, correlation = [], [], []
    for index in range(len(centred_learner)):
        vector = centred_learner[index]
        if not np.isfinite(vector).all():
            expected_distance.append(np.nan); margin.append(np.nan)
            correlation.append(np.nan); continue
        distances = {t: float(np.linalg.norm(vector - prototypes[t])) for t in TONES}
        expected = tones[index]
        others = [d for t, d in distances.items() if t != expected]
        expected_distance.append(distances[expected])
        margin.append(min(others) - distances[expected])
        correlation.append(float(np.corrcoef(vector, prototypes[expected])[0, 1]))

    expected_distance = np.asarray(expected_distance)
    margin = np.asarray(margin)
    correlation = np.asarray(correlation)
    train_y = y[train_mask]

    def compare(values):
        subset = values[train_mask]
        good = subset[(train_y == 0) & np.isfinite(subset)]
        bad = subset[(train_y == 1) & np.isfinite(subset)]
        return {"correct_median": float(np.median(good)),
                "incorrect_median": float(np.median(bad)),
                "n_correct": int(len(good)), "n_incorrect": int(len(bad))}

    return {"usable": True, "native_counts": {t: counts.get(t, 0) for t in TONES},
            "distance_to_expected": compare(expected_distance),
            "expected_vs_alternative_margin": compare(margin),
            "correlation_with_expected": compare(correlation),
            "note": ("diagnostic only; nearest-template identity is NOT a "
                     "produced-tone claim, which OMPAL cannot validate")}


def trajectory_weights(base, tones, y, train_mask, C, seed) -> dict:
    _, model = fit_predict(base[train_mask], tones[train_mask], y[train_mask],
                           base[train_mask][:2], tones[train_mask][:2], C, seed)
    coefficients = model.coef_[0]
    out = {}
    for position, tone in enumerate(TONES):
        if tone == REFERENCE_TONE:
            weights = coefficients[:N_POINTS]
        else:
            start = N_POINTS + 3 + (position - 1) * N_POINTS
            weights = coefficients[:N_POINTS] + coefficients[start:start + N_POINTS]
        thirds = np.array_split(weights, 3)
        out[f"T{tone}"] = {"early": float(thirds[0].mean()),
                           "middle": float(thirds[1].mean()),
                           "late": float(thirds[2].mean()),
                           "weights": [float(w) for w in weights]}
    return out


def confirm_dev(winner, representations, summary, best_traj_name, cache,
                train_mask, dev_mask, seed) -> dict:
    name = winner["representation"]
    base = (np.hstack([representations[best_traj_name], summary])
            if name == "R3_trajectory_plus_summary" else representations[name])
    tones, y = cache["tone"], cache["y"]
    scores, _ = fit_predict(base[train_mask], tones[train_mask], y[train_mask],
                            base[dev_mask], tones[dev_mask], winner["C"], seed)
    return {"representation": name, "C": winner["C"],
            "overall": metrics(y[dev_mask], scores),
            "per_tone": per_tone(y[dev_mask], scores, tones[dev_mask]),
            "opened_once": True}


def freeze(winner, best_traj_name, audit, seed) -> None:
    import sklearn
    payload = {
        "phase": "C6",
        "trajectory_extraction": {
            "pitch_floor": PITCH_FLOOR, "pitch_ceiling": PITCH_CEILING,
            "time_step": PITCH_STEP, "points": N_POINTS,
            "time_axis": "normalised across the voiced span",
            "units": "semitones, 12*log2(F0)",
        },
        "normalisation": best_traj_name,
        "missing_f0_handling": audit["missing_handling"],
        "candidates": ["R0_summary", "R1_trajectory_N1", "R2_trajectory_N2",
                       "R3_trajectory_plus_summary"],
        "cv_design": {"scheme": "GroupKFold", "group": "speaker_id",
                      "folds": N_FOLDS, "scope": "TRAIN only"},
        "c_grid": list(C_GRID), "class_weight": CLASS_WEIGHT,
        "selected_representation": winner["representation"],
        "selected_C": winner["C"],
        "train_cv": {k: winner[k] for k in ("pr_auc", "roc_auc",
                                            "balanced_accuracy", "incorrect_f1")},
        "seed": seed,
        "software": {"python": platform.python_version(), "numpy": np.__version__,
                     "scikit_learn": sklearn.__version__},
        "test_lock": {"trajectories": False, "features": False,
                      "predictions": False, "metrics": False},
    }
    payload["sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=float).encode()).hexdigest()
    PROTOCOL.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=float),
                        encoding="utf-8")


if __name__ == "__main__":
    main()
