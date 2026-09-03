"""Audit the vocabulary bank before it can contribute evidence to BKT.

Examples::

    python -m scripts.audit_bkt_eligibility
    python -m scripts.audit_bkt_eligibility --csv questions_verified_v3_book_locked.csv
    python -m scripts.audit_bkt_eligibility --fail-on-ineligible

The command is read-only. It never rewrites educational content or database
rows. Reports default to ``output/`` so generated artifacts stay out of git.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.bkt_question_validation import (  # noqa: E402
    analyze_response_quality,
    validate_bkt_diagnostic_design,
    write_coverage_csv,
    write_report,
)


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _load_database_questions(all_tiers: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from database import connect_db
    from scripts.export_quiz_questions import build_question_rows

    query = "SELECT id, title, published, lesson_number, frames, quiz_approved_snapshot FROM custom_stories WHERE published = TRUE ORDER BY lesson_number NULLS LAST, created_at, id"
    with connect_db() as db:
        stories = [dict(row) for row in db.execute(query).fetchall()]
        attempts = [dict(row) for row in db.execute("SELECT id, student_id, student_name, mode, completed_at, question_results FROM vocab_quiz_attempts").fetchall()]
    questions = build_question_rows(stories, tiers=("easy", "medium", "hard") if all_tiers else ("easy",))
    return questions, attempts


def _print_summary(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print("BKT Diagnostic Question Audit")
    print(f"Vocabulary words: {summary['vocabularyWords']}")
    print(f"PASS: {summary['pass']}")
    print(f"WARNING: {summary['warning']}")
    print(f"FAIL: {summary['fail']}")
    print(f"Questions checked: {summary['questionsChecked']}")
    print(f"BKT eligible: {summary['bktEligible']}")
    print(f"BKT ineligible: {summary['bktIneligible']}")
    print(f"Bank hash: {report['bankHash']}")
    total_capacity = report["capacity"]["total"]
    print(f"Diagnostic capacity: {total_capacity['capacity']} slots; required: {total_capacity['requiredForCurrentWords']}; shortfall: {total_capacity['shortfall']}")
    print("Question types:", ", ".join(f"{key}={value}" for key, value in report["questionTypeDistribution"].items()) or "none")
    print("Correct-option positions:", ", ".join(f"{key}={value}" for key, value in report["correctOptionPositionDistribution"].items()) or "none")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit vocabulary questions for standard word-level BKT eligibility.")
    parser.add_argument("--csv", type=Path, help="Audit an exported question CSV instead of the configured database.")
    parser.add_argument("--all-tiers", action="store_true", help="Include easy, medium, and hard story levels when reading the database.")
    parser.add_argument("--approved-types", default=",".join(sorted(("translation", "reverse", "listening"))), help="Comma-separated question types allowed as BKT evidence.")
    parser.add_argument("--allow-unapproved", action="store_true", help="Report content quality without requiring APPROVED status; not recommended for research evidence.")
    parser.add_argument("--output", type=Path, default=Path("output/bkt-question-validation-report.json"), help="JSON report path.")
    parser.add_argument("--coverage-csv", type=Path, default=Path("output/bkt-coverage-matrix.csv"), help="Coverage matrix CSV path.")
    parser.add_argument("--fail-on-ineligible", action="store_true", help="Exit 1 when any question or word is not eligible.")
    args = parser.parse_args()

    if args.csv:
        questions = _read_csv(args.csv)
        if not args.all_tiers:
            questions = [question for question in questions if question.get("tier", "easy") == "easy"]
        attempts: list[dict[str, Any]] = []
    else:
        questions, attempts = _load_database_questions(args.all_tiers)
    approved_types = tuple(value.strip() for value in args.approved_types.split(",") if value.strip())
    report = validate_bkt_diagnostic_design(
        questions,
        approved_types=approved_types,
        require_teacher_approval=not args.allow_unapproved,
    )
    report["responseQuality"] = analyze_response_quality(attempts)
    _print_summary(report)
    write_report(report, args.output)
    write_coverage_csv(report, args.coverage_csv)
    print(f"JSON report: {args.output}")
    print(f"Coverage matrix: {args.coverage_csv}")
    if args.fail_on_ineligible and (report["summary"]["fail"] or report["summary"]["bktIneligible"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
