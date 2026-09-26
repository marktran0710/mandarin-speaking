import type {
  VocabQuizEntry,
  VocabQuizQuestion,
  VocabQuizQuestionResult,
} from "@entities/vocabulary";
import { toPinyin, toPinyinSyllables } from "@entities/vocabulary";

export type QuizQuestionSurface = "meaning" | "pinyin" | "context";

export interface ClozeSentenceParts {
  before: string;
  after: string;
  hasBlank: boolean;
}

export interface QuestionPresentation {
  surface: QuizQuestionSurface;
  label: string;
  prompt: string;
  pinyin?: string;
  audioUrl?: string;
  explanation?: string;
}

const QUESTION_TYPE_LABELS: Record<string, string> = {
  basic_meaning_mcq: "Meaning check",
  character_to_pinyin_typing: "Reading recall",
  context_cloze_mcq: "Sentence completion",
  productive_recall: "Active recall",
  contextual_productive_recall: "Context recall",
};

const QUESTION_KIND_LABELS: Record<VocabQuizQuestion["kind"], string> = {
  translation: "Meaning check",
  cloze: "Sentence completion",
  pinyin: "Reading recall",
  pos: "Word class",
  synonym: "Related meaning",
  reverse: "Character recall",
  listening: "Listening check",
  assessment: "Assessment item",
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
    return {
      surface,
      label: QUESTION_TYPE_LABELS[question.assessment.questionType] ?? "Assessment item",
      prompt: question.prompt,
      pinyin: surface === "pinyin" ? undefined : pinyin || undefined,
      audioUrl,
      explanation: question.explanation || undefined,
    };
  }

  const prompt = question.kind === "cloze"
    ? question.sentenceWithBlank
    : question.kind === "reverse"
      ? `Choose the Chinese word for ${question.translation}.`
      : question.kind === "pinyin"
        ? "Type the pinyin reading for this word."
        : question.kind === "pos"
          ? "Choose the word class that best describes this word."
          : question.kind === "synonym"
            ? "Choose the closest related meaning."
            : question.kind === "listening"
              ? "Listen to the model and choose the matching word."
              : "Choose the English meaning of this word.";

  return {
    surface,
    label: QUESTION_KIND_LABELS[question.kind],
    prompt,
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
