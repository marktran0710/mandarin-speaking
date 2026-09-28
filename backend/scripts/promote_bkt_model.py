"""Inspect, activate or deactivate the BKT parameters that serve learners.

Activation points serving at one immutable candidate created by
``scripts.refit_bkt_parameters`` and rebuilds every learner's cached mastery.
The database only accepts candidates that are format-aware, fitted on real
learner evidence and passed every promotion gate. Deactivation returns serving
to the engineering defaults in ``analytics/learner_model/bkt/core.py``.

Serving processes pick up a change within BKT_ACTIVE_CONFIG_TTL_SECONDS
(default 30s).

Examples, run from ``backend/``::

    python -m scripts.promote_bkt_model status
    python -m scripts.promote_bkt_model candidates
    python -m scripts.promote_bkt_model activate bkt-real-candidate-... --reason "Spring pilot fit"
    python -m scripts.promote_bkt_model deactivate
"""

from __future__ import annotations

import argparse

from analytics.learner_model.bkt.deployment import (
    deactivate_deployment,
    load_active_deployment,
    promote_model_version,
)
from db import connect_db


def _status(db) -> None:
    active = load_active_deployment(db)
    if not active:
        print("No active deployment: learners are served the engineering defaults in bkt/core.py.")
        return
    print(f"Active: {active['model_version']} (since {active['updated_at']}, evidence {active['evidence_origin']})")
    for label, key in (
        ("P(L0)", "initial_mastery"), ("P(T)", "learn_rate"), ("MCQ guess", "guess_rate"),
        ("MCQ slip", "slip_rate"), ("Typed guess", "guess_rate_typed"), ("Typed slip", "slip_rate_typed"),
    ):
        print(f"  {label:<12} {active[key]}")


def _candidates(db) -> None:
    rows = db.execute(
        """
        SELECT model.version, model.evidence_origin, model.model_scope, fit.promotable,
               fit.status, fit.response_count, fit.student_count, fit.completed_at
        FROM bkt_model_versions AS model
        JOIN bkt_model_fit_runs AS fit ON fit.id = model.fit_run_id
        ORDER BY fit.completed_at DESC NULLS LAST
        LIMIT 20
        """
    ).fetchall()
    for row in rows:
        flag = "promotable" if row["promotable"] else "not promotable"
        print(
            f"{row['version']}  {row['evidence_origin']:<14} {row['model_scope'] or 'global'}  "
            f"{row['response_count']} answers / {row['student_count']} students  {flag}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show the active deployment.")
    commands.add_parser("candidates", help="List recent candidates.")
    activate = commands.add_parser("activate", help="Serve a promotable candidate.")
    activate.add_argument("model_version")
    activate.add_argument("--reason", required=True)
    commands.add_parser("deactivate", help="Return to the engineering defaults.")
    args = parser.parse_args()

    with connect_db() as db:
        if args.command == "status":
            _status(db)
        elif args.command == "candidates":
            _candidates(db)
        elif args.command == "activate":
            result = promote_model_version(db, args.model_version, args.reason)
            print(f"Activated {result['modelVersion']} (previous: {result['previousModelVersion'] or 'defaults'}).")
            print("Every learner's cached mastery was rebuilt with the new parameters.")
        else:
            result = deactivate_deployment(db)
            print(f"Deactivated {result['previousModelVersion'] or '(nothing was active)'}; serving the defaults.")


if __name__ == "__main__":
    main()
