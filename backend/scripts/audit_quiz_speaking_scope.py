"""Offline, read-only content audit; only the three output reports are written.

Run from any directory::

    python backend/scripts/audit_quiz_speaking_scope.py --output output/quiz-speaking-audit

All quiz tiers are audited: easy/medium/hard are not CEFR classifications.
Optional --evidence JSON has questions_sha256 and a rows array. Each entry
requires record_number, composite_identity (array), reviewer, reference, and
optional semantic_review (reviewed/not_reviewed), cefr (A1/A2/unverified).
Evidence is attributed, not independently validated by this mechanical audit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TIERS = {"easy": "", "medium": "medium", "hard": "hard"}
DISTRACTOR_TYPES = {"translation", "cloze", "synonym"}
ANSWER_POOL_TYPES = {"reverse", "listening", "pinyin"}
QUESTION_TYPES = DISTRACTOR_TYPES | ANSWER_POOL_TYPES | {"pos"}
METADATA = ("story_title", "published", "lesson_number", "lesson_sub_order")
IDENTITY = ("story_id", "tier", "frame_index", "word_index", "question_type")
QUESTION_COLUMNS = (
    "story_id", *METADATA, "tier", "frame_index", "word_index", "word",
    "question_type", "prompt", "correct_answer", "translation", "pinyin",
    "part_of_speech", "options_from_source", "context_sentence", "source",
    "validation_status", "validation_errors",
)
# Explicitly exclude vocabularyCloze/Synonym/Distractors/Lookalike and snapshots.
LIST_FIELDS = {
    "vocabulary", "vocabularytranslation", "vocabularypinyin", "vocabularypos",
    "phrases", "phrasestranslation", "phrasespinyin",
}
SENTENCE_FIELDS = {"suggestedanswer", "listenscript", "grammarexample"}
SOURCE_FIELDS = LIST_FIELDS | SENTENCE_FIELDS | {"grammarpattern", "grammarexplanation"}
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]")
BLANK = re.compile(r"_{2,}")


def normalize(value: str) -> str:
    """Literal matching only: compatibility normalization and collapsed whitespace."""
    return " ".join(unicodedata.normalize("NFKC", value).split())


def packed(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def index_value(value: str) -> int | None:
    try:
        result = int(value)
        return result if result >= 0 else None
    except (TypeError, ValueError):
        return None


def identity(row: dict[str, str]) -> list[Any]:
    return [index_value(row.get(key, "")) if key.endswith("_index")
            and index_value(row.get(key, "")) is not None else row.get(key, "")
            for key in IDENTITY]


def read_csv(path: Path, required: set[str]) -> tuple[list[dict], dict, list[dict]]:
    """Keep logical data-record numbers separate from physical CSV line numbers."""
    content = path.read_bytes()
    manifest = {"path": str(path.resolve()), "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content)}
    reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
    records, issues = [], []
    try:
        header = next(reader, [])
    except csv.Error as error:
        header = []
        issues.append({"code": "malformed_csv_header", "detail": str(error)})
    missing = sorted(required - set(header))
    if missing:
        issues.append({"code": "missing_columns", "detail": packed(missing)})
    if len(header) != len(set(header)):
        issues.append({"code": "duplicate_columns", "detail": packed(header)})
    while True:
        start = reader.line_num + 1
        row_issues = []
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error as error:
            cells = []
            row_issues.append({"code": "malformed_csv_record", "detail": str(error)})
        if not cells and not row_issues:
            continue
        if len(cells) != len(header):
            row_issues.append({"code": "csv_row_width", "detail":
                               f"Expected {len(header)} cells, found {len(cells)}"})
        records.append({"record_number": len(records) + 1, "physical_start_line": start,
                        "physical_end_line": reader.line_num,
                        "data": dict(zip(header, cells)), "issues": row_issues})
    manifest["records"] = len(records)
    return records, manifest, issues


def source_key(key: str) -> tuple[str, str] | None:
    compact = key.replace("_", "").lower()
    for suffix in ("medium", "hard", "easy", ""):
        base = compact[:-len(suffix)] if suffix else compact
        if (not suffix or compact.endswith(suffix)) and base in SOURCE_FIELDS:
            return base, "" if suffix == "easy" else suffix
    return None


def values(value: Any, base: str) -> list[str]:
    # Speaking's comma lists use the same nonempty-entry indexing as its exporter.
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()] if base in LIST_FIELDS else [value]
    if isinstance(value, list):
        return [part for part in value if isinstance(part, str) and part.strip()]
    return []


class SpeakingSources:
    def __init__(self, records: list[dict]):
        self.frames: dict[tuple[str, int | None], list[dict]] = defaultdict(list)
        self.strings: list[dict] = []
        self.issues: list[dict] = []
        self.cache: dict[tuple[str, bool], list[dict]] = {}
        for record in records:
            row = record["data"]
            frame = {**record, "fields": {}, "source_issues": list(record["issues"])}
            try:
                payload = json.loads(row.get("frame_json", ""))
                if not isinstance(payload, dict):
                    raise ValueError("frame_json must be an object")
            except (ValueError, TypeError) as error:
                payload = {}
                frame["source_issues"].append({"code": "malformed_frame_json", "detail": str(error)})
            for origin, mapping in (("csv", row), ("frame_json", payload)):
                for key, value in mapping.items():
                    recognized = source_key(key)
                    if recognized is None or value is None or value == "":
                        continue
                    base, suffix = recognized
                    parts = values(value, base)
                    if not isinstance(value, (str, list)) or (isinstance(value, list)
                            and not all(isinstance(part, str) for part in value)):
                        frame["source_issues"].append({"code": "malformed_source_field", "detail": f"{origin}.{key}"})
                    field = {"parts": parts, "field": f"{origin}.{key}"}
                    prior = frame["fields"].get((base, suffix))
                    if prior and [normalize(p) for p in prior["parts"]] != [normalize(p) for p in parts]:
                        frame["source_issues"].append({"code": "source_field_mismatch", "detail":
                            packed({"csv": prior, "frame_json": field})})
                    frame["fields"][(base, suffix)] = field
                    for part in parts:
                        if not normalize(part):
                            continue
                        self.strings.append({"story_id": row.get("story_id", ""),
                            "frame_index": index_value(row.get("frame_index", "")),
                            "record_number": record["record_number"],
                            "physical_start_line": record["physical_start_line"],
                            "field": field["field"], "text": part,
                            "normalized": normalize(part), "is_sentence": base in SENTENCE_FIELDS})
            location = (row.get("story_id", ""), index_value(row.get("frame_index", "")))
            if not location[0] or location[1] is None:
                frame["source_issues"].append({"code": "invalid_source_identity", "detail": packed(location)})
            self.frames[location].append(frame)
        for location, frames in self.frames.items():
            for frame in frames:
                if len(frames) > 1:
                    frame["source_issues"].append({"code": "duplicate_source_frame", "detail": packed(location)})
                for issue in frame["source_issues"]:
                    self.issues.append({**issue, "story_id": location[0], "frame_index": location[1],
                        "record_number": frame["record_number"], "physical_start_line": frame["physical_start_line"]})

    def search(self, text: str, story: str, frame: int | None, *, sentence: bool = False) -> dict:
        needle = normalize(text)
        cache_key = (needle, sentence)
        if cache_key not in self.cache:
            hits = []
            if needle:
                for source in self.strings:
                    if sentence:
                        candidates = [source["normalized"], *(
                            normalize(part) for part in re.split(r"(?<=[\u3002.!?])\s*|[\r\n]+", source["text"]))]
                        matched = source["is_sentence"] and needle in candidates
                    else:
                        matched = needle in source["normalized"]
                    if matched:
                        hits.append(source)
            self.cache[cache_key] = hits
        scopes: dict[str, list[dict]] = defaultdict(list)
        for hit in self.cache[cache_key]:
            scope = ("same_frame" if hit["frame_index"] == frame else "same_story") if hit["story_id"] == story else "other_speaking_story"
            scopes[scope].append(hit)
        for scope in ("same_frame", "same_story", "other_speaking_story"):
            if scopes[scope]:
                hit = scopes[scope][0]
                return {"scope": scope, "match_count": len(scopes[scope]),
                        "evidence": {key: value for key, value in hit.items() if key not in {"normalized", "is_sentence"}}}
        return {"scope": "not_found", "match_count": 0, "evidence": None}


def tier_field(frame: dict, base: str, tier: str) -> dict:
    suffix = TIERS.get(tier, "")
    for candidate in dict.fromkeys((suffix, "")):
        field = frame["fields"].get((base, candidate))
        if field and field["parts"] and any(normalize(part) for part in field["parts"]):
            return {**field, "resolution": "base_fallback" if candidate != suffix else "tier"}
    return {"parts": [], "field": "", "resolution": "unavailable"}


def audit_row(record: dict, sources: SpeakingSources, duplicate: bool) -> tuple[dict, list[dict]]:
    row = {key: value.strip() for key, value in record["data"].items()}
    location = {key: record[key] for key in ("record_number", "physical_start_line", "physical_end_line")}
    location.update({key: row.get(key, "") for key in IDENTITY})
    location["composite_identity"] = identity(row)
    findings = []

    def add(code: str, field: str = "", detail: Any = "", match: dict | None = None) -> None:
        findings.append({**location, "entity": "question", "code": code, "field": field,
                         "detail": detail, "source_scope": (match or {}).get("scope", ""),
                         "evidence": (match or {}).get("evidence")})

    for issue in record["issues"]:
        add(issue["code"], detail=issue["detail"])
    for field in ("story_id", "word", "correct_answer", "prompt"):
        if not row.get(field):
            add("missing_value", field)
    if duplicate:
        add("duplicate_question_identity")
    tier, kind = row.get("tier", ""), row.get("question_type", "")
    frame_index, word_index = (index_value(row.get(key, "")) for key in ("frame_index", "word_index"))
    if frame_index is None or word_index is None:
        add("invalid_index")
    if tier not in TIERS:
        add("unsupported_tier", "tier", tier)
    if kind not in QUESTION_TYPES:
        add("unsupported_question_type", "question_type", kind)
    word, answer = row.get("word", ""), row.get("correct_answer", "")
    story = row.get("story_id", "")
    word_match = sources.search(word, story, frame_index)
    answer_match = sources.search(answer, story, frame_index)
    if word_match["scope"] in {"not_found", "other_speaking_story"}:
        add("target_word_outside_story", "word", word, word_match)
    target = {"resolution": "unavailable", "field": "", "expected_word": ""}
    frames = sources.frames.get((story, frame_index), [])
    if not frames:
        add("missing_source_frame")
    elif len(frames) > 1:
        add("ambiguous_source_frame")
    else:
        frame = frames[0]
        for issue in frame["source_issues"]:
            add(issue["code"], "frame_json", issue["detail"])
        for field in METADATA:
            expected, actual = normalize(frame["data"].get(field, "")), normalize(row.get(field, ""))
            if field == "published":
                expected, actual = expected.casefold(), actual.casefold()
            if expected != actual:
                add("metadata_mismatch", field, {"expected": expected, "actual": actual})
        selected = tier_field(frame, "vocabulary", tier)
        target.update({key: selected[key] for key in ("resolution", "field")})
        if word_index is None or word_index >= len(selected["parts"]):
            add("target_index_out_of_range", "word_index", {"available_words": len(selected["parts"])})
        else:
            target["expected_word"] = selected["parts"][word_index]
            if normalize(word) != normalize(target["expected_word"]):
                add("target_word_mismatch", "word", target)
            for field, base in (("translation", "vocabularytranslation"), ("pinyin", "vocabularypinyin"),
                                ("part_of_speech", "vocabularypos")):
                selected = tier_field(frame, base, tier)
                expected = selected["parts"][word_index] if word_index < len(selected["parts"]) else ""
                if normalize(row.get(field, "")) != normalize(expected):
                    add("target_metadata_mismatch", field, {"expected": expected, "actual": row.get(field, ""),
                                                            "source_field": selected["field"]})
    expected_answer = row.get({"translation": "translation", "pinyin": "pinyin", "pos": "part_of_speech"}.get(kind, "word"), "")
    if kind in QUESTION_TYPES - {"synonym"} and normalize(answer) != normalize(expected_answer):
        add("correct_answer_mismatch", "correct_answer", {"expected": expected_answer, "actual": answer})
    options = []
    try:
        parsed = json.loads(row.get("options_from_source", ""))
        if not isinstance(parsed, list):
            raise ValueError("Options must be a JSON array")
        if not all(isinstance(option, str) for option in parsed):
            add("malformed_options", "options_from_source", "Options must contain only strings")
        options = [option for option in parsed if isinstance(option, str)]
    except (ValueError, TypeError) as error:
        add("malformed_options", "options_from_source", str(error))
    normalized_options = [normalize(option) for option in options]
    if "" in normalized_options:
        add("empty_option", "options_from_source")
    if len(normalized_options) != len(set(normalized_options)):
        add("duplicate_options", "options_from_source")
    if kind != "pos" and not any(normalized_options):
        add("empty_options", "options_from_source")
    if kind in DISTRACTOR_TYPES and normalize(answer) in normalized_options:
        add("correct_answer_in_distractors", "options_from_source")
    if kind in ANSWER_POOL_TYPES and normalize(answer) not in normalized_options:
        add("correct_answer_missing_from_options", "options_from_source")
    distractor_matches = []
    for option_index, option in enumerate(options):
        if normalize(option) == normalize(answer) or not HAN.search(option):
            continue
        match = sources.search(option, story, frame_index)
        distractor_matches.append({"option_index": option_index, "text": option, **match})
        if match["scope"] in {"not_found", "other_speaking_story"}:
            add("chinese_distractor_" + ("not_found" if match["scope"] == "not_found" else "other_story"),
                f"options_from_source[{option_index}]", option, match)
    if kind == "synonym" and answer_match["scope"] in {"not_found", "other_speaking_story"}:
        add("synonym_answer_" + ("not_found" if answer_match["scope"] == "not_found" else "other_story"),
            "correct_answer", answer, answer_match)
    reconstructed, context_match, blank_count = "", None, ""
    if kind == "cloze":
        context = normalize(row.get("context_sentence", ""))
        blanks = list(BLANK.finditer(context))
        blank_count = len(blanks)
        if blank_count != 1:
            add("cloze_blank_count", "context_sentence", {"expected": 1, "actual": blank_count})
        else:
            blank = blanks[0]
            reconstructed = context[:blank.start()] + answer + context[blank.end():]
            context_match = sources.search(reconstructed, story, frame_index, sentence=True)
            if context_match["scope"] == "not_found":
                add("altered_context", "context_sentence", {"reconstructed": reconstructed}, context_match)
            elif context_match["scope"] != "same_frame":
                add("cloze_context_outside_frame", "context_sentence", reconstructed, context_match)
    ledger = {**record["data"], **location, "semantic_review": "not_reviewed", "cefr": "unverified",
              "review_evidence": None, "target_alignment": target,
              "word_source_scope": word_match["scope"], "word_source_match": word_match,
              "answer_source_scope": answer_match["scope"], "answer_source_match": answer_match,
              "chinese_distractor_matches": distractor_matches, "cloze_blank_count": blank_count,
              "reconstructed_context": reconstructed, "context_source_match": context_match,
              "finding_count": len(findings), "finding_codes": sorted({f["code"] for f in findings})}
    return ledger, findings


def historical_inventory(root: Path, excluded: set[Path]) -> list[dict]:
    inventory = []
    for directory, folders, files in os.walk(root):
        folders[:] = sorted(name for name in folders if not name.startswith(".")
                            and name not in {"node_modules", "venv", "output", "dist", "build", "__pycache__"}
                            and not (Path(directory) / name).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix.lower() != ".csv" or not any(part in name.lower() for part in ("quiz", "question")):
                continue
            if path.resolve() in excluded:
                continue
            excluded.add(path.resolve())
            entry = {"path": str(path.resolve()), "role": "historical_not_canonical", "included_in_totals": False}
            try:
                _, manifest, issues = read_csv(path, {"question_type"})
                entry.update(manifest)
                entry["issues"] = issues
            except (OSError, UnicodeError) as error:
                entry["error"] = str(error)
            inventory.append(entry)
    return inventory


def apply_evidence(path: Path, manifest: dict, ledger: list[dict]) -> tuple[dict, list[dict]]:
    content = path.read_bytes()
    evidence_manifest = {"path": str(path.resolve()), "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
    issues = []
    try:
        evidence = json.loads(content)
        if not isinstance(evidence, dict) or evidence.get("questions_sha256") != manifest["sha256"]:
            raise ValueError("Evidence must identify the exact questions_sha256")
        entries = evidence.get("rows")
        if not isinstance(entries, list):
            raise ValueError("Evidence rows must be an array")
        counts = Counter(item.get("record_number") for item in entries
                         if isinstance(item, dict) and type(item.get("record_number")) is int)
        by_record = {row["record_number"]: row for row in ledger}
        for item in entries:
            number = item.get("record_number") if isinstance(item, dict) else None
            row = by_record.get(number) if type(number) is int else None
            if (row is None or counts[number] != 1 or item.get("composite_identity") != row["composite_identity"]
                    or not all(isinstance(item.get(key), str) and item[key].strip() for key in ("reference", "reviewer"))
                    or item.get("semantic_review", "not_reviewed") not in {"not_reviewed", "reviewed"}
                    or item.get("cefr", "unverified") not in {"unverified", "A1", "A2"}):
                issues.append({"code": "invalid_review_evidence", "detail": packed(item)})
                continue
            row.update({"semantic_review": item.get("semantic_review", "not_reviewed"),
                        "cefr": item.get("cefr", "unverified"), "review_evidence": item})
    except (ValueError, TypeError) as error:
        issues.append({"code": "invalid_review_evidence", "detail": str(error)})
    return evidence_manifest, issues


def audit(questions: Path, speaking: Path,
          *, root: Path = ROOT, evidence: Path | None = None) -> tuple[dict, list[dict], list[dict]]:
    records, question_manifest, question_issues = read_csv(questions, set(QUESTION_COLUMNS))
    source_records, speaking_manifest, speaking_issues = read_csv(speaking, {"story_id", *METADATA, "frame_index", "frame_json"})
    sources = SpeakingSources(source_records)
    frequencies = Counter(packed(identity(record["data"])) for record in records)
    ledger, findings = [], []
    for record in records:
        row, row_findings = audit_row(record, sources, frequencies[packed(identity(record["data"]))] > 1)
        ledger.append(row)
        findings.extend(row_findings)
    manifests = {"questions": question_manifest, "speaking": speaking_manifest}
    input_issues = [{**issue, "input": name} for name, issues in
                    (("questions", question_issues), ("speaking", speaking_issues)) for issue in issues]
    if evidence:
        manifests["evidence"], evidence_issues = apply_evidence(evidence, question_manifest, ledger)
        input_issues.extend({**issue, "input": "evidence"} for issue in evidence_issues)

    def grouped(key: str) -> dict:
        groups = {}
        for value in sorted({row.get(key, "") for row in ledger}):
            rows = [row for row in ledger if row.get(key, "") == value]
            relevant = [finding for finding in findings if finding.get(key, "") == value]
            groups[value] = {"rows": len(rows), "unique_affected_rows": sum(bool(row["finding_count"]) for row in rows),
                             "findings": len(relevant), "by_code": dict(sorted(Counter(f["code"] for f in relevant).items()))}
        return groups

    summary = {"scope": "A1-A2 intended educational scope; Speaking CSV sources only; all quiz tiers",
        "method": {"matching": "NFKC and collapsed whitespace, case-sensitive literal match within individual source strings",
                   "source_fields": sorted(SOURCE_FIELDS), "tier_suffixes": ["base", "easy", "medium", "hard"],
                   "target_selection": "frame_json fields take precedence over CSV mirrors; requested tier then base when empty",
                   "pos_options": "Optional pool; no required answer presence, matching the locked importer",
                   "cloze": "One underscore-run blank; reconstruction must equal a Speaking sentence. altered_context is not a grammar verdict.",
                   "record_number": "One-based data record, excluding header and empty physical rows",
                   "limits": "No semantic, grammar, CEFR, official TOCFL or runtime validation; malformed CSV quoting may consume following physical lines."},
        "input_manifest": manifests, "input_issues": input_issues, "source_issues": sources.issues,
        "total_rows": len(ledger), "source_frames": len(source_records),
        "unique_affected_rows": sum(bool(row["finding_count"]) for row in ledger), "total_findings": len(findings),
        "by_code": dict(sorted(Counter(f["code"] for f in findings).items())),
        "by_story": grouped("story_id"), "by_type": grouped("question_type"),
        "by_tier": dict(sorted(Counter(row.get("tier", "") for row in ledger).items())),
        "semantic_review": dict(Counter(row["semantic_review"] for row in ledger)),
        "cefr": dict(Counter(row["cefr"] for row in ledger)),
        "historical_quiz_inventory": historical_inventory(root, {questions.resolve(), speaking.resolve()})}
    for issue in sources.issues:
        findings.append({**issue, "entity": "speaking_source"})
    for issue in input_issues:
        findings.append({**issue, "entity": "input"})
    return summary, ledger, findings


def write_reports(output: Path, summary: dict, ledger: list[dict], findings: list[dict]) -> None:
    protected = {Path(item["path"]).resolve() for item in summary["input_manifest"].values()}
    protected.update(Path(item["path"]).resolve() for item in summary["historical_quiz_inventory"])
    destinations = [output / name for name in ("summary.json", "row_ledger.csv", "findings.csv")]
    for destination in destinations:
        if destination.is_symlink() or destination.resolve() in protected:
            raise ValueError(f"Report would overwrite an input: {destination}")
        if destination.exists() and any(destination.samefile(path) for path in protected if path.exists()):
            raise ValueError(f"Report aliases an input: {destination}")
    output.mkdir(parents=True, exist_ok=True)
    destinations[0].write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for path, rows, defaults in ((destinations[1], ledger, ["record_number", "physical_start_line", *QUESTION_COLUMNS,
                                                          "composite_identity", "semantic_review", "cefr"]),
                                 (destinations[2], findings, ["entity", "record_number", "physical_start_line",
                                                            "composite_identity", *IDENTITY, "code", "field", "detail", "source_scope", "evidence"])):
        columns = list(dict.fromkeys([*defaults, *(key for row in rows for key in row)]))
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: packed(value) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--questions", type=Path, required=True, help="Question CSV to audit")
    parser.add_argument("--speaking", type=Path, required=True, help="Speaking/story CSV to audit")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "quiz-speaking-audit", help="Directory for generated reports only")
    parser.add_argument("--inventory-root", type=Path, default=ROOT)
    parser.add_argument("--evidence", type=Path, help="Optional attributed review evidence tied to the input hash")
    args = parser.parse_args(argv)
    try:
        summary, ledger, findings = audit(args.questions, args.speaking, root=args.inventory_root, evidence=args.evidence)
        write_reports(args.output, summary, ledger, findings)
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(2, f"Audit could not complete: {error}\n")
    print(json.dumps({"rows": summary["total_rows"], "unique_affected_rows": summary["unique_affected_rows"],
                      "findings": summary["total_findings"], "output": str(args.output.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
