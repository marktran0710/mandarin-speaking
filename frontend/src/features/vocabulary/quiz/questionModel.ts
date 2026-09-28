import type {
  VocabQuizEntry,
  VocabQuizQuestion,
  VocabQuizQuestionResult,
} from "@entities/vocabulary";
import { numericToToneMarked, toPinyin, toPinyinSyllables } from "@entities/vocabulary";
import type { StudentUiCopyKey } from "../../../i18n/student-ui-copy";

export type QuizQuestionSurface = "meaning" | "pinyin" | "context";

export interface ClozeSentenceParts {
  before: string;
  after: string;
  hasBlank: boolean;
}

export interface QuestionPresentation {
  surface: QuizQuestionSurface;
  label: string;
  labelKey: StudentUiCopyKey;
  prompt: string;
  promptKey?: StudentUiCopyKey;
  promptData?: string;
  pinyin?: string;
  audioUrl?: string;
  explanation?: string;
}

const QUESTION_TYPE_LABELS: Record<string, { label: string; key: StudentUiCopyKey }> = {
  basic_meaning_mcq: { label: "Meaning check", key: "meaningCheck" },
  character_to_pinyin_typing: { label: "Reading recall", key: "readingRecall" },
  context_cloze_mcq: { label: "Sentence completion", key: "sentenceCompletion" },
  productive_recall: { label: "Active recall", key: "activeRecall" },
  contextual_productive_recall: { label: "Context recall", key: "contextRecall" },
};

const QUESTION_KIND_LABELS: Record<VocabQuizQuestion["kind"], { label: string; key: StudentUiCopyKey }> = {
  translation: { label: "Meaning check", key: "meaningCheck" },
  cloze: { label: "Sentence completion", key: "sentenceCompletion" },
  pinyin: { label: "Reading recall", key: "readingRecall" },
  pos: { label: "Word class", key: "wordClass" },
  synonym: { label: "Related meaning", key: "relatedMeaning" },
  reverse: { label: "Character recall", key: "characterRecall" },
  listening: { label: "Listening check", key: "listeningCheck" },
  assessment: { label: "Assessment item", key: "assessmentItem" },
};

function surfaceFor(question: VocabQuizQuestion): QuizQuestionSurface {
  if (question.kind === "assessment") {
    if (question.assessment.questionType === "character_to_pinyin_typing") return "pinyin";
    if (question.assessment.questionType === "context_cloze_mcq") return "context";
    return "meaning";
  }
  if (question.kind === "pinyin") return "pinyin";
  if (question.kind === "cloze") return "context";
  return "meaning";
}

export function questionPresentation(
  question: VocabQuizQuestion,
  entry?: VocabQuizEntry,
): QuestionPresentation {
  const surface = surfaceFor(question);
  const assessment = question.kind === "assessment" ? question.assessment : undefined;
  const pinyin = assessment?.pinyin || entry?.pinyin || toPinyin(question.word);
  const audioUrl = assessment?.audioUrl || entry?.audioUrl;

  if (question.kind === "assessment") {
    const label = QUESTION_TYPE_LABELS[question.assessment.questionType] ?? QUESTION_KIND_LABELS.assessment;
    return {
      surface,
      label: label.label,
      labelKey: label.key,
      prompt: question.prompt,
      pinyin: surface === "pinyin" ? undefined : pinyin || undefined,
      audioUrl,
      explanation: question.explanation || undefined,
    };
  }

  const prompt = question.kind === "cloze" ? question.sentenceWithBlank : "";
  const promptKey = question.kind === "cloze"
    ? "chooseWordCompletesSentence"
    : question.kind === "reverse"
      ? "chooseChineseWord"
      : question.kind === "pinyin"
        ? "typePinyinReading"
        : question.kind === "pos"
          ? "chooseWordClass"
          : question.kind === "synonym"
            ? "chooseRelatedMeaning"
            : question.kind === "listening"
              ? "listenChooseWord"
              : "chooseEnglishMeaning";

  const label = QUESTION_KIND_LABELS[question.kind];
  return {
    surface,
    label: label.label,
    labelKey: label.key,
    prompt,
    promptKey,
    promptData: question.kind === "reverse" ? question.translation : undefined,
    pinyin: surface === "pinyin" ? undefined : pinyin || undefined,
    audioUrl,
  };
}

export function isFreeTextQuestion(question: VocabQuizQuestion): boolean {
  return question.kind === "pinyin"
    || (question.kind === "assessment" && question.assessment.answerFormat === "free_text");
}

export function resultForQuestion(
  results: VocabQuizQuestionResult[],
  index: number,
  word: string,
): VocabQuizQuestionResult | undefined {
  return results.find((result) => result.questionIndex === index)
    ?? results.find((result) => result.word === word);
}

export function extractClozeSentence(
  prompt: string,
  fallbackSentence?: string,
): ClozeSentenceParts {
  const raw = (fallbackSentence || prompt).trim();
  const markerIndex = raw.search(/CLOZE_BLANK|_{3,}|＿{2,}/u);
  const prefix = markerIndex >= 0 ? raw.slice(0, markerIndex) : raw;
  const colonIndex = markerIndex >= 0 ? prefix.lastIndexOf(":") : -1;
  const source = (colonIndex >= 0 ? raw.slice(colonIndex + 1) : raw)
    .replace(/^.*?(?:sentence|句子)\s*:\s*/i, "")
    .trim();
  const match = source.match(/^(.*?)(CLOZE_BLANK|_{3,}|＿{2,})(.*)$/u);
  if (!match) return { before: source, after: "", hasBlank: false };
  return { before: match[1], after: match[3], hasBlank: true };
}

function isHanCharacter(value: string): boolean {
  return /[\u3400-\u9fff]/u.test(value);
}

/**
 * Render-friendly pinyin segments. The backend cache is authoritative; when
 * a sentence is not fully available, returning plain text is safer than
 * inventing ruby readings in the learner UI.
 */
export function sentenceSegments(text: string): Array<{ text: string; pinyin?: string[] }> {
  return text.split(/([\u3400-\u9fff]+)/u).filter(Boolean).map((segment) => {
    if (!isHanCharacter(segment)) return { text: segment };
    const syllables = toPinyinSyllables(segment);
    return syllables.length === Array.from(segment).length
      ? { text: segment, pinyin: syllables }
      : { text: segment };
  });
}

export interface ToneMarkEdit {
  value: string;
  cursor: number;
}

const TONE_MARKS: Record<string, string[]> = {
  a: ["ā", "á", "ǎ", "à"],
  e: ["ē", "é", "ě", "è"],
  i: ["ī", "í", "ǐ", "ì"],
  o: ["ō", "ó", "ǒ", "ò"],
  u: ["ū", "ú", "ǔ", "ù"],
  "ü": ["ǖ", "ǘ", "ǚ", "ǜ"],
};

const TONE_MARK_TO_BASE = new Map(
  Object.entries(TONE_MARKS).flatMap(([base, marks]) => marks.map((mark) => [mark, base] as const)),
);

function normalizePinyinVowel(character: string): string {
  const lower = character.toLowerCase();
  return lower === "v" ? "ü" : lower;
}

function isPinyinVowel(character: string): boolean {
  return /[aeiouüvAEIOUÜVāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]/u.test(character);
}

function isPinyinCharacter(character: string): boolean {
  return /[a-zA-ZüÜ1-5āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]/u.test(character);
}

function toneBearingIndex(syllable: string): number {
  const normalized = Array.from(syllable)
    .filter((character) => !/[1-5]/u.test(character))
    .map((character) => TONE_MARK_TO_BASE.get(character) ?? normalizePinyinVowel(character));
  const aOrE = normalized.findIndex((character) => character === "a" || character === "e");
  if (aOrE >= 0) return aOrE;
  const ou = normalized.findIndex((character, index) => character === "o" && normalized[index + 1] === "u");
  if (ou >= 0) return ou;
  for (let index = normalized.length - 1; index >= 0; index -= 1) {
    if (isPinyinVowel(normalized[index])) return index;
  }
  return -1;
}

export function applyToneMark(
  value: string,
  tone: 1 | 2 | 3 | 4,
  selectionStart = value.length,
  selectionEnd = selectionStart,
): ToneMarkEdit {
  const characters = Array.from(value);
  let start = Math.max(0, Math.min(selectionStart, characters.length));
  let end = Math.max(start, Math.min(selectionEnd, characters.length));
  while (start > 0 && isPinyinVowel(characters[start - 1])) start -= 1;
  while (end < characters.length && isPinyinVowel(characters[end])) end += 1;
  while (start > 0 && isPinyinCharacter(characters[start - 1])) start -= 1;
  while (end < characters.length && isPinyinCharacter(characters[end])) end += 1;

  const syllable = characters.slice(start, end).join("");
  const vowelIndex = toneBearingIndex(syllable);
  if (vowelIndex < 0) {
    const mark = TONE_MARKS.a[tone - 1];
    const next = [...characters.slice(0, selectionStart), mark, ...characters.slice(selectionEnd)].join("");
    return { value: next, cursor: selectionStart + 1 };
  }

  const syllableCharacters = Array.from(syllable).filter((character) => !/[1-5]/u.test(character));
  const originalVowel = syllableCharacters[vowelIndex];
  const base = TONE_MARK_TO_BASE.get(originalVowel) ?? normalizePinyinVowel(originalVowel);
  const replacement = TONE_MARKS[base]?.[tone - 1] ?? originalVowel;
  const editedSyllable = syllableCharacters.map((character, index) => index === vowelIndex ? replacement : character).join("");
  const next = [...characters.slice(0, start), editedSyllable, ...characters.slice(end)].join("");
  return { value: next, cursor: start + vowelIndex + 1 };
}

// ── Hints for the one retry after a wrong diagnostic answer ────────────────
// A hint points the learner in the right direction without revealing the
// answer: Know It gets the word in a lesson sentence (or its word class) —
// its pinyin is already on screen; Say It gets the English meaning plus which
// syllable is off (tone / initial / final); Use It gets the pinyin of the
// missing word (the options already show English glosses).

export type SyllableIssue = "tone" | "initial" | "final";

export interface QuestionHint {
  /** Lesson sentence containing the word (Know It). */
  example?: string;
  /** Word class, when no lesson sentence is available (Know It). */
  wordClass?: string;
  /** English meaning (Say It). */
  meaning?: string;
  /** Pinyin of the missing word (Use It). */
  pinyin?: string;
  /** Per-syllable diagnosis of a typed reading (Say It), 1-based. */
  syllableIssues?: Array<{ syllable: number; issue: SyllableIssue }>;
  /** The typed reading has a different number of syllables. */
  syllableCountWrong?: boolean;
}

const MARKED_VOWELS: Record<string, [string, number]> = Object.fromEntries(
  Object.entries(TONE_MARKS).flatMap(([base, marks]) => marks.map((mark, index) => [mark, [base, index + 1] as [string, number]])),
);

const INITIALS = ["zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "j", "q", "x", "r", "z", "c", "s", "y", "w"];

interface ParsedSyllable { base: string; tone: number }

/** "nǐ hǎo" / "ni3 hao3" → [{base:"ni",tone:3},{base:"hao",tone:3}]; tone 5 = none. */
function parseSyllable(raw: string): ParsedSyllable {
  const marked = numericToToneMarked(raw.normalize("NFC").toLowerCase());
  let tone = 5;
  let base = "";
  for (const character of Array.from(marked)) {
    const mark = MARKED_VOWELS[character];
    if (mark) {
      base += mark[0];
      tone = mark[1];
    } else if (/[a-zü]/u.test(character)) {
      base += character;
    } else if (character === "v") {
      base += "ü";
    }
  }
  return { base: base.replace(/v/g, "ü"), tone };
}

function splitReading(reading: string): string[] {
  return reading.normalize("NFC").trim().split(/[\s'’·-]+/u).filter(Boolean);
}

function initialOf(base: string): string {
  return INITIALS.find((initial) => base.startsWith(initial)) ?? "";
}

/** Which syllables of a typed reading are off, without revealing the answer.
 * Unspaced input ("ni3hao3") is aligned by the expected syllables' spelling. */
export function diagnosePinyin(typed: string, expected: string): Pick<QuestionHint, "syllableIssues" | "syllableCountWrong"> {
  const want = splitReading(expected).map(parseSyllable);
  let got = splitReading(typed).map(parseSyllable);
  if (want.length === 0) return {};
  if (got.length !== want.length) {
    // Re-split a run-together reading using the expected syllable spellings;
    // numeric tones are attached per syllable ("ni3hao3") so split on them.
    const numericSplit = typed.normalize("NFC").toLowerCase().match(/[a-züv]+[1-5]?/giu) ?? [];
    const candidate = numericSplit.length === want.length ? numericSplit.map(parseSyllable) : null;
    if (candidate) {
      got = candidate;
    } else {
      const joined = got.map((syllable) => syllable.base).join("");
      const wantJoined = want.map((syllable) => syllable.base).join("");
      if (joined !== wantJoined) return { syllableCountWrong: true };
      // Same letters, different spacing: tones cannot be located reliably.
      return { syllableIssues: [] };
    }
  }
  const issues: NonNullable<QuestionHint["syllableIssues"]> = [];
  want.forEach((expectedSyllable, index) => {
    const typedSyllable = got[index];
    if (typedSyllable.base !== expectedSyllable.base) {
      const issue: SyllableIssue = initialOf(typedSyllable.base) !== initialOf(expectedSyllable.base) ? "initial" : "final";
      issues.push({ syllable: index + 1, issue });
    } else if (typedSyllable.tone !== expectedSyllable.tone) {
      issues.push({ syllable: index + 1, issue: "tone" });
    }
  });
  return { syllableIssues: issues };
}

function lessonSentenceFor(word: string, entry?: VocabQuizEntry): string | undefined {
  return entry?.lessonSentences?.map((sentence) => sentence.trim()).find((sentence) => sentence && sentence.includes(word));
}

export function questionHint(question: VocabQuizQuestion, entry: VocabQuizEntry | undefined, attemptedAnswer: string): QuestionHint {
  const surface = surfaceFor(question);
  const assessment = question.kind === "assessment" ? question.assessment : undefined;
  if (surface === "meaning") {
    const example = lessonSentenceFor(question.word, entry);
    if (example) return { example };
    const wordClass = assessment?.pos || entry?.pos;
    return wordClass ? { wordClass } : {};
  }
  if (surface === "pinyin") {
    const meaning = assessment?.simpleEnglishMeaning || entry?.translation || undefined;
    const expected = question.kind === "assessment" ? question.correctAnswer : question.kind === "pinyin" ? question.correctPinyin : "";
    return { meaning, ...diagnosePinyin(attemptedAnswer, expected) };
  }
  const pinyin = assessment?.pinyin || entry?.pinyin || toPinyin(question.word) || undefined;
  return pinyin ? { pinyin } : {};
}
