"""Fail CI when a Mandarin tone benchmark is unsafe for student release."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from benchmarking.tone_release_gate import (
    ToneReleaseThresholds,
    evaluate_tone_release_gate,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="benchmark JSON report to verify")
    parser.add_argument("--min-recordings", type=int, default=800)
    parser.add_argument("--min-speakers", type=int, default=40)
    parser.add_argument("--min-accuracy", type=float, default=0.85)
    parser.add_argument("--min-kappa", type=float, default=0.70)
    parser.add_argument("--min-tone-f1", type=float, default=0.80)
    parser.add_argument("--max-false-positive-rate", type=float, default=0.05)
    parser.add_argument("--max-mae", type=float, default=12.0)
    parser.add_argument("--min-spearman", type=float, default=0.75)
    return parser


def _format_actual(actual: float | None) -> str:
    return "missing/invalid" if actual is None else f"{actual:g}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    report_path = Path(args.report)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except OSError as error:
        print(f"ERROR: cannot read benchmark report {report_path}: {error}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"ERROR: invalid JSON in benchmark report {report_path}: {error}", file=sys.stderr)
        return 2

    thresholds = ToneReleaseThresholds(
        min_recording_count=args.min_recordings,
        min_speaker_count=args.min_speakers,
        min_accuracy=args.min_accuracy,
        min_kappa=args.min_kappa,
        min_per_tone_f1=args.min_tone_f1,
        max_false_positive_rate=args.max_false_positive_rate,
        max_mean_absolute_error=args.max_mae,
        min_spearman_correlation=args.min_spearman,
    )
    try:
        result = evaluate_tone_release_gate(report, thresholds)
    except TypeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    for check in result.checks:
        status = "PASS" if check.passed else "FAIL"
        line = (
            f"[{status}] {check.name}: {_format_actual(check.actual)} "
            f"{check.operator} {check.threshold:g}"
        )
        if check.detail:
            line += f" ({check.detail})"
        print(line)

    if result.passed:
        print("RELEASE GATE PASSED: benchmark evidence meets every required criterion.")
        return 0
    failed = sum(not check.passed for check in result.checks)
    print(
        f"RELEASE GATE FAILED: {failed}/{len(result.checks)} checks failed. "
        "Do not release tone feedback to students.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
