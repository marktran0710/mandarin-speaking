"""Import and validate a three-round vocabulary assessment CSV.

This module deliberately keeps assessment content separate from learning-model
configuration. It validates one Easy/Medium/Hard observation per lesson word;
the lesson decides the word count.
"""

from __future__ import annotations

import csv
import io
import json
import random
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence, TextIO

try:  # The backend already depends on opencc-python-reimplemented.
    from opencc import OpenCC
except ImportError:  # pragma: no cover - keeps this pure module importable in minimal tools.
    OpenCC = None  # type: ignore[assignment,misc]


LEVELS = ("Easy", "Medium", "Hard")
# Compatibility exports for older reports. Validation below is dynamic and
# does not require these sample-course values.
EXPECTED_WORD_COUNT = 15
EXPECTED_QUESTION_COUNT = EXPECTED_WORD_COUNT * len(LEVELS)
MCQ_LEVELS = frozenset({"Easy", "Medium"})
QUESTION_TYPE_BY_LEVEL = {
    "Easy": "basic_meaning_mcq",
    "Medium": "context_cloze_mcq",
    "Hard": "productive_recall",
}
_REQUIRED_COLUMNS = frozenset({
    "word_id", "target_word", "pinyin", "pos", "simple_english_meaning",
    "level", "difficulty_weight", "question_type", "answer_format", "prompt",
    "options_json", "correct_answer", "accepted_answers_json", "explanation",
})
_WHITESPACE_OR_PUNCTUATION = re.compile(r"[\s\W_]+", re.UNICODE)
_S2T = OpenCC("s2t") if OpenCC is not None else None
# OpenCC's s2t dictionary prefers 喫 for 吃, although 吃 is standard
# Traditional Chinese in the supplied Taiwan-oriented course material.
_TRADITIONAL_VARIANT_CHARACTERS = frozenset({"吃"})


@dataclass(frozen=True)
class VocabularyQuestion:
    word_id: str
    target_word: str
    pinyin: str
    part_of_speech: str
    simple_english_meaning: str
    level: str
    difficulty_weight: int
    question_type: str
    answer_format: str
    prompt: str
    options: tuple[str, ...]
    correct_answer: str
    accepted_answers: tuple[str, ...]
    explanation: str
    raw: Mapping[str, str]

    @property
    def question_id(self) -> str:
        return f"{self.word_id}_{self.level.upper()}"


@dataclass(frozen=True)
class VocabularyItem:
    word_id: str
    target_word: str
    pinyin: str
    part_of_speech: str
    simple_english_meaning: str
    observations: tuple[VocabularyQuestion, VocabularyQuestion, VocabularyQuestion]

    def observation_for(self, level: str) -> VocabularyQuestion:
        canonical_level = _canonical_level(level)
        for observation in self.observations:
            if observation.level == canonical_level:
                return observation
        raise KeyError(f"{self.word_id} has no {canonical_level} observation")


@dataclass(frozen=True)
class AssessmentValidationIssue:
    code: str
    message: str
    question_id: str | None = None
    word_id: str | None = None


def _canonical_level(value: str) -> str:
    normalized = value.strip().casefold()
    for level in LEVELS:
        if normalized == level.casefold():
            return level
    return value.strip()


def _parse_json_string_list(value: str, *, field: str, row_number: int) -> tuple[str, ...]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(f"row {row_number}: {field} must be valid JSON") from exc
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise ValueError(f"row {row_number}: {field} must be a JSON array of strings")
    return tuple(item.strip() for item in parsed)


def _question_from_row(row: Mapping[str, str], row_number: int) -> VocabularyQuestion:
    missing = _REQUIRED_COLUMNS.difference(row)
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")
    try:
        weight = int((row.get("difficulty_weight") or "").strip())
    except ValueError as exc:
        raise ValueError(f"row {row_number}: difficulty_weight must be an integer") from exc
    return VocabularyQuestion(
        word_id=(row.get("word_id") or "").strip(),
        target_word=(row.get("target_word") or "").strip(),
        pinyin=(row.get("pinyin") or "").strip(),
        part_of_speech=(row.get("pos") or "").strip(),
        simple_english_meaning=(row.get("simple_english_meaning") or "").strip(),
        level=_canonical_level(row.get("level") or ""),
        difficulty_weight=weight,
        question_type=(row.get("question_type") or "").strip(),
        answer_format=(row.get("answer_format") or "").strip(),
        prompt=(row.get("prompt") or "").strip(),
        options=_parse_json_string_list(row.get("options_json") or "", field="options_json", row_number=row_number),
        correct_answer=(row.get("correct_answer") or "").strip(),
        accepted_answers=_parse_json_string_list(row.get("accepted_answers_json") or "", field="accepted_answers_json", row_number=row_number),
        explanation=(row.get("explanation") or "").strip(),
        raw=dict(row),
    )


def parse_vocab_assessment_csv(source: Path | str | TextIO) -> list[VocabularyQuestion]:
    """Read UTF-8 CSV rows and parse the two JSON-array fields.

    A string may be either CSV text or a filesystem path.  The returned list
    keeps source ordering and each question retains its unmodified raw row.
    """
    if hasattr(source, "read"):
        reader_source = source
        close_after = False
    elif isinstance(source, Path) or ("\n" not in source and Path(source).is_file()):
        reader_source = Path(source).open(encoding="utf-8-sig", newline="")
        close_after = True
    else:
        reader_source = io.StringIO(source)
        close_after = True
    try:
        reader = csv.DictReader(reader_source)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        missing = _REQUIRED_COLUMNS.difference(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")
        return [_question_from_row(row, index) for index, row in enumerate(reader, start=2)]
    finally:
        if close_after:
            reader_source.close()


def build_vocabulary_items(questions: Iterable[VocabularyQuestion]) -> list[VocabularyItem]:
    """Group observations into vocabulary items after validating their shape."""
    question_list = list(questions)
    issues = validate_vocab_assessment(question_list)
    if issues:
        rendered = "; ".join(f"{issue.code}: {issue.message}" for issue in issues)
        raise ValueError(rendered)
    by_word: dict[str, list[VocabularyQuestion]] = defaultdict(list)
    for question in question_list:
        by_word[question.word_id].append(question)
    items: list[VocabularyItem] = []
    for word_id, observations in by_word.items():
        by_level = {observation.level: observation for observation in observations}
        first = observations[0]
        items.append(VocabularyItem(
            word_id=word_id,
            target_word=first.target_word,
            pinyin=first.pinyin,
            part_of_speech=first.part_of_speech,
            simple_english_meaning=first.simple_english_meaning,
            observations=tuple(by_level[level] for level in LEVELS),  # type: ignore[arg-type]
        ))
    return items


def raw_observations_by_word(questions: Iterable[VocabularyQuestion]) -> dict[str, list[Mapping[str, str]]]:
    """Return raw source observations without de-duplicating repeated rows."""
    grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for question in questions:
        grouped[question.word_id].append(question.raw)
    return dict(grouped)


def validate_assessment_payload(payload: object) -> list[AssessmentValidationIssue]:
    """Validate the camelCase JSON form used by the story API.

    The CSV importer is the normal entry point, but the API also accepts a
    prebuilt bank for round trips. Keeping this boundary strict prevents an
    unvalidated payload from bypassing the fixed assessment contract.
    """
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        return [AssessmentValidationIssue("PAYLOAD_NOT_LIST", "vocabAssessment must be a list.")]
    questions: list[VocabularyQuestion] = []
    issues: list[AssessmentValidationIssue] = []
    for index, row in enumerate(payload, start=1):
        if not isinstance(row, Mapping):
            issues.append(AssessmentValidationIssue("PAYLOAD_ROW_INVALID", f"Question {index} must be an object."))
            continue
        options = row.get("options", [])
        accepted = row.get("acceptedAnswers", [])
        if not isinstance(options, Sequence) or isinstance(options, (str, bytes)) or any(not isinstance(value, str) for value in options):
            issues.append(AssessmentValidationIssue("PAYLOAD_OPTIONS_INVALID", f"Question {index} options must be a list of strings."))
            options = []
        if not isinstance(accepted, Sequence) or isinstance(accepted, (str, bytes)) or any(not isinstance(value, str) for value in accepted):
            issues.append(AssessmentValidationIssue("PAYLOAD_ACCEPTED_ANSWERS_INVALID", f"Question {index} acceptedAnswers must be a list of strings."))
            accepted = []
        try:
            weight = int(row.get("difficultyWeight", 0))
        except (TypeError, ValueError):
            weight = 0
        question = VocabularyQuestion(
            word_id=str(row.get("wordId", "")).strip(),
            target_word=str(row.get("targetWord", "")).strip(),
            pinyin=str(row.get("pinyin", "")).strip(),
            part_of_speech=str(row.get("pos", "")).strip(),
            simple_english_meaning=str(row.get("simpleEnglishMeaning", "")).strip(),
            level=_canonical_level(str(row.get("level", ""))),
            difficulty_weight=weight,
            question_type=str(row.get("questionType", "")).strip(),
            answer_format=str(row.get("answerFormat", "")).strip(),
            prompt=str(row.get("prompt", "")).strip(),
            options=tuple(value.strip() for value in options),
            correct_answer=str(row.get("correctAnswer", "")).strip(),
            accepted_answers=tuple(value.strip() for value in accepted),
            explanation=str(row.get("explanation", "")).strip(),
            raw=row,
        )
        expected_question_id = question.question_id
        if row.get("questionId") != expected_question_id:
            issues.append(AssessmentValidationIssue(
                "INVALID_QUESTION_ID",
                f"questionId must be {expected_question_id}.",
                str(row.get("questionId") or expected_question_id),
                question.word_id or None,
            ))
        questions.append(question)
    return issues + validate_vocab_assessment(questions)


def normalize_answer(value: str) -> str:
    """Normalize presentation differences only; it never converts Simplified Chinese."""
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return _WHITESPACE_OR_PUNCTUATION.sub("", normalized)


def answer_is_accepted(question: VocabularyQuestion, answer: str) -> bool:
    normalized_answer = normalize_answer(answer)
    return bool(normalized_answer) and any(
        normalized_answer == normalize_answer(accepted)
        for accepted in question.accepted_answers
    )


def shuffled_options(question: VocabularyQuestion, *, seed: str = "assessment") -> tuple[str, ...]:
    """Return a deterministic display order while preserving every MCQ option."""
    options = list(question.options)
    random.Random(f"{seed}:{question.question_id}").shuffle(options)
    return tuple(options)


def _contains_simplified_chinese(value: str) -> bool:
    if _S2T is None:
        return False
    return any(
        character not in _TRADITIONAL_VARIANT_CHARACTERS
        and _S2T.convert(character) != character
        for character in value
    )


def validate_vocab_assessment(questions: Sequence[VocabularyQuestion]) -> list[AssessmentValidationIssue]:
    """Validate dynamic lesson coverage: each word has one of each level."""
    issues: list[AssessmentValidationIssue] = []
    expected_question_count = len({question.word_id for question in questions if question.word_id}) * len(LEVELS)
    if expected_question_count and len(questions) != expected_question_count:
        issues.append(AssessmentValidationIssue(
            "QUESTION_COUNT", f"Expected {expected_question_count} questions for the supplied words, found {len(questions)}."
        ))
    by_word: dict[str, list[VocabularyQuestion]] = defaultdict(list)
    seen_ids: set[str] = set()
    for question in questions:
        by_word[question.word_id].append(question)
        question_id = question.question_id
        if question_id in seen_ids:
            issues.append(AssessmentValidationIssue("DUPLICATE_QUESTION_ID", f"Duplicate question id {question_id}.", question_id, question.word_id))
        seen_ids.add(question_id)
        if question.level not in LEVELS:
            issues.append(AssessmentValidationIssue("INVALID_LEVEL", "Level must be Easy, Medium, or Hard.", question_id, question.word_id))
        if not all((question.word_id, question.target_word, question.pinyin, question.part_of_speech, question.simple_english_meaning, question.question_type, question.prompt, question.correct_answer, question.explanation)):
            issues.append(AssessmentValidationIssue("MISSING_REQUIRED_VALUE", "Question has an empty required value.", question_id, question.word_id))
        if question.difficulty_weight != {"Easy": 1, "Medium": 2, "Hard": 3}.get(question.level):
            issues.append(AssessmentValidationIssue("INVALID_DIFFICULTY_WEIGHT", "Difficulty weight must match its level.", question_id, question.word_id))
        if question.level in QUESTION_TYPE_BY_LEVEL and question.question_type != QUESTION_TYPE_BY_LEVEL[question.level]:
            issues.append(AssessmentValidationIssue(
                "INVALID_QUESTION_TYPE",
                f"{question.level} observations must use {QUESTION_TYPE_BY_LEVEL[question.level]}.",
                question_id,
                question.word_id,
            ))
        if not question.accepted_answers or normalize_answer(question.correct_answer) not in {normalize_answer(value) for value in question.accepted_answers}:
            issues.append(AssessmentValidationIssue("INVALID_ACCEPTED_ANSWERS", "Accepted answers must include the canonical correct answer.", question_id, question.word_id))
        chinese_values = (question.target_word, question.prompt, question.correct_answer, question.explanation, *question.options, *question.accepted_answers)
        if any(_contains_simplified_chinese(value) for value in chinese_values):
            issues.append(AssessmentValidationIssue("SIMPLIFIED_CHINESE", "Assessment content must use Traditional Chinese.", question_id, question.word_id))

        normalized_options = [normalize_answer(option) for option in question.options]
        if question.level in MCQ_LEVELS:
            if question.answer_format != "single_choice":
                issues.append(AssessmentValidationIssue("INVALID_MCQ_FORMAT", "Easy and Medium observations must be single-choice MCQs.", question_id, question.word_id))
            if len(question.options) != 4 or any(not option for option in question.options):
                issues.append(AssessmentValidationIssue("INVALID_MCQ_OPTIONS", "MCQs require exactly four non-empty options.", question_id, question.word_id))
            if len(normalized_options) != len(set(normalized_options)):
                issues.append(AssessmentValidationIssue("DUPLICATE_MCQ_OPTIONS", "MCQ options must be unique after answer normalization.", question_id, question.word_id))
            if normalized_options.count(normalize_answer(question.correct_answer)) != 1:
                issues.append(AssessmentValidationIssue("INVALID_MCQ_CORRECT_OPTION", "MCQs must contain exactly one canonical correct option.", question_id, question.word_id))
        elif question.level == "Hard":
            if question.answer_format != "free_text":
                issues.append(AssessmentValidationIssue("INVALID_HARD_FORMAT", "Hard observations must use free text.", question_id, question.word_id))
            if question.options:
                issues.append(AssessmentValidationIssue("HARD_HAS_OPTIONS", "Hard observations must not expose options.", question_id, question.word_id))

    for word_id, observations in by_word.items():
        levels = [observation.level for observation in observations]
        if set(levels) != set(LEVELS) or len(observations) != len(LEVELS):
            issues.append(AssessmentValidationIssue("LEVEL_COVERAGE", "Each word must have exactly one Easy, Medium, and Hard observation.", word_id=word_id))
        first = observations[0] if observations else None
        if first and any((observation.target_word, observation.pinyin, observation.part_of_speech, observation.simple_english_meaning) != (first.target_word, first.pinyin, first.part_of_speech, first.simple_english_meaning) for observation in observations[1:]):
            issues.append(AssessmentValidationIssue("INCONSISTENT_WORD_METADATA", "Observations for one word must share vocabulary metadata.", word_id=word_id))
    return issues
