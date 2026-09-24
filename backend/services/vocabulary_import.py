"""Admin-facing quiz vocabulary import: CSV -> validate -> preview -> confirm.

Reuses the exact row shape and per-row/per-word validation
``scripts/import_question_bank_workbook.py`` already established for the
canonical Chapters 5-8 workbook, minus that script's one-time assumptions
(a fixed 648-row count, chapters 5-8 only, a single hardcoded file path).
``build_payloads`` and ``find_story_for_part`` are reused as-is - neither
one carried those assumptions to begin with.

Import never overwrites a story's whole ``vocab_assessment`` bank. It
upserts by ``wordId`` within each section's matched story: words present in
the file replace any existing entry with the same id (or are added), and
existing words the file doesn't mention are left untouched. Nothing is
written until ``apply_vocabulary_import`` is called explicitly - preview is
read-only.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from typing import Any

import openpyxl
from psycopg.types.json import Jsonb

from domain.vocabulary.assessment import validate_assessment_payload
from scripts.import_question_bank_workbook import REQUIRED_COLUMNS, ROUNDS, build_payloads
from scripts.seed_quiz_assessments import find_story_for_part


ROUND_ALIASES = {"1": "Round 1", "2": "Round 2", "3": "Round 3"}
INPUT_MODE_ALIASES = {"mcq": "click"}


def _normalize_import_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Accept the compact workbook vocabulary used by the admin template.

    The canonical payload still uses the internal ``Round 1``/``click`` values,
    but exported workbooks commonly use numeric rounds and ``mcq``. Normalize
    those aliases once at the upload boundary so validation and publishing see
    one consistent shape.
    """
    normalized: list[dict[str, str]] = []
    for raw_row in rows:
        row = dict(raw_row)
        round_value = (row.get("Round") or "").strip()
        input_mode = (row.get("Input Mode") or "").strip()
        row["Round"] = ROUND_ALIASES.get(round_value.casefold(), round_value)
        row["Input Mode"] = INPUT_MODE_ALIASES.get(input_mode.casefold(), input_mode)
        normalized.append(row)
    return normalized


def parse_csv_rows(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    missing = REQUIRED_COLUMNS.difference(reader.fieldnames or ())
    if missing:
        raise ValueError(f"File is missing required columns: {', '.join(sorted(missing))}")
    return _normalize_import_rows([dict(row) for row in reader if row.get("Question ID")])


def _cell_text(value: object) -> str:
    """Excel stores numbers as float/int; normalize integral values before validation."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_xlsx_rows(content: bytes) -> list[dict[str, str]]:
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        sheet = next(
            (workbook[name] for name in workbook.sheetnames if name.strip().casefold() in {"questions", "quiz questions"}),
            workbook[workbook.sheetnames[0]],
        )
        rows_iter = sheet.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            raise ValueError("File has no header row.") from None
        header = [_cell_text(cell) for cell in header_row]
        missing = REQUIRED_COLUMNS.difference(header)
        if missing:
            raise ValueError(f"File is missing required columns: {', '.join(sorted(missing))}")
        rows: list[dict[str, str]] = []
        for raw_row in rows_iter:
            row = {header[index]: _cell_text(raw_row[index]) for index in range(len(header)) if index < len(raw_row)}
            if row.get("Question ID"):
                rows.append(row)
        return _normalize_import_rows(rows)
    finally:
        workbook.close()


def parse_uploaded_rows(filename: str, content: bytes) -> list[dict[str, str]]:
    """Dispatch by extension - both formats produce the identical row shape
    that validate_import_rows/build_payloads consume, so nothing downstream
    needs to know which one was uploaded."""
    suffix = (filename or "").rsplit(".", 1)[-1].casefold() if "." in (filename or "") else ""
    if suffix in {"xlsx", "xlsm"}:
        return parse_xlsx_rows(content)
    if suffix == "xls":
        raise ValueError("The legacy .xls format is not supported - save as .xlsx or .csv and re-upload.")
    return parse_csv_rows(content)


def _answers(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split("|") if part.strip()]


def validate_import_rows(rows: list[dict[str, str]]) -> list[str]:
    """Same per-row/per-word checks as the workbook importer, generalized to
    any section/row count (no fixed 648-row or chapter-5-8 assumption)."""
    issues: list[str] = []
    if not rows:
        issues.append("File has no data rows.")
        return issues
    seen_question_ids: set[str] = set()
    by_word: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        qid = row.get("Question ID", "")
        if qid in seen_question_ids:
            issues.append(f"duplicate Question ID: {qid}")
        seen_question_ids.add(qid)
        by_word[row.get("Word Key", "")].append(row)
        section = row.get("Section", "")
        if "-" not in section or not all(part.strip().isdigit() for part in section.split("-", 1)):
            issues.append(f"{qid}: Section must look like '5-1' (chapter-part), found {section!r}")
        round_info = ROUNDS.get(row.get("Round", ""))
        if round_info is None:
            issues.append(f"{qid}: unsupported round {row.get('Round')!r}")
            continue
        level, _, answer_format = round_info
        expected_type = {"easy": "basic_meaning_mcq", "medium": "character_to_pinyin_typing", "hard": "context_cloze_mcq"}[level]
        if row.get("Question Type") != expected_type:
            issues.append(f"{qid}: {row.get('Round')} uses {row.get('Question Type')}, expected {expected_type}")
        if row.get("Input Mode") == "click" and answer_format != "single_choice":
            issues.append(f"{qid}: click input is not a single-choice question")
        if row.get("Input Mode") == "free_text" and answer_format != "free_text":
            issues.append(f"{qid}: free-text input has the wrong answer format")
        if level in {"easy", "hard"}:
            options = [row.get(f"Option {letter}", "") for letter in "ABCD"]
            if len(set(options)) != 4 or any(not option for option in options):
                issues.append(f"{qid}: options must contain four distinct values")
            correct_option = row.get("Correct Option", "")
            if correct_option not in "ABCD":
                issues.append(f"{qid}: invalid correct option {correct_option!r}")
            elif options["ABCD".index(correct_option)] != row.get("Correct Answer"):
                issues.append(f"{qid}: correct option does not match correct answer")
        else:
            accepted = _answers(row.get("Accepted Answers", ""))
            if row.get("Correct Answer") not in accepted:
                issues.append(f"{qid}: pinyin correct answer is not accepted")
        for required in ("Word Key", "Traditional Chinese", "Pinyin", "POS", "English Meaning", "Prompt", "Correct Answer"):
            if not (row.get(required) or "").strip():
                issues.append(f"{qid}: empty {required}")
    for word_id, word_rows in by_word.items():
        if len(word_rows) != 3 or {row.get("Round") for row in word_rows} != set(ROUNDS):
            issues.append(f"{word_id}: expected exactly one row for each round (Round 1/2/3)")
        for field in ("Chapter", "Section", "Traditional Chinese", "Pinyin", "POS", "English Meaning"):
            if len({row.get(field) for row in word_rows}) != 1:
                issues.append(f"{word_id}: inconsistent {field} metadata across its three rows")
    return issues


def _section_preview(db: Any, section: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        story = find_story_for_part(db, section)
    except LookupError as exc:
        return {
            "section": section, "storyId": None, "storyTitle": None, "found": False,
            "error": str(exc), "newWords": 0, "updatedWords": 0, "questionCount": len(payload), "issues": [],
        }
    row = db.execute("SELECT vocab_assessment FROM custom_stories WHERE id = %s", (story["id"],)).fetchone()
    existing = row["vocab_assessment"] if row and isinstance(row.get("vocab_assessment"), list) else []
    existing_word_ids = {question.get("wordId") for question in existing}
    incoming_word_ids = {question["wordId"] for question in payload}
    merged = _merge_assessment(existing, payload)
    issues = validate_assessment_payload(merged)
    return {
        "section": section,
        "storyId": story["id"],
        "storyTitle": story["title"],
        "found": True,
        "newWords": len(incoming_word_ids - existing_word_ids),
        "updatedWords": len(incoming_word_ids & existing_word_ids),
        "questionCount": len(payload),
        "issues": [f"{issue.code}: {issue.message}" for issue in issues],
    }


def _merge_assessment(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    incoming_word_ids = {question["wordId"] for question in incoming}
    kept = [question for question in existing if question.get("wordId") not in incoming_word_ids]
    return kept + incoming


def preview_vocabulary_import(db: Any, content: bytes, filename: str = "") -> dict[str, Any]:
    """Read-only: parse, validate, and report what an import would do."""
    rows = parse_uploaded_rows(filename, content)
    row_issues = validate_import_rows(rows)
    if row_issues:
        return {"rows": len(rows), "rowIssues": row_issues, "sections": []}
    payloads = build_payloads(rows)
    with_db = [_section_preview(db, section, payload) for section, payload in sorted(payloads.items())]
    return {"rows": len(rows), "rowIssues": [], "sections": with_db}


def apply_vocabulary_import(db: Any, content: bytes, filename: str = "") -> dict[str, Any]:
    """Write path. Re-validates from scratch - never trusts a client-held
    preview result as proof the file is still valid to write."""
    rows = parse_uploaded_rows(filename, content)
    row_issues = validate_import_rows(rows)
    if row_issues:
        raise ValueError("Row validation failed:\n" + "\n".join(row_issues[:30]))
    payloads = build_payloads(rows)
    published: list[dict[str, Any]] = []
    for section, payload in sorted(payloads.items()):
        story = find_story_for_part(db, section)
        row = db.execute(
            "SELECT vocab_assessment FROM custom_stories WHERE id = %s FOR UPDATE", (story["id"],),
        ).fetchone()
        existing = row["vocab_assessment"] if row and isinstance(row.get("vocab_assessment"), list) else []
        merged = _merge_assessment(existing, payload)
        issues = validate_assessment_payload(merged)
        if issues:
            rendered = "; ".join(f"{issue.code}: {issue.message}" for issue in issues[:8])
            raise ValueError(f"{section} would fail validation after merge ({len(issues)} issues): {rendered}")
        db.execute(
            "UPDATE custom_stories SET vocab_assessment = %s::jsonb WHERE id = %s",
            (Jsonb(merged), story["id"]),
        )
        published.append({"section": section, "storyId": story["id"], "storyTitle": story["title"], "questionCount": len(payload)})
    return {"published": published}
