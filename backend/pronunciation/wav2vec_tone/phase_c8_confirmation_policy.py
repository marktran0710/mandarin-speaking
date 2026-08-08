"""Phase C8 — one-sided PASS / RETRY confirmation policy on frozen R2.

C7 established the asymmetry: this model can identify likely-acceptable
productions far better than it can identify incorrect ones. So the product is
no longer a Correct/Incorrect classifier. It confirms good attempts and stays
silent otherwise.

RETRY means "not enough evidence to confirm", never "wrong". That distinction
is enforced here in naming and carried into the report and the learner wording.

The raw R2 score is an internal ranking variable only -- C7 showed cross-fold
calibration destroys pooled comparability, so it is not a probability and must
never reach a learner.

    python -m pronunciation.wav2vec_tone.phase_c8_confirmation_policy
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
    TONES, fit_predict, normalise,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
TRAJ_CACHE = DATA_DIR / "phase_c6_trajectories.npz"
CURVE_CSV = DATA_DIR / "ompal_phase_c8_train_pass_curve.csv"
PRED_CSV = DATA_DIR / "ompal_phase_c8_train_predictions.csv"
DEV_JSON = DATA_DIR / "ompal_phase_c8_dev_confirmation.json"
POLICY = DATA_DIR / "ompal_phase_c8_policy_FROZEN.json"

C_VALUE, CLASS_WEIGHT, N_FOLDS, SEED = 0.1, "balanced", 5, 0

# Admission criteria, fixed before any curve was inspected.
MIN_PASS_PRECISION = 0.90
MIN_PASS_COUNT = 100
MIN_PASS_SPEAKERS = 20
# Tone-safety screening for POLICY B only; the global 0.90 still applies.
TONE_GATE_MIN_PASS = 20
TONE_GATE_MIN_PRECISION = 0.85
BOOTSTRAP = 4000


def oof_scores(base, tones, y, speakers, seed):
    from sklearn.model_selection import GroupKFold

    scores = np.zeros(len(y))
    audit = {"folds": 0, "leaked_speakers": 0}
    for train_index, test_index in GroupKFold(n_splits=N_FOLDS).split(
            np.zeros(len(y)), groups=speakers):
        overlap = set(speakers[train_index].tolist()) & set(speakers[test_index].tolist())
        audit["leaked_speakers"] += len(overlap)
        audit["folds"] += 1
        scores[test_index], _ = fit_predict(base[train_index], tones[train_index],
                                            y[train_index], base[test_index],
                                            tones[test_index], C_VALUE, seed)
    return scores, audit


def pass_mask(scores, tones, available, t_pass, enabled_tones):
    """PASS only when a trajectory exists, the tone is enabled, and the score
    is low enough. Everything else is RETRY -- including extraction failure."""
    eligible = available & np.isin(tones, list(enabled_tones))
    return eligible & (scores <= t_pass)


def evaluate(y, scores, tones, speakers, available, t_pass, enabled_tones) -> dict:
    passed = pass_mask(scores, tones, available, t_pass, enabled_tones)
    true_correct = int((passed & (y == 0)).sum())
    false_pass = int((passed & (y == 1)).sum())
    by_speaker = Counter(s for s, p in zip(speakers, passed) if p)
    return {
        "t_pass": float(t_pass),
        "enabled_tones": "".join(sorted(enabled_tones)),
        "n": int(len(y)),
        "n_pass": int(passed.sum()),
        "n_retry": int((~passed).sum()),
        "coverage": float(passed.mean()),
        "pass_precision": (true_correct / passed.sum()) if passed.sum() else float("nan"),
        "true_pass": true_correct, "false_pass": false_pass,
        "false_pass_rate": (false_pass / passed.sum()) if passed.sum() else float("nan"),
        "incorrect_tokens_passed": false_pass,
        "speakers_any_pass": len(by_speaker),
        "speakers_5plus_pass": sum(1 for v in by_speaker.values() if v >= 5),
        "speakers_zero_pass": len(set(speakers.tolist())) - len(by_speaker),
    }


def bootstrap_precision(y, passed, speakers, seed=0, draws=BOOTSTRAP):
    """Speaker-cluster bootstrap: resample speakers, not tokens.

    Tokens within a learner are not independent, so a token bootstrap would
    give an interval far narrower than 32 speakers can support.
    """
    unique = np.array(sorted(set(speakers.tolist())))
    index_by_speaker = {s: np.flatnonzero(speakers == s) for s in unique}
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(draws):
        drawn = rng.choice(unique, len(unique), replace=True)
        indices = np.concatenate([index_by_speaker[s] for s in drawn])
        selected = passed[indices]
        if selected.sum() == 0:
            continue
        values.append(float((y[indices][selected] == 0).mean()))
    if not values:
        return None
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


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
    stored = np.load(TRAJ_CACHE, allow_pickle=True)
    order = {t: i for i, t in enumerate(cache["token_ids"].tolist())}
    rows = sorted(rows, key=lambda r: order[r["token_id"]])

    trajectory = normalise(stored["learner"], "N2")
    available_all = np.asarray([s.startswith("ok") for s in stored["status"]])
    split = cache["split"]
    train_mask, dev_mask = split == "train", split == "dev"
    tones, y, speakers = cache["tone"], cache["y"], cache["speaker"]

    scores, audit = oof_scores(trajectory[train_mask], tones[train_mask],
                               y[train_mask], speakers[train_mask], args.seed)
    train_y, train_tones = y[train_mask], tones[train_mask]
    train_speakers, train_available = speakers[train_mask], available_all[train_mask]

    print(f"Train rows {int(train_mask.sum())}, speakers "
          f"{len(set(train_speakers.tolist()))}, folds {audit['folds']}, "
          f"speaker leakage {audit['leaked_speakers']}")
    assert audit["leaked_speakers"] == 0
    assert int(train_mask.sum()) == 1424 and len(set(train_speakers.tolist())) == 32
    print(f"trajectory unavailable (forced RETRY): "
          f"{int((~train_available).sum())}/{len(train_available)}")

    all_tones = set(TONES)
    grid = np.unique(np.round(np.quantile(scores, np.linspace(0.01, 0.95, 120)), 5))
    curve = []
    for t_pass in grid:
        entry = evaluate(train_y, scores, train_tones, train_speakers,
                         train_available, t_pass, all_tones)
        for tone in TONES:
            mask = train_tones == tone
            sub = evaluate(train_y[mask], scores[mask], train_tones[mask],
                           train_speakers[mask], train_available[mask], t_pass,
                           all_tones)
            entry[f"T{tone}_pass"] = sub["n_pass"]
            entry[f"T{tone}_precision"] = sub["pass_precision"]
            entry[f"T{tone}_false_pass"] = sub["false_pass"]
        curve.append(entry)
    with CURVE_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(curve[0].keys()))
        writer.writeheader()
        writer.writerows(curve)

    def admissible(entry):
        return (np.isfinite(entry["pass_precision"])
                and entry["pass_precision"] >= MIN_PASS_PRECISION
                and entry["n_pass"] >= MIN_PASS_COUNT
                and entry["speakers_any_pass"] >= MIN_PASS_SPEAKERS)

    targets = {}
    for target in (0.90, 0.925, 0.95, 0.975):
        pool = [c for c in curve if np.isfinite(c["pass_precision"])
                and c["pass_precision"] >= target
                and c["n_pass"] >= MIN_PASS_COUNT
                and c["speakers_any_pass"] >= MIN_PASS_SPEAKERS]
        if pool:
            best = max(pool, key=lambda c: c["n_pass"])
            passed = pass_mask(scores, train_tones, train_available,
                               best["t_pass"], all_tones)
            best = {**best, "ci": bootstrap_precision(train_y, passed,
                                                      train_speakers, args.seed)}
            targets[f"{target:.3f}"] = best
        else:
            targets[f"{target:.3f}"] = None

    print("\nPASS operating points (>=100 PASS, >=20 speakers):")
    for target, entry in targets.items():
        if entry is None:
            print(f"  precision>={target}: NOT ACHIEVABLE WITH ADEQUATE SUPPORT")
            continue
        ci = entry["ci"]
        print(f"  precision>={target}: t_pass {entry['t_pass']:.4f}  "
              f"prec {entry['pass_precision']:.3f}"
              + (f" CI [{ci[0]:.3f},{ci[1]:.3f}]" if ci else "")
              + f"  n {entry['n_pass']} ({entry['coverage'] * 100:.1f}%)  "
              f"speakers {entry['speakers_any_pass']}  "
              f"false-pass {entry['false_pass']}")

    # --- POLICY A: global -------------------------------------------------
    policy_a_pool = [c for c in curve if admissible(c)]
    policy_a = max(policy_a_pool, key=lambda c: c["n_pass"]) if policy_a_pool else None

    # --- POLICY B: tone-safety gate at POLICY A's threshold ----------------
    policy_b = None
    gate = {}
    if policy_a:
        t_pass = policy_a["t_pass"]
        for tone in TONES:
            mask = train_tones == tone
            sub = evaluate(train_y[mask], scores[mask], train_tones[mask],
                           train_speakers[mask], train_available[mask], t_pass,
                           all_tones)
            eligible = (sub["n_pass"] >= TONE_GATE_MIN_PASS
                        and np.isfinite(sub["pass_precision"])
                        and sub["pass_precision"] >= TONE_GATE_MIN_PRECISION)
            gate[f"T{tone}"] = {"n_pass": sub["n_pass"],
                                "precision": sub["pass_precision"],
                                "false_pass": sub["false_pass"],
                                "eligible": bool(eligible)}
        enabled = {t for t in TONES if gate[f"T{t}"]["eligible"]}
        if enabled:
            policy_b = evaluate(train_y, scores, train_tones, train_speakers,
                                train_available, t_pass, enabled)
            passed_b = pass_mask(scores, train_tones, train_available, t_pass, enabled)
            policy_b["ci"] = bootstrap_precision(train_y, passed_b, train_speakers,
                                                 args.seed)
        print("\ntone-safety gate (>=20 PASS and >=0.85 precision at POLICY A's "
              "threshold):")
        for tone, entry in gate.items():
            print(f"  {tone}: n_pass {entry['n_pass']:>3}  "
                  f"prec {entry['precision']:.3f}  false-pass {entry['false_pass']:>3}  "
                  f"{'ELIGIBLE' if entry['eligible'] else 'GATED -> RETRY'}")

    if policy_a:
        passed_a = pass_mask(scores, train_tones, train_available,
                             policy_a["t_pass"], all_tones)
        policy_a["ci"] = bootstrap_precision(train_y, passed_a, train_speakers,
                                             args.seed)
        print(f"\nPOLICY A global : prec {policy_a['pass_precision']:.3f} "
              f"CI {policy_a['ci']}  n {policy_a['n_pass']} "
              f"({policy_a['coverage'] * 100:.1f}%)  speakers "
              f"{policy_a['speakers_any_pass']}  false-pass {policy_a['false_pass']}")
    if policy_b:
        print(f"POLICY B gated  : prec {policy_b['pass_precision']:.3f} "
              f"CI {policy_b['ci']}  n {policy_b['n_pass']} "
              f"({policy_b['coverage'] * 100:.1f}%)  speakers "
              f"{policy_b['speakers_any_pass']}  false-pass {policy_b['false_pass']}  "
              f"tones {policy_b['enabled_tones']}")

    # Priority: precision, then speaker coverage, then tone safety, then coverage.
    chosen = None
    candidates = [p for p in (policy_a, policy_b) if p and admissible(p)]
    if candidates:
        chosen = max(candidates, key=lambda p: (round(p["pass_precision"], 3),
                                                p["speakers_any_pass"],
                                                len(p["enabled_tones"]) * -1,
                                                p["n_pass"]))
        chosen["policy_name"] = ("POLICY_B_tone_gated"
                                 if chosen is policy_b else "POLICY_A_global")

    per_speaker, false_audit = {}, []
    if chosen:
        enabled = set(chosen["enabled_tones"])
        passed = pass_mask(scores, train_tones, train_available,
                           chosen["t_pass"], enabled)
        for speaker in sorted(set(train_speakers.tolist())):
            mask = train_speakers == speaker
            per_speaker[speaker] = {
                "n": int(mask.sum()),
                "true_correct_rate": float((train_y[mask] == 0).mean()),
                "n_pass": int(passed[mask].sum()),
                "pass_coverage": float(passed[mask].mean()),
                "pass_precision": float((train_y[mask][passed[mask]] == 0).mean())
                if passed[mask].sum() else None,
            }
        train_rows = [r for r, m in zip(rows, train_mask) if m]
        for index in np.flatnonzero(passed & (train_y == 1)):
            false_audit.append({
                "token_id": train_rows[index]["token_id"],
                "speaker_id": train_speakers[index],
                "expected_tone": train_tones[index],
                "trajectory_available": bool(train_available[index]),
                "score": float(scores[index]),
                "distance_from_threshold": float(chosen["t_pass"] - scores[index]),
            })

    with PRED_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["token_id", "speaker_id", "expected_tone",
                         "tone_correctness", "trajectory_available", "r2_score",
                         "decision"])
        train_rows = [r for r, m in zip(rows, train_mask) if m]
        enabled = set(chosen["enabled_tones"]) if chosen else all_tones
        t_pass = chosen["t_pass"] if chosen else float(np.quantile(scores, 0.2))
        decisions = pass_mask(scores, train_tones, train_available, t_pass, enabled)
        for index, row in enumerate(train_rows):
            writer.writerow([row["token_id"], row["speaker_id"], row["expected_tone"],
                             row["tone_correctness"], int(train_available[index]),
                             f"{scores[index]:.6f}",
                             "PASS" if decisions[index] else "RETRY"])

    dev = None
    if chosen:
        dev = confirm_dev(chosen, trajectory, tones, y, speakers, available_all,
                          train_mask, dev_mask, args.seed)
        DEV_JSON.write_text(json.dumps(dev, indent=2, ensure_ascii=False, default=float),
                            encoding="utf-8")
        freeze(chosen, gate, targets, per_speaker, args.seed)
        print(f"\nFROZEN: {chosen['policy_name']}  t_pass {chosen['t_pass']:.4f}  "
              f"tones {chosen['enabled_tones']}")
        print("\n--- one-time Dev confirmation (development confirmation, "
              "NOT independent validation) ---")
        overall = dev["overall"]
        print(f"  PASS {overall['n_pass']} ({overall['coverage'] * 100:.1f}%)  "
              f"precision {overall['pass_precision']:.3f} CI {dev['ci']}  "
              f"false-pass {overall['false_pass']}  "
              f"speakers {overall['speakers_any_pass']}")
        for tone, entry in dev["per_tone"].items():
            print(f"    {tone}: n_pass {entry['n_pass']:>3} "
                  f"prec {entry['pass_precision']:.3f} "
                  f"cov {entry['coverage'] * 100:5.1f}%")
        print(f"  stability: Δprecision "
              f"{overall['pass_precision'] - chosen['pass_precision']:+.3f}, "
              f"Δcoverage {overall['coverage'] - chosen['coverage']:+.3f}")
    else:
        print("\nNO ADMISSIBLE POLICY. Dev NOT opened.")

    (DATA_DIR / "ompal_phase_c8_summary.json").write_text(json.dumps({
        "targets": targets, "policy_a": policy_a, "policy_b": policy_b,
        "tone_gate": gate, "chosen": chosen, "per_speaker": per_speaker,
        "false_pass_audit": false_audit, "dev": dev,
        "leakage_audit": audit,
        "admission": {"min_precision": MIN_PASS_PRECISION,
                      "min_pass": MIN_PASS_COUNT,
                      "min_speakers": MIN_PASS_SPEAKERS},
        "test_lock": {"trajectories": False, "features": False, "scores": False,
                      "decisions": False, "metrics": False},
    }, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    print(f"\nfiles: {CURVE_CSV.name}, {PRED_CSV.name}"
          + (f", {DEV_JSON.name}, {POLICY.name}" if chosen else ""))


def confirm_dev(policy, trajectory, tones, y, speakers, available, train_mask,
                dev_mask, seed) -> dict:
    scores, _ = fit_predict(trajectory[train_mask], tones[train_mask], y[train_mask],
                            trajectory[dev_mask], tones[dev_mask], C_VALUE, seed)
    dev_y, dev_tones = y[dev_mask], tones[dev_mask]
    dev_speakers, dev_available = speakers[dev_mask], available[dev_mask]
    enabled = set(policy["enabled_tones"])
    overall = evaluate(dev_y, scores, dev_tones, dev_speakers, dev_available,
                       policy["t_pass"], enabled)
    passed = pass_mask(scores, dev_tones, dev_available, policy["t_pass"], enabled)
    per_tone = {}
    for tone in TONES:
        mask = dev_tones == tone
        per_tone[f"T{tone}"] = evaluate(dev_y[mask], scores[mask], dev_tones[mask],
                                        dev_speakers[mask], dev_available[mask],
                                        policy["t_pass"], enabled)
    return {"label": "development confirmation (Dev already inspected in C6)",
            "overall": overall, "per_tone": per_tone,
            "ci": bootstrap_precision(dev_y, passed, dev_speakers, seed),
            "opened_once": True}


def freeze(policy, gate, targets, per_speaker, seed) -> None:
    payload = {
        "phase": "C8", "policy_name": policy["policy_name"],
        "representation": "R2 20-pt median-centred semitone trajectory + tone interactions",
        "model_hash": hashlib.sha256(json.dumps(
            {"C": C_VALUE, "class_weight": CLASS_WEIGHT, "points": 20},
            sort_keys=True).encode()).hexdigest(),
        "t_pass": policy["t_pass"], "enabled_tones": policy["enabled_tones"],
        "trajectory_failure_rule": "trajectory unavailable -> RETRY, never PASS",
        "outputs_allowed": ["PASS", "RETRY"],
        "outputs_forbidden": ["INCORRECT", "wrong tone", "produced-tone diagnosis"],
        "retry_semantics": ("insufficient evidence to confirm; NOT a claim that "
                            "the pronunciation was wrong"),
        "score_semantics": ("internal ranking variable only; not a probability, "
                            "never displayed to a learner"),
        "train": {k: policy[k] for k in
                  ("pass_precision", "coverage", "n_pass", "false_pass",
                   "speakers_any_pass", "speakers_5plus_pass", "speakers_zero_pass")},
        "train_precision_ci": policy.get("ci"),
        "tone_gate": gate,
        "bootstrap": ("speaker-cluster: resample the 32 Train speakers with "
                      f"replacement {BOOTSTRAP} times, recompute PASS precision, "
                      "report 2.5/97.5 percentiles"),
        "admission_criteria": {"min_precision": MIN_PASS_PRECISION,
                               "min_pass_count": MIN_PASS_COUNT,
                               "min_speakers": MIN_PASS_SPEAKERS,
                               "fixed_before_results": True},
        "seed": seed,
        "software": {"python": platform.python_version(), "numpy": np.__version__},
    }
    payload["sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=float).encode()).hexdigest()
    POLICY.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=float),
                      encoding="utf-8")


if __name__ == "__main__":
    main()
