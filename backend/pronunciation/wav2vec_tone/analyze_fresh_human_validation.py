"""Analysis pipeline for the fresh human validation study (Phase D).

Written and frozen BEFORE any data exists. It fabricates nothing: given no
completed trials file it exits with a clear message rather than producing a
placeholder result.

Two rules are enforced in code, not just documented:

* The fresh human labels are validation data. Nothing here refits, retunes or
  reads the model; the script only scores decisions that were already made.
* Every primary interval is a speaker-cluster bootstrap over PARTICIPANTS.
  ~400 productions from ~25 learners are not 400 independent observations, and
  a token bootstrap would give intervals several times too narrow.

    python -m pronunciation.wav2vec_tone.analyze_fresh_human_validation \\
        --trials data/fresh_validation_trials.csv \\
        --participants data/fresh_validation_participants.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
FROZEN = DATA_DIR / "fresh_validation_system_FROZEN.json"

PASS_PRECISION_TARGET = 0.90      # pre-specified; never moved after results
BOOTSTRAP = 4000
TONES = ("1", "2", "3", "4")

# Pre-registered missing-data rules, fixed before collection.
MISSING_RULES = {
    "missing_one_rater": "trial excluded from strict-consensus analysis; "
                         "reported in the full-sample sensitivity analysis if "
                         "an adjudicated label exists",
    "missing_both_raters": "trial excluded from all human-comparison analyses; "
                           "counted in the trial-flow table",
    "corrupt_audio": "trial excluded from human comparison; counted as a "
                     "technical failure",
    "system_technical_failure": "system_decision must be RETRY; retained in "
                                "coverage denominators, excluded from PASS "
                                "precision numerator and denominator",
    "participant_withdrawal": "all of that participant's trials excluded; "
                              "participant counted in the flow table",
}


def die(message: str) -> None:
    sys.exit(f"[fresh-validation] {message}")


def load(path: Path, what: str) -> list[dict]:
    if not path.exists():
        die(f"{what} not found at {path}. No data has been collected yet — this "
            f"script does not generate placeholder results.")
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        die(f"{what} at {path} is empty.")
    return rows


def yes(value) -> bool | None:
    text = str(value).strip().upper()
    if text in ("YES", "Y", "1", "TRUE", "ACCEPT"):
        return True
    if text in ("NO", "N", "0", "FALSE", "REJECT"):
        return False
    return None


def cluster_bootstrap(values, participants, statistic, seed=0, draws=BOOTSTRAP):
    """Resample participants with replacement; recompute the statistic."""
    participants = np.asarray(participants)
    unique = np.array(sorted(set(participants.tolist())))
    index_by = {p: np.flatnonzero(participants == p) for p in unique}
    rng = np.random.default_rng(seed)
    draws_out = []
    for _ in range(draws):
        drawn = rng.choice(unique, len(unique), replace=True)
        indices = np.concatenate([index_by[p] for p in drawn])
        result = statistic(indices)
        if result is not None and np.isfinite(result):
            draws_out.append(result)
    if not draws_out:
        return None
    return float(np.percentile(draws_out, 2.5)), float(np.percentile(draws_out, 97.5))


def human_reliability(rows) -> dict:
    """Rater agreement, reported BEFORE any system comparison."""
    pairs = [(yes(r["rater1_accept"]), yes(r["rater2_accept"])) for r in rows]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    if not pairs:
        return {"n_pairs": 0, "note": "no trial has both raters"}
    agree = sum(1 for a, b in pairs if a == b)
    total = len(pairs)
    observed = agree / total
    first = Counter(a for a, _ in pairs)
    second = Counter(b for _, b in pairs)
    expected = sum((first[v] / total) * (second[v] / total) for v in (True, False))
    kappa = ((observed - expected) / (1 - expected)) if expected < 1 else float("nan")
    both_yes = sum(1 for a, b in pairs if a and b)
    both_no = sum(1 for a, b in pairs if not a and not b)
    return {
        "n_pairs": total,
        "raw_agreement": observed,
        "cohens_kappa": float(kappa) if np.isfinite(kappa) else None,
        "positive_agreement": (2 * both_yes / (sum(a for a, _ in pairs)
                                               + sum(b for _, b in pairs)))
        if (sum(a for a, _ in pairs) + sum(b for _, b in pairs)) else None,
        "negative_agreement": (2 * both_no / (sum(not a for a, _ in pairs)
                                              + sum(not b for _, b in pairs)))
        if (sum(not a for a, _ in pairs) + sum(not b for _, b in pairs)) else None,
        "rater1_yes_rate": float(np.mean([a for a, _ in pairs])),
        "rater2_yes_rate": float(np.mean([b for _, b in pairs])),
        "interpretation_note": ("read kappa together with raw agreement and the "
                                "marginals; kappa is depressed at high YES "
                                "prevalence and a low value does not by itself "
                                "invalidate the human criterion"),
    }


def consensus(row) -> str:
    a, b = yes(row["rater1_accept"]), yes(row["rater2_accept"])
    if a is None or b is None:
        return "INCOMPLETE"
    if a and b:
        return "HUMAN_ACCEPT"
    if not a and not b:
        return "HUMAN_REJECT"
    return "DISAGREEMENT"


def pass_precision_block(rows, label, seed) -> dict:
    """PASS precision — the primary metric for a one-sided positive claim."""
    passed = [r for r in rows if r["system_decision"].strip().upper() == "PASS"]
    if not passed:
        return {"label": label, "n_pass": 0,
                "note": "no PASS decisions in this subset"}
    accepted = [r for r in passed if r["_consensus"] == "HUMAN_ACCEPT"]
    participants = [r["participant_id"] for r in passed]
    flags = np.asarray([r["_consensus"] == "HUMAN_ACCEPT" for r in passed])

    def statistic(indices):
        subset = flags[indices]
        return float(subset.mean()) if len(subset) else None

    ci = cluster_bootstrap(flags, participants, statistic, seed)
    return {
        "label": label, "n_pass": len(passed),
        "true_pass": len(accepted), "false_pass": len(passed) - len(accepted),
        "pass_precision": len(accepted) / len(passed),
        "false_pass_rate": 1 - len(accepted) / len(passed),
        "ci_95_cluster_bootstrap": ci,
        "n_participants": len(set(participants)),
        "n_productions": len(passed),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", default=str(DATA_DIR / "fresh_validation_trials.csv"))
    parser.add_argument("--participants",
                        default=str(DATA_DIR / "fresh_validation_participants.csv"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default=str(DATA_DIR / "fresh_validation_results.json"))
    args = parser.parse_args()

    if not FROZEN.exists():
        die("frozen system record missing; refusing to analyse an unspecified system")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    print(f"validating {frozen['system_version']} "
          f"(sha256 {frozen['sha256'][:16]}), t_pass={frozen['decision_policy']['t_pass']}")

    participants = load(Path(args.participants), "participants file")
    trials = load(Path(args.trials), "trials file")

    withdrawn = {p["participant_id"] for p in participants
                 if str(p.get("withdrew", "")).strip().upper() in ("YES", "TRUE", "1")}
    flow = Counter({"trials_total": len(trials)})
    usable = []
    for row in trials:
        if row["participant_id"] in withdrawn:
            flow["excluded_withdrawn"] += 1
            continue
        if str(row.get("first_attempt", "")).strip().upper() not in ("YES", "TRUE", "1"):
            flow["excluded_not_first_attempt"] += 1
            continue
        flow["first_attempts"] += 1
        row["_consensus"] = consensus(row)
        usable.append(row)

    if not usable:
        die("no usable first-attempt trials after applying the pre-registered "
            "exclusion rules")

    for row in usable:
        flow[f"consensus_{row['_consensus']}"] += 1

    reliability = human_reliability(usable)
    print(f"\nHUMAN RELIABILITY FIRST (n={reliability.get('n_pairs')}): "
          f"raw agreement {reliability.get('raw_agreement')}, "
          f"kappa {reliability.get('cohens_kappa')}")

    strict = [r for r in usable if r["_consensus"] in ("HUMAN_ACCEPT", "HUMAN_REJECT")]
    adjudicated = []
    for row in usable:
        if row["_consensus"] == "DISAGREEMENT" and yes(row.get("adjudicated_accept")) is not None:
            row = {**row, "_consensus": "HUMAN_ACCEPT" if yes(row["adjudicated_accept"])
                   else "HUMAN_REJECT"}
        if row["_consensus"] in ("HUMAN_ACCEPT", "HUMAN_REJECT"):
            adjudicated.append(row)

    primary = pass_precision_block(strict, "strict_consensus", args.seed)
    sensitivity = pass_precision_block(adjudicated, "full_sample_adjudicated", args.seed)

    # --- coverage, confusion, tone and speaker breakdowns -------------------
    decisions = Counter(r["system_decision"].strip().upper() for r in usable)
    coverage = decisions["PASS"] / len(usable)
    confusion = Counter((r["system_decision"].strip().upper(), r["_consensus"])
                        for r in strict)

    by_tone = {}
    for tone in TONES:
        subset = [r for r in strict if str(r["expected_tone"]).strip() == tone]
        all_tone = [r for r in usable if str(r["expected_tone"]).strip() == tone]
        block = pass_precision_block(subset, f"T{tone}", args.seed)
        block.update({
            "n_recordings": len(all_tone),
            "system_pass": sum(1 for r in all_tone
                               if r["system_decision"].strip().upper() == "PASS"),
            "system_retry": sum(1 for r in all_tone
                                if r["system_decision"].strip().upper() == "RETRY"),
            "human_accept": sum(1 for r in subset if r["_consensus"] == "HUMAN_ACCEPT"),
            "human_reject": sum(1 for r in subset if r["_consensus"] == "HUMAN_REJECT"),
            "coverage": (sum(1 for r in all_tone
                             if r["system_decision"].strip().upper() == "PASS")
                         / len(all_tone)) if all_tone else None,
        })
        by_tone[f"T{tone}"] = block

    by_participant = {}
    for participant in sorted({r["participant_id"] for r in usable}):
        subset = [r for r in usable if r["participant_id"] == participant]
        passed = [r for r in subset if r["system_decision"].strip().upper() == "PASS"]
        strict_passed = [r for r in passed if r["_consensus"] == "HUMAN_ACCEPT"]
        by_participant[participant] = {
            "n": len(subset), "n_pass": len(passed),
            "coverage": len(passed) / len(subset),
            "pass_precision": (len(strict_passed) / len(passed)) if passed else None,
        }

    # --- technical robustness ----------------------------------------------
    latencies = np.asarray([float(r["processing_latency_ms"]) for r in usable
                            if str(r.get("processing_latency_ms", "")).strip()
                            not in ("", "NA")], dtype=float)
    technical = {
        "audio_captured_rate": float(np.mean([
            str(r.get("audio_captured", "")).strip().upper() in ("YES", "TRUE", "1")
            for r in usable])),
        "trajectory_available_rate": float(np.mean([
            str(r.get("trajectory_available", "")).strip().upper() in ("YES", "TRUE", "1")
            for r in usable])),
        "technical_failure_reasons": dict(Counter(
            r.get("technical_failure_reason", "").strip() for r in usable
            if r.get("technical_failure_reason", "").strip())),
        "latency_ms": {
            "n": int(len(latencies)),
            "median": float(np.median(latencies)) if len(latencies) else None,
            "iqr": [float(np.percentile(latencies, 25)),
                    float(np.percentile(latencies, 75))] if len(latencies) else None,
            "p95": float(np.percentile(latencies, 95)) if len(latencies) else None,
        },
    }

    retries = defaultdict(int)
    for row in trials:
        if row["participant_id"] in withdrawn:
            continue
        try:
            if int(row.get("attempt_number", 1)) > 1:
                retries[row["participant_id"]] += 1
        except ValueError:
            pass
    retry_stats = {
        "total_retry_attempts": int(sum(retries.values())),
        "participants_with_any_retry": len(retries),
        "note": ("Improvement across immediate retries may reflect practice, "
                 "repetition, increased attention, or feedback response and "
                 "cannot establish learning effectiveness."),
    }

    duplicates = [r for r in trials
                  if str(r.get("is_duplicate_qc_trial", "")).strip().upper()
                  in ("YES", "TRUE", "1")]
    duplicate_block = {"n_duplicate_trials": len(duplicates)}
    if duplicates:
        pairs = []
        by_uid = {r.get("duplicate_of_trial_id"): r for r in trials}
        for row in duplicates:
            original = by_uid.get(row.get("duplicate_of_trial_id"))
            if original:
                for rater in ("rater1_accept", "rater2_accept"):
                    a, b = yes(row.get(rater)), yes(original.get(rater))
                    if a is not None and b is not None:
                        pairs.append(a == b)
        if pairs:
            duplicate_block["intra_rater_agreement"] = float(np.mean(pairs))
            duplicate_block["n_compared"] = len(pairs)

    verdict_line = None
    if "pass_precision" in primary:
        ci = primary.get("ci_95_cluster_bootstrap")
        meets = primary["pass_precision"] >= PASS_PRECISION_TARGET
        verdict_line = (
            f"PASS precision {primary['pass_precision']:.3f}"
            + (f", 95% cluster CI [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "")
            + f" — pre-specified target {PASS_PRECISION_TARGET:.2f}: "
            + ("MET" if meets else "NOT MET")
            + ". The threshold is frozen; a shortfall is the finding, not a "
              "reason to retune.")

    results = {
        "system_version": frozen["system_version"],
        "system_sha256": frozen["sha256"],
        "participant_flow": {"enrolled": len(participants),
                             "withdrawn": len(withdrawn),
                             "analysed": len({r["participant_id"] for r in usable})},
        "trial_flow": dict(flow),
        "human_reliability_reported_first": reliability,
        "consensus_distribution": dict(Counter(r["_consensus"] for r in usable)),
        "primary_strict_consensus": primary,
        "sensitivity_full_sample": sensitivity,
        "coverage": {"pass_coverage": coverage,
                     "retry_rate": 1 - coverage,
                     "decisions": dict(decisions)},
        "confusion_system_vs_human": {f"{k[0]}|{k[1]}": v for k, v in confusion.items()},
        "by_tone": by_tone, "by_participant": by_participant,
        "technical": technical, "retry": retry_stats,
        "qc_duplicates": duplicate_block,
        "missing_data_rules": MISSING_RULES,
        "pre_specified_target": PASS_PRECISION_TARGET,
        "verdict": verdict_line,
        "no_model_modification": ("validation labels were not used to refit or "
                                  "retune anything; this script never loads the "
                                  "model"),
    }
    Path(args.out).write_text(json.dumps(results, indent=2, ensure_ascii=False,
                                         default=float), encoding="utf-8")

    print(f"\nPASS coverage {coverage * 100:.1f}%  "
          f"({decisions['PASS']} of {len(usable)} first attempts)")
    if "pass_precision" in primary:
        print(verdict_line)
    for tone, block in by_tone.items():
        print(f"  {tone}: n={block['n_recordings']} pass={block['system_pass']} "
              f"precision={block.get('pass_precision')}")
    print(f"\nresults: {args.out}")


if __name__ == "__main__":
    main()
