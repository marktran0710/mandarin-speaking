"""Import and validate the canonical three-round vocabulary assessment bank.

The public bank contract is deliberately numeric and question-type based:
each word has exactly one observation for rounds 1, 2, and 3. Difficulty
labels are not part of the stored assessment shape.
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


ROUNDS = (1, 2, 3)
EXPECTED_WORD_COUNT = 15
EXPECTED_QUESTION_COUNT = EXPECTED_WORD_COUNT * len(ROUNDS)
QUESTION_TYPE_BY_ROUND = {
    1: "basic_meaning_mcq",
    2: "character_to_pinyin_typing",
    3: "context_cloze_mcq",
}
ANSWER_FORMAT_BY_ROUND = {1: "single_choice", 2: "free_text", 3: "single_choice"}
TIER_BY_ROUND = {1: "tier1", 2: "tier2", 3: "tier3"}
SUPPORTED_QUESTION_TYPES = frozenset(QUESTION_TYPE_BY_ROUND.values())
_REQUIRED_COLUMNS = frozenset({
    "word_id", "target_word", "pinyin", "pos", "simple_english_meaning",
    "round", "question_type", "answer_format", "prompt",
    "options_json", "correct_answer", "accepted_answers_json", "explanation",
})
_WHITESPACE_OR_PUNCTUATION = re.compile(r"[\s\W_]+", re.UNICODE)
_S2T = OpenCC("s2t") if OpenCC is not None else None
# OpenCC's s2t dictionary prefers alternate forms for a few characters that
# are standard in the supplied Taiwan-oriented course material. Keep the
# textbook spellings accepted instead of rewriting the source content:
# 喫/吃, 牀/床, 臺/台, 晒/曬 (the supplied lesson 5-3 variant), and 游 in
# the textbook's standard 游泳 spelling (OpenCC maps the single character to
# 遊 even though 游泳 is the source's intended Traditional form).
_TRADITIONAL_VARIANT_CHARACTERS = frozenset({"吃", "床", "台", "晒", "游"})


@dataclass(frozen=True)
class VocabularyQuestion:
    word_id: str
    target_word: str
    pinyin: str
    part_of_speech: str
    simple_english_meaning: str
    round: int
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
        raw_id = self.raw.get("questionId") or self.raw.get("question_id") or self.raw.get("Question ID")
        return str(raw_id).strip() if raw_id else f"{self.word_id}:round:{self.round}"

    @property
    def tier(self) -> str:
        return TIER_BY_ROUND[self.round]


@dataclass(frozen=True)
class VocabularyItem:
    word_id: str
    target_word: str
    pinyin: str
    part_of_speech: str
    simple_english_meaning: str
    observations: tuple[VocabularyQuestion, VocabularyQuestion, VocabularyQuestion]

    def observation_for(self, round_number: int | str) -> VocabularyQuestion:
        canonical_round = _canonical_round(round_number)
        for observation in self.observations:
            if observation.round == canonical_round:
                return observation
        raise KeyError(f"{self.word_id} has no round {canonical_round} observation")


@dataclass(frozen=True)
class AssessmentValidationIssue:
    code: str
    message: str
    question_id: str | None = None
    word_id: str | None = None


def _canonical_round(value: int | str) -> int:
    normalized = str(value).strip().casefold().replace("round", "").strip()
    try:
        round_number = int(normalized)
    except ValueError:
        return 0
    return round_number if round_number in ROUNDS else 0


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
    round_number = _canonical_round(row.get("round") or "")
    if round_number not in ROUNDS:
        raise ValueError(f"row {row_number}: round must be 1, 2, or 3")
    return VocabularyQuestion(
        word_id=(row.get("word_id") or "").strip(),
        target_word=(row.get("target_word") or "").strip(),
        pinyin=(row.get("pinyin") or "").strip(),
        part_of_speech=(row.get("pos") or "").strip(),
        simple_english_meaning=(row.get("simple_english_meaning") or "").strip(),
        round=round_number,
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
        by_round = {observation.round: observation for observation in observations}
        first = observations[0]
        items.append(VocabularyItem(
            word_id=word_id,
            target_word=first.target_word,
            pinyin=first.pinyin,
            part_of_speech=first.part_of_speech,
            simple_english_meaning=first.simple_english_meaning,
            observations=tuple(by_round[round_number] for round_number in ROUNDS),
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
        legacy_fields = [field for field in ("level", "difficultyWeight", "sourceQuestionId") if field in row]
        if legacy_fields:
            issues.append(AssessmentValidationIssue(
                "LEGACY_ASSESSMENT_FIELDS",
                "Assessment questions must use round/tier and source questionId; remove " + ", ".join(legacy_fields) + ".",
                str(row.get("questionId") or "") or None,
                str(row.get("wordId") or "") or None,
            ))
        if not isinstance(options, Sequence) or isinstance(options, (str, bytes)) or any(not isinstance(value, str) for value in options):
            issues.append(AssessmentValidationIssue("PAYLOAD_OPTIONS_INVALID", f"Question {index} options must be a list of strings."))
            options = []
        if not isinstance(accepted, Sequence) or isinstance(accepted, (str, bytes)) or any(not isinstance(value, str) for value in accepted):
            issues.append(AssessmentValidationIssue("PAYLOAD_ACCEPTED_ANSWERS_INVALID", f"Question {index} acceptedAnswers must be a list of strings."))
            accepted = []
        round_number = _canonical_round(row.get("round", ""))
        question = VocabularyQuestion(
            word_id=str(row.get("wordId", "")).strip(),
            target_word=str(row.get("targetWord", "")).strip(),
            pinyin=str(row.get("pinyin", "")).strip(),
            part_of_speech=str(row.get("pos", "")).strip(),
            simple_english_meaning=str(row.get("simpleEnglishMeaning", "")).strip(),
            round=round_number,
            question_type=str(row.get("questionType", "")).strip(),
            answer_format=str(row.get("answerFormat", "")).strip(),
            prompt=str(row.get("prompt", "")).strip(),
            options=tuple(value.strip() for value in options),
            correct_answer=str(row.get("correctAnswer", "")).strip(),
            accepted_answers=tuple(value.strip() for value in accepted),
            explanation=str(row.get("explanation", "")).strip(),
            raw=row,
        )
        question_id = str(row.get("questionId") or "").strip()
        if not question_id:
            issues.append(AssessmentValidationIssue(
                "INVALID_QUESTION_ID",
                "questionId is required and must be the source bank question id.",
                None,
                question.word_id or None,
            ))
        elif question_id.casefold().endswith(("_easy", "_medium", "_hard")):
            issues.append(AssessmentValidationIssue(
                "LEGACY_QUESTION_ID",
                "questionId must not use an Easy/Medium/Hard suffix.",
                question_id,
                question.word_id or None,
            ))
        question = VocabularyQuestion(**{**question.__dict__, "raw": {**question.raw, "questionId": question_id}})
        questions.append(question)
    return issues + validate_vocab_assessment(questions)


def normalize_answer(value: str) -> str:
    """Normalize presentation differences only; it never converts Simplified Chinese."""
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return _WHITESPACE_OR_PUNCTUATION.sub("", normalized)


# Tone-mark tables indexed 0-4 (tone 1-4 plus neutral/5 = no mark). This mirrors
# the frontend ``numericToToneMarked`` in ``utils/pinyin.ts`` so a pinyin answer
# typed with tone numbers grades identically on both sides.
_TONE_MARKS = {
    "a": ["ā", "á", "ǎ", "à", "a"],
    "e": ["ē", "é", "ě", "è", "e"],
    "i": ["ī", "í", "ǐ", "ì", "i"],
    "o": ["ō", "ó", "ǒ", "ò", "o"],
    "u": ["ū", "ú", "ǔ", "ù", "u"],
    "v": ["ǖ", "ǘ", "ǚ", "ǜ", "ü"],
}
_TONED_SYLLABLE = re.compile(r"^([^aeiouvü]*)([aeiouvü]+)([^aeiouvü\d]*)([1-5])$", re.IGNORECASE)
_NUMERIC_SYLLABLE = re.compile(r"[a-zü]+[1-5]", re.IGNORECASE)


def _apply_syllable_tone(syllable: str) -> str:
    match = _TONED_SYLLABLE.match(syllable)
    if not match:
        return syllable
    onset, nucleus, coda, tone_digit = match.groups()
    tone = int(tone_digit) - 1
    lower = nucleus.lower()
    if "a" in lower:
        marked = re.sub("a", _TONE_MARKS["a"][tone], nucleus, count=1, flags=re.IGNORECASE)
    elif "e" in lower:
        marked = re.sub("e", _TONE_MARKS["e"][tone], nucleus, count=1, flags=re.IGNORECASE)
    elif lower == "ou":
        marked = _TONE_MARKS["o"][tone] + "u"
    else:
        # No a/e and not "ou": the tone mark falls on the LAST vowel of the
        # cluster (ui->i, iu->u, uo->o). The earlier a/e/ou rules cover every
        # case where the mark is not on the final vowel.
        index = len(nucleus) - 1
        key = "v" if lower[index] == "ü" else lower[index]
        marked = nucleus[:index] + _TONE_MARKS[key][tone] + nucleus[index + 1:]
    return onset + marked + coda


def numeric_to_tone_marked(value: str) -> str:
    """Convert numeric pinyin ("wo3 men5") to tone-marked pinyin ("wǒ men")."""
    return _NUMERIC_SYLLABLE.sub(lambda match: _apply_syllable_tone(match.group(0)), str(value))


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
    """Validate dynamic lesson coverage: each word has one of each round."""
    issues: list[AssessmentValidationIssue] = []
    expected_question_count = len({question.word_id for question in questions if question.word_id}) * len(ROUNDS)
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
        if question.round not in ROUNDS:
            issues.append(AssessmentValidationIssue("INVALID_ROUND", "Round must be 1, 2, or 3.", question_id, question.word_id))
        if not all((question.word_id, question.target_word, question.pinyin, question.part_of_speech, question.simple_english_meaning, question.question_type, question.prompt, question.correct_answer, question.explanation)):
            issues.append(AssessmentValidationIssue("MISSING_REQUIRED_VALUE", "Question has an empty required value.", question_id, question.word_id))
        expected_type = QUESTION_TYPE_BY_ROUND.get(question.round)
        expected_format = ANSWER_FORMAT_BY_ROUND.get(question.round)
        if question.question_type not in SUPPORTED_QUESTION_TYPES:
            issues.append(AssessmentValidationIssue(
                "INVALID_QUESTION_TYPE",
                f"Unsupported question type {question.question_type}.",
                question_id,
                question.word_id,
            ))
        elif question.question_type != expected_type:
            issues.append(AssessmentValidationIssue(
                "INVALID_QUESTION_TYPE_FOR_ROUND",
                f"Round {question.round} requires {expected_type}.",
                question_id,
                question.word_id,
            ))
        elif question.answer_format != expected_format:
            issues.append(AssessmentValidationIssue(
                "INVALID_ANSWER_FORMAT",
                f"Round {question.round} requires {expected_format}.",
                question_id,
                question.word_id,
            ))
        if not question.accepted_answers or normalize_answer(question.correct_answer) not in {normalize_answer(value) for value in question.accepted_answers}:
            issues.append(AssessmentValidationIssue("INVALID_ACCEPTED_ANSWERS", "Accepted answers must include the canonical correct answer.", question_id, question.word_id))
        chinese_values = (question.target_word, question.prompt, question.correct_answer, question.explanation, *question.options, *question.accepted_answers)
        if any(_contains_simplified_chinese(value) for value in chinese_values):
            issues.append(AssessmentValidationIssue("SIMPLIFIED_CHINESE", "Assessment content must use Traditional Chinese.", question_id, question.word_id))

        normalized_options = [normalize_answer(option) for option in question.options]
        if question.answer_format == "single_choice":
            if len(question.options) != 4 or any(not option for option in question.options):
                issues.append(AssessmentValidationIssue("INVALID_MCQ_OPTIONS", "MCQs require exactly four non-empty options.", question_id, question.word_id))
            if len(normalized_options) != len(set(normalized_options)):
                issues.append(AssessmentValidationIssue("DUPLICATE_MCQ_OPTIONS", "MCQ options must be unique after answer normalization.", question_id, question.word_id))
            if normalized_options.count(normalize_answer(question.correct_answer)) != 1:
                issues.append(AssessmentValidationIssue("INVALID_MCQ_CORRECT_OPTION", "MCQs must contain exactly one canonical correct option.", question_id, question.word_id))
        elif question.answer_format == "free_text":
            if question.options:
                issues.append(AssessmentValidationIssue(
                    "FREE_TEXT_HAS_OPTIONS",
                    "Free-text questions must not expose options.",
                    question_id,
                    question.word_id,
                ))

    for word_id, observations in by_word.items():
        rounds = [observation.round for observation in observations]
        if set(rounds) != set(ROUNDS) or len(observations) != len(ROUNDS):
            issues.append(AssessmentValidationIssue("ROUND_COVERAGE", "Each word must have exactly one round 1, 2, and 3 observation.", word_id=word_id))
        first = observations[0] if observations else None
        if first and any((observation.target_word, observation.pinyin, observation.part_of_speech, observation.simple_english_meaning) != (first.target_word, first.pinyin, first.part_of_speech, first.simple_english_meaning) for observation in observations[1:]):
            issues.append(AssessmentValidationIssue("INCONSISTENT_WORD_METADATA", "Observations for one word must share vocabulary metadata.", word_id=word_id))
    return issues
