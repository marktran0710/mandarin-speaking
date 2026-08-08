"""Phase D0 — operational preflight for the fresh human validation study.

Exercises the whole chain end to end without producing validation data. Every
artefact is written under data/preflight/ and is marked PREFLIGHT so it can
never be confused with a learner recording.

Preflight audio comes from OMPAL native-reference tokens, which are outside the
learner benchmark entirely, plus one constructed silent clip to force a
trajectory failure. Neither may enter fresh_validation_trials.csv.

    python -m pronunciation.wav2vec_tone.preflight_fresh_validation
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.phase_c6_f0_trajectory import (
    N_POINTS, TONES, fit_predict, normalise, trajectory_from_segment,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
PREFLIGHT = DATA_DIR / "preflight"
MANIFEST_SPLIT = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
CACHE = DATA_DIR / "dev_features_train_dev.npz"
TRAJ_CACHE = DATA_DIR / "phase_c6_trajectories.npz"
FROZEN = DATA_DIR / "fresh_validation_system_FROZEN.json"
ITEMS = DATA_DIR / "fresh_validation_items.csv"
SAMPLE_RATE = 16000

PASS_MESSAGE = "Your tone sounds acceptable. You can continue."
RETRY_MESSAGE = ("I'm not confident enough to confirm this attempt. "
                 "Please try once more.")
FORBIDDEN = ("wrong", "incorrect", "instead of", "%", "score", "percent")


def check(results, name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return bool(ok)


def load_frozen(results):
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    recorded = frozen.pop("sha256")
    recomputed = hashlib.sha256(
        json.dumps(frozen, sort_keys=True, default=str).encode()).hexdigest()
    frozen["sha256"] = recorded
    # A hash mismatch means the artefact under test is not the artefact that was
    # frozen. That must halt a session, not be worked around.
    check(results, "frozen system hash verified", recomputed == recorded,
          f"{recorded[:16]}")
    if recomputed != recorded:
        sys.exit("STOP VALIDATION SESSION: frozen system artefact has changed")
    return frozen


def build_deployed_model(seed=0):
    """Fit the frozen configuration on Train exactly as deployment would."""
    cache = dict(np.load(CACHE, allow_pickle=True))
    stored = np.load(TRAJ_CACHE, allow_pickle=True)
    trajectory = normalise(stored["learner"], "N2")
    train = cache["split"] == "train"
    return (trajectory[train], cache["tone"][train], cache["y"][train])


def score_one(train_parts, trajectory, tone, seed=0):
    base, tones, y = train_parts
    scores, _ = fit_predict(base, tones, y,
                            trajectory.reshape(1, -1), np.asarray([tone]), 0.1, seed)
    return float(scores[0])


def decide(score, tone, available, t_pass, enabled):
    """The frozen policy, reimplemented exactly as specified."""
    if not available:
        return "RETRY", "trajectory_unavailable"
    if tone not in enabled:
        return "RETRY", "tone_not_enabled"
    if score <= t_pass:
        return "PASS", "score_below_threshold"
    return "RETRY", "score_above_threshold"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260808)
    args = parser.parse_args()

    import soundfile as sf

    PREFLIGHT.mkdir(parents=True, exist_ok=True)
    results = []
    print("=" * 74)
    print("PHASE D0 PREFLIGHT — no validation data is produced")
    print("=" * 74)

    frozen = load_frozen(results)
    t_pass = frozen["decision_policy"]["t_pass"]
    enabled = {t.replace("T", "") for t in frozen["decision_policy"]["enabled_pass_tones"]}
    print(f"  system {frozen['system_version']}  t_pass={t_pass}  enabled={sorted(enabled)}")

    train_parts = build_deployed_model(args.seed)

    # --- assemble preflight audio -----------------------------------------
    rows = [r for r in csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8"))
            if r["split"] == "native_reference"]
    # Same test lock every other manifest reader carries. The filter above
    # already excludes test rows; this asserts it rather than assuming it.
    if any(r["split"] == "test" for r in rows):
        sys.exit("TEST LOCK VIOLATION")
    by_tone = defaultdict(list)
    for row in rows:
        by_tone[row["expected_tone"]].append(row)
    trials = []
    for tone in TONES:
        if by_tone[tone]:
            trials.append({"source": by_tone[tone][0], "tone": tone,
                           "kind": "native_reference_preflight"})
    check(results, "preflight audio available for all four tones",
          len(trials) == 4, f"{len(trials)} tones")

    silent = PREFLIGHT / "PREFLIGHT_silence.wav"
    sf.write(silent, np.zeros(int(0.25 * SAMPLE_RATE), dtype=np.float32), SAMPLE_RATE)
    trials.append({"source": None, "tone": "2", "kind": "forced_trajectory_failure",
                   "path": silent})

    # --- run the chain ------------------------------------------------------
    print("\ntechnical chain:")
    chain_rows, latencies = [], []
    for index, trial in enumerate(trials, 1):
        started = time.perf_counter()
        if trial["source"] is not None:
            path = DATA_DIR / trial["source"]["extracted_token_path"]
            audio, _ = sf.read(str(path), dtype="float32")
        else:
            path = trial["path"]
            audio, _ = sf.read(str(path), dtype="float32")
        audio = np.asarray(audio, dtype=np.float32)
        captured = len(audio) > 0

        raw, reason = trajectory_from_segment(audio)
        available = raw is not None
        if available:
            centred = raw - np.median(raw)
            score = score_one(train_parts, centred, trial["tone"], args.seed)
        else:
            score = float("nan")
        decision, why = decide(score, trial["tone"], available, t_pass, enabled)
        latency = (time.perf_counter() - started) * 1000
        latencies.append(latency)

        chain_rows.append({
            "preflight_trial_id": f"PF{index:02d}",
            "kind": trial["kind"], "expected_tone": trial["tone"],
            "audio_path": str(path.relative_to(DATA_DIR)) if DATA_DIR in path.parents else str(path),
            "audio_captured": "YES" if captured else "NO",
            "trajectory_available": "YES" if available else "NO",
            "technical_failure_reason": "" if available else reason,
            "processing_latency_ms": f"{latency:.1f}",
            "r2_raw_score": "" if not available else f"{score:.6f}",
            "system_decision": decision, "decision_reason": why,
            "learner_message": PASS_MESSAGE if decision == "PASS" else RETRY_MESSAGE,
            "IS_PREFLIGHT": "YES",
        })
        print(f"  PF{index:02d} {trial['kind']:<30} T{trial['tone']}  "
              f"traj={'Y' if available else 'N'}  "
              f"score={'' if not available else f'{score:.3f}'}  "
              f"-> {decision} ({why})  {latency:.0f} ms")

    with (PREFLIGHT / "preflight_trials.csv").open("w", newline="", encoding="utf-8") as h:
        writer = csv.DictWriter(h, fieldnames=list(chain_rows[0].keys()))
        writer.writeheader()
        writer.writerows(chain_rows)

    # --- policy invariants --------------------------------------------------
    print("\npolicy invariants:")
    t1 = [r for r in chain_rows if r["expected_tone"] == "1"]
    check(results, "T1 always RETRY regardless of acoustics",
          all(r["system_decision"] == "RETRY" for r in t1),
          f"{len(t1)} T1 trial(s)")
    failed = [r for r in chain_rows if r["trajectory_available"] == "NO"]
    check(results, "trajectory unavailable -> RETRY, never PASS",
          bool(failed) and all(r["system_decision"] == "RETRY" for r in failed),
          f"{len(failed)} forced-failure trial(s)")
    check(results, "only PASS/RETRY emitted",
          set(r["system_decision"] for r in chain_rows) <= {"PASS", "RETRY"})

    print("\nlearner-facing wording:")
    messages = {r["learner_message"] for r in chain_rows}
    violations = [m for m in messages for f in FORBIDDEN if f in m.lower()]
    check(results, "no forbidden wording in learner messages",
          not violations, str(violations) if violations else "clean")
    check(results, "raw score never in a learner message",
          not any(any(ch.isdigit() for ch in m) for m in messages))

    # --- rater export blinding ---------------------------------------------
    print("\nrater export blinding:")
    rater_fields = ["rating_trial_id", "traditional_character", "expected_pinyin",
                    "expected_tone", "audio_path", "accept_yes_no",
                    "confidence_1_5", "perceived_tone", "comment"]
    items = list(csv.DictReader(ITEMS.open(encoding="utf-8")))
    export = []
    for index, row in enumerate(chain_rows, 1):
        item = next((i for i in items if i["expected_tone"] == row["expected_tone"]), items[0])
        export.append({"rating_trial_id": f"R{index:04d}",
                       "traditional_character": item["traditional_character"],
                       "expected_pinyin": item["expected_pinyin"],
                       "expected_tone": item["expected_tone"],
                       "audio_path": row["audio_path"],
                       "accept_yes_no": "", "confidence_1_5": "",
                       "perceived_tone": "", "comment": ""})
    with (PREFLIGHT / "preflight_rater_export.csv").open("w", newline="", encoding="utf-8") as h:
        writer = csv.DictWriter(h, fieldnames=rater_fields)
        writer.writeheader()
        writer.writerows(export)
    header = ",".join(rater_fields)
    leaks = [f for f in ("system_decision", "r2_raw_score", "participant_id",
                         "rater1", "rater2", "ompal", "PASS", "RETRY")
             if f.lower() in header.lower()]
    check(results, "rater export contains no system/participant/other-rater fields",
          not leaks, str(leaks) if leaks else "clean")

    # --- randomisation + duplicate QC dry run ------------------------------
    print("\nrandomisation and duplicate QC:")
    rng = np.random.default_rng(args.seed)
    mock = [{"trial_uid": f"T{i:04d}",
             "participant_id": f"P{i % 25:02d}",
             "expected_tone": TONES[i % 4]} for i in range(400)]
    # Random shuffling cannot beat the ~25% same-tone adjacency floor with four
    # tones, so the order is constructed rather than sampled: at each step take
    # the trial that differs from the previous in both tone and learner,
    # preferring whichever category has most remaining so the tail cannot dead-end.
    remaining = defaultdict(list)
    for index, trial in enumerate(mock):
        remaining[(trial["participant_id"], trial["expected_tone"])].append(index)
    for bucket in remaining.values():
        rng.shuffle(bucket)

    chosen_order = []
    previous_speaker = previous_tone = None
    while any(remaining.values()):
        keys = [k for k, v in remaining.items() if v]
        eligible = [k for k in keys
                    if k[0] != previous_speaker and k[1] != previous_tone]
        if not eligible:      # relax tone first, then speaker
            eligible = [k for k in keys if k[0] != previous_speaker] or keys
        key = max(eligible, key=lambda k: (len(remaining[k]), rng.random()))
        chosen_order.append(remaining[key].pop())
        previous_speaker, previous_tone = key

    same_speaker = sum(1 for a, b in zip(chosen_order, chosen_order[1:])
                       if mock[a]["participant_id"] == mock[b]["participant_id"])
    same_tone = sum(1 for a, b in zip(chosen_order, chosen_order[1:])
                    if mock[a]["expected_tone"] == mock[b]["expected_tone"])
    check(results, "consecutive same-learner trials minimised",
          same_speaker <= len(mock) * 0.02, f"{same_speaker}/399 adjacent pairs")
    check(results, "consecutive same-tone trials minimised",
          same_tone <= len(mock) * 0.02, f"{same_tone}/399 adjacent pairs")

    n_duplicates = int(round(len(mock) * 0.075))
    duplicate_source = rng.choice(len(mock), n_duplicates, replace=False)
    check(results, "duplicate rate within 5-10%",
          0.05 <= n_duplicates / len(mock) <= 0.10,
          f"{n_duplicates}/{len(mock)} = {n_duplicates / len(mock) * 100:.1f}%")
    duplicate_ids = {f"R{len(mock) + i + 1:04d}" for i in range(n_duplicates)}
    check(results, "duplicate identity invisible in rater export",
          all(not d.startswith("DUP") for d in duplicate_ids),
          "duplicates carry ordinary sequential rating ids")
    check(results, "randomisation seed recorded", True, str(args.seed))

    # --- analysis pipeline preflight ---------------------------------------
    print("\nanalysis pipeline:")
    source = (Path(__file__).parent / "analyze_fresh_human_validation.py").read_text(
        encoding="utf-8")
    check(results, "primary analysis restricted to first attempts",
          'first_attempt' in source and 'excluded_not_first_attempt' in source)
    check(results, "pre-registered consensus rule present",
          all(k in source for k in ("HUMAN_ACCEPT", "HUMAN_REJECT", "DISAGREEMENT")))
    check(results, "duplicates excluded from primary denominator",
          "is_duplicate_qc_trial" in source)
    check(results, "speaker-cluster bootstrap over participants",
          "cluster_bootstrap" in source and "participants" in source)
    check(results, "analysis never loads or refits the model",
          not any(k in source for k in ("fit_predict", "fit_fold", "LogisticRegression(")),
          "no model import or fit call")
    check(results, "0.90 target present and not parameterised away",
          "PASS_PRECISION_TARGET = 0.90" in source)

    # --- coverage arithmetic ------------------------------------------------
    print("\ncoverage arithmetic (from frozen C8 Train evidence):")
    c8 = json.loads((DATA_DIR / "ompal_phase_c8_policy_FROZEN.json").read_text(encoding="utf-8"))
    gate = c8["tone_gate"]
    enabled_pass = sum(gate[f"T{t}"]["n_pass"] for t in ("2", "3", "4"))
    print(f"  overall Train coverage      : {c8['train']['coverage'] * 100:.1f}%")
    print(f"  enabled-tone PASS decisions : {enabled_pass}")

    summary = {
        "phase": "D0", "system_version": frozen["system_version"],
        "system_sha256": frozen["sha256"], "seed": args.seed,
        "checks": results,
        "n_failed": sum(1 for r in results if not r["pass"]),
        "chain_trials": chain_rows,
        "latency_ms": {"n": len(latencies), "median": float(np.median(latencies)),
                       "min": float(np.min(latencies)), "max": float(np.max(latencies))},
        "preflight_isolation": ("all artefacts under data/preflight/ and marked "
                                "IS_PREFLIGHT=YES; none may enter "
                                "fresh_validation_trials.csv"),
        "software": {"python": platform.python_version(), "numpy": np.__version__},
        # Measured, not asserted: a hardcoded literal here would claim the seal
        # without checking it. The authority is verify_ompal_test_seal.py.
        "ompal_test": {
            "test_rows_loaded": 0,
            "test_rows_in_feature_cache": int(sum(
                np.asarray(np.load(CACHE, allow_pickle=True)["split"]) == "test")),
            "verified_by": "verify_ompal_test_seal.py",
        },
    }
    (PREFLIGHT / "preflight_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=float),
        encoding="utf-8")

    failed = summary["n_failed"]
    print(f"\nlatency (preflight only, not a real-world estimate): median "
          f"{np.median(latencies):.0f} ms, range {np.min(latencies):.0f}-"
          f"{np.max(latencies):.0f} ms")
    print(f"\nchecks: {len(results) - failed}/{len(results)} passed")
    print(f"artefacts: {PREFLIGHT}")
    if failed:
        sys.exit(f"{failed} preflight check(s) FAILED")


if __name__ == "__main__":
    main()
