"""Audit a CSV/JSONL speech benchmark for split leakage before training/evaluation."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarking.leakage_guard import audit_rows


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number} is not a JSON object")
            rows.append(value)
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--require-sealed-test", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional JSON audit artifact")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    try:
        audit = audit_rows(_load_rows(args.manifest), require_sealed_test=args.require_sealed_test)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    payload = audit.as_dict()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Rows: {payload['row_count']}")
        print(f"Manifest SHA-256: {payload['manifest_sha256']}")
        print(f"Leakage audit: {'PASS' if payload['passed'] else 'FAIL'}")
        for problem in payload["errors"]:
            print(f"ERROR: {problem}")
        for warning in payload["warnings"]:
            print(f"WARNING: {warning}")
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
