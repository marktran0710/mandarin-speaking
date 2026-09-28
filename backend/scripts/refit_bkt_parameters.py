"""Create an offline, versioned BKT parameter candidate from the ledger.

This command is safe to invoke from an external scheduler.  It uses cadence
and new-evidence gates by default, stores an immutable candidate, and never
changes the learner-serving model (see ``scripts.promote_bkt_model`` for
that).  Use ``--force`` for a deliberate pilot or synthetic recovery check.

By default it fits the format-aware model production serves (P(L0), P(T),
MCQ guess/slip, typed guess/slip), compares it out of sample with the
currently deployed parameters, and previews how each learner's word statuses
would change.  ``--model global`` runs the legacy single guess/slip fit.

Examples, run from ``backend/``::

    python -m scripts.refit_bkt_parameters --source synthetic --force
    python -m scripts.refit_bkt_parameters --source real
    python -m scripts.refit_bkt_parameters --source real --json
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from analytics.learner_model.bkt.calibration_store import run_calibration_candidate
from db import connect_db


_LABELS = (
    ("prior", "P(L0)"),
    ("learn", "P(T)"),
    ("guess", "MCQ guess"),
    ("slip", "MCQ slip"),
    ("guess_typed", "Typed guess"),
    ("slip_typed", "Typed slip"),
)


def _fmt(value: Any, digits: int = 4) -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "-"


def print_summary(result: dict[str, Any]) -> None:
    if result["status"] != "completed":
        print(f"Skipped ({result['decision'].get('reason')}): no candidate was created.")
        return
    counts = result["counts"]
    print(f"Candidate {result['modelVersion']}  (evidence: {result['evidenceOrigin']})")
    print(f"  {counts['records']} answers, {counts['students']} students, {counts['concepts']} words")
    candidate, current = result["candidateParameters"], result["productionParameters"]
    print("\n  Parameter        current   candidate")
    for key, label in _LABELS:
        if key in candidate:
            print(f"  {label:<15} {_fmt(current.get(key)):>8}   {_fmt(candidate.get(key)):>8}")
    ident = result.get("identifiability") or {}
    for warning in ident.get("warnings", []):
        print(f"  ! {warning}")
    metrics = result["metrics"]
    print("\n  Held-out (5-fold, by student)   current   candidate")
    for key in ("log_loss", "brier", "calibration_error", "auc"):
        print(f"  {key:<31} {_fmt(metrics['production'].get(key)):>8}   {_fmt(metrics['candidate'].get(key)):>8}")
    failed = [name for name, ok in result["gates"].items() if not ok]
    print(f"\n  Gates: {'all passed' if not failed else 'FAILED ' + ', '.join(failed)}")
    impact = result.get("impact")
    if impact:
        print(
            f"\n  Impact if activated ({impact['students']} students, {impact['observedWords']} observed words):"
            f"\n    review status changes: {impact['changedWords']} words for {impact['studentsWithChanges']} students"
            f"\n    BKT STRONG words: {impact['strongBefore']} -> {impact['strongAfter']}"
            f"\n    P(learned) shift: mean {impact['meanAbsolutePLearnedChange']}, max {impact['maxAbsolutePLearnedChange']}"
        )
        for label, table in (("review", impact["transitions"]), ("BKT", impact["bktTransitions"])):
            for transition, count in table.items():
                print(f"    {label} {transition}: {count}")
        print("    Most affected words:")
        for example in impact["examples"][:10]:
            before, after = example["before"], example["after"]
            print(
                f"      {example['studentId']} {example['word']} ({example['correct']}/{example['observations']} correct): "
                f"{before['pLearned']} {before['bktStatus']}/{before['status']} -> "
                f"{after['pLearned']} {after['bktStatus']}/{after['status']}"
            )
    if result["promotable"]:
        print(f"\n  Promotable. Activate with:\n    python -m scripts.promote_bkt_model activate {result['modelVersion']} --reason \"...\"")
    elif result["evidenceOrigin"] != "real":
        print("\n  Not promotable: fitted on synthetic evidence (report only; the database refuses to deploy it).")
    else:
        print("\n  Not promotable: see the failed gates above.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--source",
        choices=("real", "synthetic"),
        default="real",
        help="Ledger evidence origin. Synthetic candidates are never promotable.",
    )
    parser.add_argument(
        "--model",
        choices=("format-aware", "global"),
        default="format-aware",
        help="format-aware (what production serves) or the legacy global single-pair fit.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass only the scheduling cadence; evidence and promotion gates still apply.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=200,
        help="Maximum L-BFGS-B iterations per fit.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full result as JSON.")
    parser.add_argument("--student-ids", nargs="+", help="Restrict snapshot and cadence to these student IDs.")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be at least 1")

    with connect_db() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        result = run_calibration_candidate(
            db,
            args.source,
            force=args.force,
            iterations=args.iterations,
            model=args.model,
            student_ids=args.student_ids,
        )
    if args.json or args.model == "global":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print_summary(result)


if __name__ == "__main__":
    main()
