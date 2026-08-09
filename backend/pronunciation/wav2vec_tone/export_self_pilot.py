"""Export the researcher self-pilot log as a descriptive summary.

Descriptive only. PASS and RETRY counts here are workflow observations, not
accuracy: the researcher is not an independent validation criterion, so no
number in this file may be read as evidence about pronunciation assessment.
`forbid_validity_metrics` enforces that on the way out.

    python -m pronunciation.wav2vec_tone.export_self_pilot
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.self_pilot import (  # noqa: E402
    CHALLENGE_PLAN, RUN_A, RUN_B, RUN_C, RUN_TECHNICAL, SUMMARY_JSON,
    TRIALS_CSV, forbid_validity_metrics, load_items, protected_artefact_digests,
    read_trials,
)

NOT_VALIDATION = (
    "SELF-PILOT ONLY. The researcher is not an independent validation "
    "criterion. Nothing here is accuracy, PASS precision, sensitivity, "
    "specificity, human-system agreement or kappa, and none of these rows may "
    "enter the fresh human validation, its PASS-precision denominator, or any "
    "inter-rater analysis."
)


def float_or_none(value: str):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarise(trials: list[dict]) -> dict:
    runs = Counter(row.get("run", "") for row in trials)
    decisions = Counter(row.get("system_decision", "") for row in trials)
    failures = Counter(row.get("failure_code", "") for row in trials if
                       row.get("failure_code") not in ("", "ok"))
    trajectory = Counter(row.get("trajectory_available", "") for row in trials)

    latencies = [v for v in (float_or_none(row.get("latency_ms", ""))
                             for row in trials) if v is not None]
    values = np.asarray(latencies) if latencies else np.asarray([])

    # T1 gate: any PASS on a T1 item is a technical failure, full stop.
    t1_rows = [row for row in trials if row.get("expected_tone", "").upper()
               in ("1", "T1")]
    t1_violations = [row["trial_uid"] for row in t1_rows
                     if row.get("system_decision") == "PASS"]

    # Unsafe PASS: a PASS without a usable trajectory or with a failure code.
    unsafe = [row["trial_uid"] for row in trials
              if row.get("system_decision") == "PASS"
              and (row.get("trajectory_available") != "YES"
                   or row.get("failure_code") not in ("", "ok"))]

    # Per-item repeat consistency is a WORKFLOW observation: it says whether the
    # same person recording the same prompt twice got the same verdict. It is
    # not model accuracy and is reported as raw counts, never as a rate.
    by_item: dict[str, list[str]] = {}
    for row in trials:
        if row.get("run") in (RUN_A, RUN_B):
            by_item.setdefault(row.get("item_id", ""), []).append(
                row.get("system_decision", ""))
    repeat_pairs = {item: verdicts for item, verdicts in by_item.items()
                    if len(verdicts) >= 2}
    same = sum(1 for verdicts in repeat_pairs.values()
               if len(set(verdicts)) == 1)

    challenge_rows = [row for row in trials if row.get("run") == RUN_C]

    summary = {
        "_note": NOT_VALIDATION,
        "phase": "SELF_PILOT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "PILOT_ONLY": True,
        "RESEARCHER_SELF_TEST": True,
        "is_validation_data": False,
        "eligible_for_human_validation_analysis": False,
        "system": {
            "scientific_version": next((row.get("scientific_version")
                                        for row in trials if row.get("scientific_version")), None),
            "deployment_version": next((row.get("deployment_version")
                                        for row in trials if row.get("deployment_version")), None),
            "audio_contract_version": next((row.get("audio_contract_version")
                                            for row in trials if row.get("audio_contract_version")), None),
            "fitted_model_sha256": next((row.get("fitted_model_sha256")
                                         for row in trials if row.get("fitted_model_sha256")), None),
        },
        "totals": {
            "total_recordings": len(trials),
            "per_run": dict(runs),
            "run_A_natural": runs.get(RUN_A, 0),
            "run_B_repeat": runs.get(RUN_B, 0),
            "run_C_challenge": runs.get(RUN_C, 0),
            "technical_cases": runs.get(RUN_TECHNICAL, 0),
        },
        "processing": {
            "trajectory_available_yes": trajectory.get("YES", 0),
            "trajectory_available_no": trajectory.get("NO", 0),
            "processing_successes": sum(1 for row in trials
                                        if row.get("failure_code") in ("", "ok")),
            "technical_failures": dict(failures),
        },
        "decision_counts_descriptive_only": {
            "PASS": decisions.get("PASS", 0),
            "RETRY": decisions.get("RETRY", 0),
            "_warning": ("descriptive workflow counts; NOT accuracy and NOT "
                         "PASS precision"),
        },
        "safety": {
            "t1_gate_violations": len(t1_violations),
            "t1_gate_violation_ids": t1_violations,
            "unsafe_pass_count": len(unsafe),
            "unsafe_pass_ids": unsafe,
        },
        "latency_ms": {
            "n": int(values.size),
            "median": float(np.median(values)) if values.size else None,
            "p95": float(np.percentile(values, 95)) if values.size else None,
            "scope": ("server-side inference latency logged per trial; excludes "
                      "capture and network, so not an end-user estimate"),
        },
        "repeat_workflow_observation": {
            "items_with_two_or_more_attempts": len(repeat_pairs),
            "items_where_verdict_was_identical": same,
            "items_where_verdict_differed": len(repeat_pairs) - same,
            "_warning": ("a workflow observation about repeat recordings; it is "
                         "NOT reliability, NOT agreement and NOT accuracy"),
        },
        "challenge_observations": {
            "planned": len(CHALLENGE_PLAN),
            "recorded": len(challenge_rows),
            "by_challenge_type": dict(Counter(
                row.get("challenge_type", "") for row in challenge_rows)),
            "decisions": dict(Counter(
                row.get("system_decision", "") for row in challenge_rows)),
            "_warning": ("diagnostic probes; the manipulations are NOT verified "
                         "Mandarin tone errors and no accuracy may be derived"),
        },
        "item_coverage": {
            "items_defined": len(load_items()),
            "items_attempted": len({row.get("item_id") for row in trials
                                    if row.get("item_id")}),
            "teacher_approved": False,
            "_note": ("items remain unapproved; the self-pilot does not advance "
                      "the D2 item-approval gate"),
        },
        "protected_artefacts_untouched": protected_artefact_digests(),
        "software": {"python": platform.python_version(), "numpy": np.__version__},
    }
    forbid_validity_metrics(summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    trials = read_trials()
    summary = summarise(trials)
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                            encoding="utf-8")

    if args.quiet:
        return

    print("=" * 72)
    print("RESEARCHER SELF-PILOT SUMMARY -- descriptive only, not validation")
    print("=" * 72)
    print(f"  trials file      : {TRIALS_CSV}")
    print(f"  total recordings : {summary['totals']['total_recordings']}")
    print(f"  per run          : {summary['totals']['per_run']}")
    print(f"  trajectory yes/no: {summary['processing']['trajectory_available_yes']}"
          f"/{summary['processing']['trajectory_available_no']}")
    print(f"  PASS / RETRY     : {summary['decision_counts_descriptive_only']['PASS']}"
          f" / {summary['decision_counts_descriptive_only']['RETRY']}"
          "   (descriptive; NOT accuracy)")
    print(f"  T1 gate breaches : {summary['safety']['t1_gate_violations']}")
    print(f"  unsafe PASS      : {summary['safety']['unsafe_pass_count']}")
    print(f"  technical failure: {summary['processing']['technical_failures'] or 'none'}")
    if summary["latency_ms"]["median"] is not None:
        print(f"  latency ms       : median {summary['latency_ms']['median']:.1f}, "
              f"p95 {summary['latency_ms']['p95']:.1f}")
    print(f"\n  {NOT_VALIDATION}")
    print(f"\n  written: {SUMMARY_JSON}")


if __name__ == "__main__":
    main()
