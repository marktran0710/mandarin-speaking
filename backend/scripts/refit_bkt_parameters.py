"""Create an offline, versioned BKT parameter candidate from the ledger.

This command is safe to invoke from an external scheduler.  It uses cadence
and new-evidence gates by default, stores an immutable candidate, and never
changes the learner-serving model.  Use ``--force`` for a deliberate pilot or
synthetic recovery check.

Examples, run from ``backend/``::

    python -m scripts.refit_bkt_parameters --source synthetic --force
    python -m scripts.refit_bkt_parameters --source real
"""

from __future__ import annotations

import argparse
import json

from analytics.bkt_calibration_store import run_calibration_candidate
from database import connect_db


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=("real", "synthetic"),
        default="real",
        help="Ledger evidence origin. Synthetic candidates are never promotable.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass only the scheduling cadence; evidence and promotion gates still apply.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=80,
        help="Maximum L-BFGS-B iterations per fit.",
    )
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be at least 1")

    with connect_db() as db:
        result = run_calibration_candidate(
            db,
            args.source,
            force=args.force,
            iterations=args.iterations,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
