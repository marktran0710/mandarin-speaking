"""Read-only balance/integrity report for a research study's item
assignments (Epic 2, Task 2.5). Never modifies data - run this after every
scripts.build_research_assignments run and before freezing a study.

Examples::

    python -m scripts.audit_research_assignments --study-id pilot-2026
    python -m scripts.audit_research_assignments --study-id pilot-2026 --fail-on-violations

Exit code is 1 when --fail-on-violations is passed and the report is not
clean (missing assignments, duplicates, related-set violations, or unyoked
words) - suitable for a pre-freeze CI/checklist gate.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.research_assignment_audit import audit_assignments_for_study  # noqa: E402
from db import connect_db  # noqa: E402


def _print_report(report) -> None:
    print(f"Study: {report.study_id}")
    print(f"Total assignments: {report.total_assignments}")
    print("Condition counts:")
    for condition, count in sorted(report.condition_counts.items()):
        print(f"  {condition}: {count}")

    print(f"Lesson balance ({len(report.lesson_balance)} lessons):")
    for lesson_id, counts in sorted(report.lesson_balance.items()):
        print(f"  lesson {lesson_id}: {counts}")

    print(f"Class balance ({len(report.class_balance)} classes with data):")
    for class_id, counts in sorted(report.class_balance.items()):
        print(f"  class {class_id}: {counts}")

    if report.participants_with_missing_words:
        print(f"MISSING ASSIGNMENTS ({len(report.participants_with_missing_words)} participants):")
        for student_id, (have, expected) in sorted(report.participants_with_missing_words.items()):
            print(f"  {student_id}: {have} / {expected}")
    else:
        print("Missing assignments: none")

    if report.duplicate_student_word_pairs:
        print(f"DUPLICATES ({len(report.duplicate_student_word_pairs)}):")
        for student_id, word_id in report.duplicate_student_word_pairs:
            print(f"  {student_id} x {word_id}")
    else:
        print("Duplicates: none")

    if report.related_set_violations:
        print(f"RELATED-SET VIOLATIONS ({len(report.related_set_violations)}):")
        for student_id, related_set_id in report.related_set_violations:
            print(f"  {student_id}: set {related_set_id} split across conditions")
    else:
        print("Related-set violations: none")

    print(f"Unyoked words: {report.unyoked_count}")
    print(f"Clean: {report.is_clean}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--study-id", required=True)
    parser.add_argument("--fail-on-violations", action="store_true")
    args = parser.parse_args()

    with connect_db() as db:
        report = audit_assignments_for_study(db, args.study_id)

    _print_report(report)

    if args.fail_on_violations and not report.is_clean:
        sys.exit(1)


if __name__ == "__main__":
    main()
