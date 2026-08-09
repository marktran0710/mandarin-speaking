"""Validate an annotation CSV/JSONL before it is used by the KPI gate."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarking.annotation_schema import validate_annotation_row


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"line {line_number} is not a JSON object")
        rows.append(value)
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="CSV or JSONL annotation manifest")
    parser.add_argument("--require-gold", action="store_true", help="Require labels/boundaries/QC needed for sealed scoring")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON diagnostics")
    args = parser.parse_args(argv)
    try:
        rows = _load_rows(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    diagnostics: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 2):
        errors = validate_annotation_row(row, require_gold=args.require_gold)
        if errors:
            diagnostics.append({"row": index, "annotation_id": row.get("annotation_id", ""), "errors": errors})
    payload = {"rows": len(rows), "invalid_rows": len(diagnostics), "valid": not diagnostics, "diagnostics": diagnostics}
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Rows: {len(rows)}")
        print(f"Invalid rows: {len(diagnostics)}")
        for item in diagnostics[:20]:
            print(f"Row {item['row']}: {'; '.join(item['errors'])}")
        if len(diagnostics) > 20:
            print(f"... and {len(diagnostics) - 20} more rows")
    return 0 if not diagnostics else 1


if __name__ == "__main__":
    raise SystemExit(main())
