"""Run the unified character/phone/tone KPI gate and emit audit artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarking.kpi_release_gate import build_kpi_report, evaluate_kpi_gate, write_kpi_artifacts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", help="Unified KPI report JSON")
    parser.add_argument("--rows", help="Per-character JSONL/JSON rows; can build the report when --report is omitted")
    parser.add_argument("--model-version", default="", help="Frozen model version for row-derived reports")
    parser.add_argument("--schema-version", default="", help="Frozen schema version for row-derived reports")
    parser.add_argument("--sealed-test-set", action="store_true", help="Mark the supplied rows as a sealed test set")
    parser.add_argument("--output-dir", default="backend/reports/kpi_gate", help="Artifact directory")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print machine-readable gate JSON")
    return parser


def _load_rows(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    source = Path(path)
    if source.suffix.lower() == ".csv":
        with source.open(encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    raw = source.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [row for row in parsed if isinstance(row, dict)]
        if isinstance(parsed, dict) and isinstance(parsed.get("rows"), list):
            return [row for row in parsed["rows"] if isinstance(row, dict)]
        return []
    except json.JSONDecodeError:
        return [json.loads(line) for line in raw.splitlines() if line.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        rows = _load_rows(args.rows)
        if args.report:
            report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        elif rows:
            provenance = {
                "model_version": args.model_version,
                "schema_version": args.schema_version,
            }
            report = build_kpi_report(rows, provenance)
            report["test_set"] = {"sealed": args.sealed_test_set}
        else:
            raise ValueError("provide --report or --rows")
        result = evaluate_kpi_gate(report)
        artifacts = write_kpi_artifacts(report, rows, args.output_dir)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    payload = result.as_dict() | {"artifacts": artifacts}
    if args.json_output:
        print(json.dumps(payload, indent=2))
    else:
        for check in result.checks:
            actual = "missing" if check.actual is None else f"{check.actual:g}"
            print(f"[{('PASS' if check.passed else 'FAIL')}] {check.name}: {actual} {check.operator} {check.threshold:g}")
        print(f"KPI STATUS: {result.status}")
        print(f"RELEASE STATUS: {result.release_status}")
        print(f"JSON ARTIFACT: {artifacts['json']}")
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
