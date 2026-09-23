"""Offline, deterministic item-assignment run for a vocabulary research
study (Epic 2 of the BKT x SM-2 research-mode plan).

Assigns every active participant's permanent experimental condition for
every eligible word (published stories in the given lesson range), writing
frozen rows to vocab_research_assignments. Never run this from a live
request - conditions must be decided offline, once, before treatment
begins (see domain/vocabulary/research_assignment.py's module docstring
for the counterbalancing/yoking design this implements).

Refuses to run against a frozen study. Refuses to overwrite an existing
run unless --force is passed, and even --force is blocked once frozen.

Examples::

    python -m scripts.build_research_assignments --study-id pilot-2026
    python -m scripts.build_research_assignments --study-id pilot-2026 --force
    python -m scripts.build_research_assignments --study-id pilot-2026 --lesson-min 5 --lesson-max 8
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.research_assignment_builder import (  # noqa: E402
    AssignmentsAlreadyExistError,
    StudyFrozenError,
    build_assignments_for_study,
)
from db import connect_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--study-id", required=True)
    parser.add_argument("--assignment-version", default=None, help="Defaults to an ISO timestamp if omitted.")
    parser.add_argument("--lesson-min", type=int, default=5)
    parser.add_argument("--lesson-max", type=int, default=8)
    parser.add_argument("--force", action="store_true", help="Delete and regenerate an existing (non-frozen) run.")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).isoformat()
    assignment_version = args.assignment_version or now

    try:
        with connect_db() as db:
            result = build_assignments_for_study(
                db,
                args.study_id,
                assignment_version=assignment_version,
                created_at=now,
                lesson_min=args.lesson_min,
                lesson_max=args.lesson_max,
                force=args.force,
            )
    except (StudyFrozenError, AssignmentsAlreadyExistError) as exc:
        print(f"Refused: {exc}")
        sys.exit(1)

    print(f"Study: {result.study_id}")
    print(f"Assignment version: {result.assignment_version}")
    print(f"Participants assigned: {result.participants_assigned}")
    print(f"Words per participant: {result.words_per_participant}")
    print("Condition counts (words, across all participants):")
    for condition, count in sorted(result.condition_counts.items()):
        print(f"  {condition}: {count}")
    if result.unyoked_word_count:
        print(
            f"WARNING: {result.unyoked_word_count} yoked-condition words had no matching "
            "adaptive-condition word to yoke to (uneven word count) - run "
            "scripts.audit_research_assignments before treating this run as final."
        )


if __name__ == "__main__":
    main()
