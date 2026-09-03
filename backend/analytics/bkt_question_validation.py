"""Validation rules for vocabulary questions used as word-level BKT evidence.

This module intentionally does not change educational content.  It accepts the
plain dictionaries already used by the quiz export and attempt APIs, reports
problems, and gives callers one explicit ``eligible_for_bkt`` decision.

The question bank is currently stored as story-frame material rather than a
question table, so the validator supports both exported rows and normalized
question dictionaries.  A missing explicit item id is given a deterministic
location-based id for reporting; it is not treated as proof that two runtime
items are different.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


MIN_DIAGNOSTIC_OBSERVATIONS = 3
MIN_TYPE_DIVERSITY = 2
BKT_DIAGNOSTIC_CAPACITIES = {"quiz_1": 20, "quiz_2": 22, "quiz_3": 25}
BKT_DIAGNOSTIC_TYPES = frozenset({"translation", "reverse", "listening", "basic_meaning_mcq"})
CEILING_ACCURACY = 0.95
FLOOR_ACCURACY = 0.20
DIFFICULTY_MIN_RESPONSES = 20

_DISTRACTOR_POOL_TYPES = frozenset({"translation", "cloze", "synonym"})
_SOURCE_OPTION_TYPES = frozenset({"reverse", "listening", "pinyin", "pos"})
_APPROVED_STATUSES = frozenset({"approved", "APPROVED"})
_SLOT_BY_MODE = {"tier1": "quiz_1", "tier2": "quiz_2", "tier3": "quiz_3"}
_SLOT_BY_VALUE = {"1": "quiz_1", "2": "quiz_2", "3": "quiz_3"}
_OBVIOUS_BAD_OPTION = re.compile(r"^(?:a{3,}|n/?a|none|nil|\?{2,}|x{3,})$", re.I)


def _field(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def normalize_value(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().strip().split())


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _question_id(question: Any) -> str:
    explicit = _text(_field(question, "question_id", "questionId", "item_id", "itemId", "id"))
    if explicit:
        return explicit
    parts = [
        _field(question, "story_id", "storyId", default=""),
        _field(question, "tier", "level", default=""),
        _field(question, "frame_index", "frameIndex", default=""),
        _field(question, "word_index", "wordIndex", default=""),
        _field(question, "question_type", "questionType", "questionKind", "kind", default=""),
    ]
    return ":".join(_text(part) for part in parts) or "unknown-question"


def _target_words(question: Any) -> list[str]:
    explicit = _field(question, "target_word_ids", "targetWordIds", "target_words", "targetWords")
    if explicit is not None:
        if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)):
            return [_text(value) for value in explicit if _text(value)]
        if _text(explicit):
            return [_text(explicit)]
    target = _field(question, "word_id", "wordId", "concept_id", "conceptId", "target_word", "targetWord", "word")
    return [_text(target)] if _text(target) else []


def _lesson_id(question: Any) -> str | None:
    value = _field(question, "lesson_id", "lessonId", "lesson_number", "lessonNumber")
    return _text(value) or None


def _issue(
    code: str,
    severity: str,
    message: str,
    question: Any,
    *,
    suggested_action: str,
    word_id: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "question_id": _question_id(question),
        "word_id": word_id,
        "lesson_id": _lesson_id(question),
        "suggested_action": suggested_action,
    }


def _options(question: Any) -> tuple[list[str], bool]:
    raw = _field(question, "options", default=None)
    is_distractors = bool(_field(question, "options_are_distractors", "optionsAreDistractors", default=False))
    if raw is None:
        raw = _field(question, "options_from_source", "optionsFromSource", default=[])
        is_distractors = _field(question, "question_type", "questionType", "questionKind", "kind", default="") in _DISTRACTOR_POOL_TYPES
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return [], is_distractors
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return [], is_distractors
    return [_text(value) for value in raw], is_distractors


def _correct_answer(question: Any) -> str:
    return _text(_field(question, "correct_answer", "correctAnswer", "answer", "correct"))


def _question_type(question: Any) -> str:
    return normalize_value(_field(question, "question_type", "questionType", "questionKind", "kind"))


def _status(question: Any) -> str:
    explicit = _text(_field(question, "validation_status", "validationStatus", default=""))
    # The exporter labels rows from quiz_approved_snapshot as source=approved.
    # That is a genuine teacher approval boundary even though the historical
    # CSV status column used "ok" for content validity.
    if normalize_value(_field(question, "source", default="")) == "approved":
        return "APPROVED"
    return explicit


def _position(question: Any) -> str | None:
    value = _field(question, "correct_option_position", "correctOptionPosition", "correct_position")
    if isinstance(value, int):
        return str(value)
    options, is_distractors = _options(question)
    if is_distractors or not options:
        return None
    answer = normalize_value(_correct_answer(question))
    matches = [index for index, option in enumerate(options) if normalize_value(option) == answer]
    return str(matches[0] + 1) if len(matches) == 1 else None


@dataclass(frozen=True)
class BktEligibilityResult:
    valid_for_quiz: bool
    eligible_for_bkt: bool
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validForQuiz": self.valid_for_quiz,
            "eligibleForBkt": self.eligible_for_bkt,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_vocabulary_question(
    question: Any,
    *,
    approved_types: Iterable[str] = BKT_DIAGNOSTIC_TYPES,
    require_teacher_approval: bool = True,
) -> BktEligibilityResult:
    """Validate one question and derive its BKT eligibility.

    ``options_from_source`` is understood as a distractor pool for
    translation/cloze/synonym rows, matching the existing export contract.
    A runtime question with an ``options`` field is always treated as a full
    displayed option list unless it explicitly sets
    ``options_are_distractors``.
    """
    targets = _target_words(question)
    question_id = _question_id(question)
    word_id = targets[0] if len(targets) == 1 else None
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    kind = _question_type(question)
    answer = _correct_answer(question)
    options, is_distractors = _options(question)

    if not targets:
        errors.append(_issue("MISSING_TARGET_WORD", "ERROR", "Question has no primary target vocabulary word.", question, suggested_action="Assign exactly one word_id/target word."))
    elif len(targets) > 1:
        errors.append(_issue("MULTIPLE_TARGET_KCS", "ERROR", f"Question maps to {len(targets)} primary vocabulary targets.", question, suggested_action="Keep one primary word_id or move this item to general practice."))

    if not kind:
        errors.append(_issue("MISSING_QUESTION_TYPE", "ERROR", "Question type is missing.", question, suggested_action="Assign a deterministic question type."))
    if not answer:
        errors.append(_issue("MISSING_CORRECT_ANSWER", "ERROR", "Question has no correct answer.", question, suggested_action="Add one canonical correct answer."))

    normalized_options = [normalize_value(option) for option in options]
    if len(options) < 2:
        errors.append(_issue("INSUFFICIENT_OPTIONS", "ERROR", "MCQ needs at least two non-empty options.", question, word_id=word_id, suggested_action="Provide at least two non-empty alternatives."))
    if any(not option for option in options):
        errors.append(_issue("EMPTY_OPTION", "ERROR", "Question contains an empty option.", question, word_id=word_id, suggested_action="Replace or remove the empty option."))
    if len(normalized_options) != len(set(normalized_options)):
        errors.append(_issue("DUPLICATE_OPTIONS", "ERROR", "Options contain duplicate values after normalization.", question, word_id=word_id, suggested_action="Keep every displayed option unique."))

    normalized_answer = normalize_value(answer)
    if is_distractors:
        if normalized_answer in normalized_options:
            errors.append(_issue("CORRECT_ANSWER_IN_DISTRACTORS", "ERROR", "The correct answer appears in the distractor pool.", question, word_id=word_id, suggested_action="Remove the correct answer from the distractors."))
    elif normalized_answer:
        answer_count = normalized_options.count(normalized_answer)
        if answer_count == 0:
            errors.append(_issue("CORRECT_OPTION_MISSING", "ERROR", "The correct answer is not present in the displayed options.", question, word_id=word_id, suggested_action="Include exactly one correct option."))
        elif answer_count > 1:
            errors.append(_issue("MULTIPLE_CORRECT_ANSWERS", "ERROR", "The correct answer occurs more than once after normalization.", question, word_id=word_id, suggested_action="Remove the duplicated correct option."))

    if len(options) < 4 and len(options) >= 2:
        warnings.append(_issue("UNDER_FOUR_OPTIONS", "WARNING", f"Question has {len(options)} options; four is the preferred MCQ standard.", question, word_id=word_id, suggested_action="Add alternatives if the lesson vocabulary supports them."))

    for option in options:
        if _OBVIOUS_BAD_OPTION.match(option.strip()):
            warnings.append(_issue("MALFORMED_DISTRACTOR", "WARNING", f"Option {option!r} looks like a placeholder or malformed distractor.", question, word_id=word_id, suggested_action="Have a teacher replace the distractor with a plausible answer."))
    nonempty_lengths = [len(option) for option in options if option]
    if nonempty_lengths and max(nonempty_lengths) >= 3 * max(1, min(nonempty_lengths)):
        warnings.append(_issue("FORMAT_LENGTH_CLUE", "WARNING", "One option is dramatically longer than the others and may reveal the answer.", question, word_id=word_id, suggested_action="Review option wording and formatting for accidental clues."))

    visible = [_text(_field(question, name, default="")) for name in ("prompt", "image_alt", "imageAlt", "explanation", "audio_filename", "audioFilename", "html_data", "htmlData")]
    # The current listening UI renders an audio control and does not display
    # its word prompt. Its export row uses the canonical word as a placeholder,
    # so prompt leakage is not meaningful for that type.
    if kind != "listening" and normalized_answer and any(normalized_answer in normalize_value(text) for text in visible if text):
        errors.append(_issue("ANSWER_LEAKAGE", "ERROR", "The correct answer is exposed in pre-response content.", question, word_id=word_id, suggested_action="Remove the answer from the prompt, media metadata, explanation, or filename."))

    allowed_types = {normalize_value(value) for value in approved_types}
    if kind not in allowed_types:
        errors.append(_issue("UNSUPPORTED_BKT_QUESTION_TYPE", "ERROR", f"Question type {kind!r} is not approved for diagnostic BKT evidence.", question, word_id=word_id, suggested_action="Use an approved lexical diagnostic type or keep the response out of BKT."))

    status = _status(question)
    if require_teacher_approval and status not in _APPROVED_STATUSES:
        errors.append(_issue("UNAPPROVED_RESEARCH_ITEM", "ERROR", f"Question validation status is {status or 'missing'}, not APPROVED.", question, word_id=word_id, suggested_action="Have a teacher review and explicitly approve this item."))

    # A deterministic MCQ is binary by construction. Explicit non-binary
    # scoring metadata is rejected so later callers cannot accidentally feed
    # partial credit or confidence into standard BKT.
    scoring = normalize_value(_field(question, "scoring", "scoring_type", "scoringType", default="binary"))
    if scoring not in {"", "binary", "boolean", "deterministic"}:
        errors.append(_issue("NON_BINARY_SCORING", "ERROR", "Question declares non-binary scoring.", question, word_id=word_id, suggested_action="Store auxiliary scores separately and use only true/false for BKT."))

    hard_quiz_errors = {"MISSING_TARGET_WORD", "MULTIPLE_TARGET_KCS", "MISSING_QUESTION_TYPE", "MISSING_CORRECT_ANSWER", "INSUFFICIENT_OPTIONS", "EMPTY_OPTION", "DUPLICATE_OPTIONS", "CORRECT_ANSWER_IN_DISTRACTORS", "CORRECT_OPTION_MISSING", "MULTIPLE_CORRECT_ANSWERS", "ANSWER_LEAKAGE", "NON_BINARY_SCORING"}
    valid_for_quiz = not any(issue["code"] in hard_quiz_errors for issue in errors)
    eligible = valid_for_quiz and not errors
    return BktEligibilityResult(valid_for_quiz, eligible, errors, warnings)


def _diagnostic_slot(question: Any) -> str | None:
    value = _field(question, "diagnostic_quiz", "diagnosticQuiz", "quiz_number", "quizNumber", "quiz_id", "quizId")
    if value is not None:
        text = normalize_value(value).replace("easy quiz", "").replace("quiz", "").strip()
        if text in _SLOT_BY_VALUE:
            return _SLOT_BY_VALUE[text]
    mode = normalize_value(_field(question, "mode", default=""))
    if mode in _SLOT_BY_MODE:
        return _SLOT_BY_MODE[mode]
    # Do not infer that a generic easy tier is one of three diagnostic rounds.
    return None


def _word_label(word_id: str) -> str:
    return word_id


def _word_is_intended(question: Any, intended_words: set[str] | None) -> bool:
    if intended_words is None:
        return True
    return any(normalize_value(target) in {normalize_value(item) for item in intended_words} for target in _target_words(question))


def validate_bkt_diagnostic_design(
    questions: Iterable[Any],
    *,
    intended_words: Iterable[str] | None = None,
    approved_types: Iterable[str] = BKT_DIAGNOSTIC_TYPES,
    require_teacher_approval: bool = True,
    min_observations: int = MIN_DIAGNOSTIC_OBSERVATIONS,
) -> dict[str, Any]:
    """Validate the complete word -> diagnostic quiz 1/2/3 relationship."""
    question_list = list(questions)
    approved_types = tuple(normalize_value(value) for value in approved_types if normalize_value(value))
    intended = set(intended_words) if intended_words is not None else None
    by_word: dict[tuple[str, str, str], list[tuple[Any, BktEligibilityResult]]] = defaultdict(list)
    invalid_questions: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    position_counts: Counter[str] = Counter()

    for question in question_list:
        result = validate_vocabulary_question(question, approved_types=approved_types, require_teacher_approval=require_teacher_approval)
        if not result.eligible_for_bkt:
            invalid_questions.append({"question": _question_id(question), "errors": result.errors, "warnings": result.warnings})
        for target in _target_words(question):
            if not _word_is_intended(question, intended):
                continue
            story = _text(_field(question, "story_id", "storyId", default=""))
            level = normalize_value(_field(question, "level", "tier", default=""))
            key = (story, level, normalize_value(target))
            by_word[key].append((question, result))
            type_counts[_question_type(question)] += 1
            position = _position(question)
            if position:
                position_counts[position] += 1

    if intended is not None:
        for word in intended:
            by_word.setdefault(("", "", normalize_value(word)), [])

    word_rows: list[dict[str, Any]] = []
    for (story_id, level, normalized_word), entries in sorted(by_word.items()):
        valid_entries = [(question, result) for question, result in entries if result.eligible_for_bkt]
        slots: dict[str, list[tuple[Any, BktEligibilityResult]]] = {"quiz_1": [], "quiz_2": [], "quiz_3": []}
        unassigned: list[tuple[Any, BktEligibilityResult]] = []
        for question, result in entries:
            slot = _diagnostic_slot(question)
            (slots[slot] if slot else unassigned).append((question, result))

        ids = [_question_id(question) for question, _ in valid_entries]
        distinct_ids = set(ids)
        duplicate = len(ids) != len(distinct_ids)
        types = {_question_type(question) for question, _ in valid_entries if _question_type(question)}
        status = "PASS"
        if not entries:
            status = "MISSING_FROM_QUIZ"
        elif any(not result.eligible_for_bkt for _, result in entries):
            status = "INVALID_ITEM"
        elif duplicate:
            status = "DUPLICATE_ITEM"
        elif len(valid_entries) < min_observations:
            status = "INSUFFICIENT_EVIDENCE"
        elif any(not slots[slot] for slot in slots):
            status = "INSUFFICIENT_EVIDENCE"

        row = {
            "word_id": normalized_word,
            "word": _word_label(normalized_word),
            "story_id": story_id or None,
            "level": level or None,
            "lesson": next((_lesson_id(question) for question, _ in entries if _lesson_id(question)), None),
            "quiz_1_items": [_question_id(question) for question, _ in slots["quiz_1"]],
            "quiz_2_items": [_question_id(question) for question, _ in slots["quiz_2"]],
            "quiz_3_items": [_question_id(question) for question, _ in slots["quiz_3"]],
            "unassigned_items": [_question_id(question) for question, _ in unassigned],
            "distinct_item_count": len(distinct_ids),
            "distinct_question_type_count": len(types),
            "question_types": sorted(types),
            "bkt_eligible_observation_count": len(valid_entries),
            "teacher_validation": "APPROVED" if entries and all(_status(question) in _APPROVED_STATUSES for question, _ in entries) else "UNVERIFIED",
            "coverage_status": status,
        }
        if len(types) < MIN_TYPE_DIVERSITY and len(valid_entries) >= min_observations:
            row["type_diversity_warning"] = "INSUFFICIENT_TYPE_DIVERSITY"
        word_rows.append(row)

    total = len(question_list)
    eligible = sum(1 for question in question_list if validate_vocabulary_question(question, approved_types=approved_types, require_teacher_approval=require_teacher_approval).eligible_for_bkt)
    status_counts = Counter(row["coverage_status"] for row in word_rows)
    bank_rows = [
        {key: value for key, value in row.items() if key not in {"type_diversity_warning"}}
        for row in word_rows
    ]
    bank_hash = hashlib.sha256(
        json.dumps(bank_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    capacity_report = {
        slot: {
            "capacity": capacity,
            "requiredForCurrentWords": len(word_rows),
            "shortfall": max(0, len(word_rows) - capacity),
        }
        for slot, capacity in BKT_DIAGNOSTIC_CAPACITIES.items()
    }
    capacity_report["total"] = {
        "capacity": sum(BKT_DIAGNOSTIC_CAPACITIES.values()),
        "requiredForCurrentWords": len(word_rows) * min_observations,
        "shortfall": max(0, len(word_rows) * min_observations - sum(BKT_DIAGNOSTIC_CAPACITIES.values())),
    }
    scope_counts = Counter((row.get("story_id") or "", row.get("level") or "") for row in word_rows)
    capacity_report["byScope"] = {
        f"{story_id}:{level}".strip(":"): {
            "storyId": story_id or None,
            "level": level or None,
            "vocabularyWords": word_count,
            "requiredObservations": word_count * min_observations,
            "shortfall": max(0, word_count * min_observations - sum(BKT_DIAGNOSTIC_CAPACITIES.values())),
        }
        for (story_id, level), word_count in sorted(scope_counts.items())
    }
    return {
        "config": {
            "minDiagnosticObservations": min_observations,
            "minTypeDiversity": MIN_TYPE_DIVERSITY,
            "bktDiagnosticTypes": sorted({normalize_value(value) for value in approved_types}),
            "requireTeacherApproval": require_teacher_approval,
            "diagnosticQuizCapacities": BKT_DIAGNOSTIC_CAPACITIES,
        },
        "summary": {
            "vocabularyWords": len(word_rows),
            "pass": status_counts.get("PASS", 0),
            "warning": sum(1 for row in word_rows if row.get("type_diversity_warning")),
            "fail": sum(1 for row in word_rows if row["coverage_status"] != "PASS"),
            "questionsChecked": total,
            "bktEligible": eligible,
            "bktIneligible": total - eligible,
        },
        "words": word_rows,
        "invalidQuestions": invalid_questions,
        "questionTypeDistribution": dict(sorted(type_counts.items())),
        "correctOptionPositionDistribution": dict(sorted(position_counts.items())),
        "capacity": capacity_report,
        "bankHash": bank_hash,
    }


def analyze_response_quality(
    attempts: Iterable[Any],
    *,
    min_responses: int = DIFFICULTY_MIN_RESPONSES,
) -> dict[str, Any]:
    """Produce pilot-quality item/type reports without feeding time into BKT."""
    item_stats: dict[str, list[bool]] = defaultdict(list)
    type_stats: dict[str, list[tuple[bool, float | None]]] = defaultdict(list)
    for attempt in attempts:
        results = _field(attempt, "questionResults", "question_results", default=[])
        if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
            continue
        for result in results:
            if _field(result, "isBktEligible", "is_bkt_eligible", default=False) is not True:
                continue
            correct = _field(result, "correct", default=None)
            if not isinstance(correct, bool):
                continue
            item = _text(_field(result, "itemId", "item_id", default="")) or _text(_field(result, "word", default=""))
            kind = normalize_value(_field(result, "questionKind", "question_kind", default="")) or "unknown"
            time_value = _field(result, "timeMs", "time_ms", default=None)
            response_time = float(time_value) if isinstance(time_value, (int, float)) and not isinstance(time_value, bool) and time_value >= 0 else None
            item_stats[item].append(correct)
            type_stats[kind].append((correct, response_time))

    item_report = []
    for item, outcomes in sorted(item_stats.items()):
        accuracy = sum(outcomes) / len(outcomes)
        flags = []
        if len(outcomes) >= min_responses and accuracy > CEILING_ACCURACY:
            flags.append("POSSIBLE_CEILING_ITEM")
        if len(outcomes) >= min_responses and accuracy < FLOOR_ACCURACY:
            flags.append("POSSIBLE_FLOOR_ITEM")
        item_report.append({"itemId": item, "nResponses": len(outcomes), "accuracy": accuracy, "flags": flags})

    type_report = []
    for kind, values in sorted(type_stats.items()):
        times = sorted(value for _, value in values if value is not None)
        median = None
        if times:
            middle = len(times) // 2
            median = times[middle] if len(times) % 2 else (times[middle - 1] + times[middle]) / 2
        type_report.append({"questionType": kind, "n": len(values), "accuracy": sum(value[0] for value in values) / len(values), "medianResponseTime": median})
    return {
        "pilotQualityHeuristics": {"ceilingAccuracyGreaterThan": CEILING_ACCURACY, "floorAccuracyLessThan": FLOOR_ACCURACY, "minimumResponses": min_responses},
        "items": item_report,
        "questionTypes": type_report,
    }


def classify_bkt_response(
    result: Any,
    attempt: Any | None = None,
    *,
    approved_types: Iterable[str] = BKT_DIAGNOSTIC_TYPES,
) -> tuple[bool, list[str]]:
    """Apply the server-side response gate before a response reaches BKT.

    All raw responses may still be persisted.  This function only answers
    whether the response is safe for standard binary, word-level BKT.
    """
    errors: list[str] = []
    if _field(result, "isBktEligible", "is_bkt_eligible", default=None) is not True:
        errors.append("BKT_ELIGIBILITY_NOT_TRUE")
    if not isinstance(_field(result, "correct", default=None), bool):
        errors.append("INVALID_BINARY_OUTCOME")
    if not _text(_field(result, "itemId", "item_id", default="")):
        errors.append("MISSING_ITEM_ID")
    concept = _text(_field(result, "conceptId", "concept_id", default=""))
    word = _text(_field(result, "word", default=""))
    if not concept or not word:
        errors.append("MISSING_TARGET_WORD")
    elif normalize_value(concept) != normalize_value(word):
        errors.append("CONCEPT_WORD_MISMATCH")
    kind = _question_type(result)
    if kind not in {normalize_value(value) for value in approved_types}:
        errors.append("UNSUPPORTED_BKT_QUESTION_TYPE")
    if _text(_field(result, "level", default="")) != "easy":
        errors.append("NON_DIAGNOSTIC_LEVEL")
    mode = normalize_value(_field(attempt, "mode", default="")) if attempt is not None else ""
    if mode not in _SLOT_BY_MODE:
        errors.append("NON_DIAGNOSTIC_MODE")
    if _field(result, "assistedResponse", "assisted_response", default=False) is True:
        errors.append("ASSISTED_RESPONSE")
    if _field(result, "bktValidationStatus", "bkt_validation_status", default=None) != "APPROVED":
        errors.append("UNAPPROVED_RESEARCH_ITEM")
    if not _text(_field(result, "diagnosticExposureId", "diagnostic_exposure_id", default="")):
        errors.append("MISSING_DIAGNOSTIC_EXPOSURE")
    return not errors, list(dict.fromkeys(errors))


def write_report(report: Mapping[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_coverage_csv(report: Mapping[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = report.get("words", [])
    fields = ["story_id", "level", "word_id", "word", "lesson", "quiz_1_items", "quiz_2_items", "quiz_3_items", "unassigned_items", "distinct_item_count", "distinct_question_type_count", "bkt_eligible_observation_count", "teacher_validation", "coverage_status"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            values = dict(row)
            for field_name in ("quiz_1_items", "quiz_2_items", "quiz_3_items", "unassigned_items"):
                values[field_name] = "; ".join(values.get(field_name, []))
            writer.writerow({field_name: values.get(field_name, "") for field_name in fields})
    return path
