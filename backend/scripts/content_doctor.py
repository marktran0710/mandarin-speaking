"""Generate the unified, read-only content inventory report.

Run from the repository root or ``backend/``::

    python backend/scripts/content_doctor.py
    python -m scripts.content_doctor --fail-on-errors

Only the JSON report is written; curriculum rows and media are never changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.media as media_service  # noqa: E402
from services.content_inventory import build_content_inventory_from_database  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/content-doctor.json"),
        help="JSON report path (default: output/content-doctor.json)",
    )
    parser.add_argument(
        "--fail-on-errors",
        action="store_true",
        help="Exit 1 when the report contains error-severity findings.",
    )
    args = parser.parse_args(argv)

    report = build_content_inventory_from_database(upload_dir=media_service.UPLOAD_DIR)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = report["summary"]
    print(
        json.dumps(
            {
                "stories": summary["stories"],
                "findings": summary["findings"],
                "errors": summary["findingsBySeverity"].get("error", 0),
                "orphanFiles": summary["orphanFiles"],
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return int(args.fail_on_errors and summary["findingsBySeverity"].get("error", 0) > 0)


if __name__ == "__main__":
    raise SystemExit(main())
