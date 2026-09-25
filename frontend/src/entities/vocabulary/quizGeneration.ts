import { toPinyin } from "./api";
import { DIAGNOSTIC_ROUNDS, type TierMode } from "./progression";
import type { VocabAssessmentLevel, VocabAssessmentQuestion, VocabQuizEntry } from "./types";
import type { VocabQuizAssessmentQuestion } from "./quizTypes";
import { CLOZE_BLANK, quizConceptId } from "./quizTypes";
type StudentIconName = "star" | "stories";

export const MAX_QUESTIONS = 8;
export const TIMER_TICK_MS = 100;
export const OPTION_COUNT = 4;
export const FILLER_DISTRACTORS = [
  "friend", "house", "water", "book", "school",
  "happy", "morning", "money", "food", "family",
  "teacher", "street", "weather", "car", "phone",
];
// Last-resort Round 3 (cloze MCQ) distractors when a lesson is too small to
// supply enough of its own word forms — generic A1 nouns unlikely to collide
// with real lesson vocabulary.
const FILLER_CLOZE_WORDS = [
  "蘋果", "電腦", "老師", "朋友", "杯子",
  "椅子", "鉛筆", "眼鏡", "雨傘", "公車",
];

export const TIER_CARDS: Array<{
  mode: TierMode;
  title: string;
  titlePinyin: string;
  titleEn: string;
  iconName: StudentIconName;
  desc: string;
  descPinyin: string;
  descEn: string;
}> = [
  { mode: "tier1", title: "第一關", titlePinyin: "Dì yī guān", titleEn: "Round 1", iconName: "star", desc: "每個生詞一題。", descPinyin: "Měi gè shēngcí yì tí.", descEn: "One question for each lesson word." },
  { mode: "tier2", title: "第二關", titlePinyin: "Dì èr guān", titleEn: "Round 2", iconName: "star", desc: "每個生詞一題，寫出拼音。", descPinyin: "Měi gè shēngcí yì tí, xiě chū pīnyīn.", descEn: "One question for each word — type the pinyin." },
  { mode: "tier3", title: "情境辨識", titlePinyin: "Qíngjìng biànshí", titleEn: "Context", iconName: "star", desc: "每個生詞一題，在情境中辨識。", descPinyin: "Měi gè shēngcí yì tí, zài qíngjìng zhōng biànshí.", descEn: "One multiple-choice question for each word in context." },
];

export const REVIEW_CARD = {
  iconName: "stories" as StudentIconName,
  title: "生詞表",
  titlePinyin: "Shēngcí biǎo",
  titleEn: "Word list",
  desc: "只是看 — 這一課所有生詞和它們的聲調，不用答題。",
  descPinyin: "Zhǐshì kàn — zhè yí kè suǒyǒu shēngcí hàn tāmen de shēngdiào, búyòng dá tí.",
  descEn: "Just looking — every word in this lesson and its tones, no questions.",
};

export function shuffle<T>(items: T[]): T[] {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}
export function buildAssessmentQuestions(
  entries: VocabQuizEntry[],
  level?: VocabAssessmentLevel,
): VocabQuizAssessmentQuestion[] {
  const levels = level ? [level] : (["easy", "medium", "hard"] as const);
  return levels.flatMap((assessmentLevel) => shuffle(
    entries.flatMap((entry) => (entry.assessmentQuestions ?? [])
      .filter((assessment) => assessment.level === assessmentLevel)
      .map((assessment) => ({
        kind: "assessment" as const,
        word: assessment.targetWord,
        prompt: assessment.prompt,
        options: shuffle([...assessment.options]),
        correctAnswer: assessment.correctAnswer,
        acceptedAnswers: assessment.acceptedAnswers,
        explanation: assessment.explanation,
        assessment,
        isAiGenerated: false as const,
      })),
    ),
  ));
}

const ASSESSMENT_LEVEL_BY_DIAGNOSTIC_KIND: Partial<Record<string, VocabAssessmentLevel>> = {
  basic_meaning_mcq: "easy",
  character_to_pinyin_typing: "medium",
  context_cloze_mcq: "hard",
  productive_recall: "hard",
  contextual_productive_recall: "hard",
};

/** Build one published item per Bottom-K word without losing server order. */
export function buildPersonalizedAssessmentQuestions(
  entries: VocabQuizEntry[],
): VocabQuizAssessmentQuestion[] {
  return entries.flatMap((entry) => {
    const bank = entry.assessmentQuestions ?? [];
    if (!bank.length) return [];
    const failedLevels = new Set(
      (entry.bktFailedQuestionKinds ?? [])
        .map((kind) => ASSESSMENT_LEVEL_BY_DIAGNOSTIC_KIND[kind])
        .filter((level): level is VocabAssessmentLevel => Boolean(level)),
    );
    const seenLevels = new Set(
      (entry.bktSeenQuestionKinds ?? [])
        .map((kind) => ASSESSMENT_LEVEL_BY_DIAGNOSTIC_KIND[kind])
        .filter((level): level is VocabAssessmentLevel => Boolean(level)),
    );
    const assessment = bank.find((candidate) => failedLevels.has(candidate.level))
      ?? bank.find((candidate) => !seenLevels.has(candidate.level))
      ?? bank[0];
    return [{
      kind: "assessment" as const,
      word: assessment.targetWord,
      prompt: assessment.prompt,
      options: shuffle([...assessment.options]),
      correctAnswer: assessment.correctAnswer,
      acceptedAnswers: assessment.acceptedAnswers,
      explanation: assessment.explanation,
      assessment,
      isAiGenerated: false as const,
    }];
  });
}

/** Scheduled maintenance uses the published bank without corrective targeting. */
export function buildMaintenanceAssessmentQuestions(
  entries: VocabQuizEntry[],
): VocabQuizAssessmentQuestion[] {
  return entries.flatMap((entry) => {
    const bank = [...(entry.assessmentQuestions ?? [])].sort((left, right) => {
      const dimensionOrder = (question: VocabAssessmentQuestion): number => (
        question.questionType === "basic_meaning_mcq"
          ? 0
          : question.questionType === "character_to_pinyin_typing"
            ? 1
            : 2
      );
      return dimensionOrder(left) - dimensionOrder(right) || left.questionId.localeCompare(right.questionId);
    });
    if (!bank.length) return [];
    const seen = new Set(entry.bktSeenQuestionKinds ?? []);
    const unseen = bank.filter((question) => !seen.has(question.questionType));
    // Finish covering every diagnostic dimension before rotating through the
    // already-seen bank. Observation count is only a tie-breaker after the
    // server evidence confirms that all dimensions have appeared.
    const candidates = unseen.length ? unseen : bank;
    const rotation = unseen.length
      ? 0
      : Math.max(0, entry.bktObservationCount ?? 0) % candidates.length;
    const assessment = candidates[rotation];
    if (!assessment) return [];
    return [{
      kind: "assessment" as const,
      word: assessment.targetWord,
      prompt: assessment.prompt,
      options: shuffle([...assessment.options]),
      correctAnswer: assessment.correctAnswer,
      acceptedAnswers: assessment.acceptedAnswers,
      explanation: assessment.explanation,
      assessment,
      isAiGenerated: false as const,
    }];
  });
}

function seededShuffle<T>(items: T[], seed: string): T[] {
  const result = [...items];
  let state = Array.from(seed).reduce((hash, character) => ((hash * 31) + character.charCodeAt(0)) >>> 0, 2166136261);
  for (let index = result.length - 1; index > 0; index -= 1) {
    state = (state * 1664525 + 1013904223) >>> 0;
    const swapIndex = state % (index + 1);
    [result[index], result[swapIndex]] = [result[swapIndex], result[index]];
  }
  return result;
}

function diagnosticQuestionId(entry: VocabQuizEntry, mode: TierMode): string {
  return `${entry.wordId ?? quizConceptId(entry.word)}:${DIAGNOSTIC_ROUNDS[mode].roundType}:v1`;
}

function vocabularyForms(word: string): string[] {
  return Array.from(new Set(
    word.split(/[／/]/u).map((form) => form.trim()).filter(Boolean),
  )).sort((left, right) => right.length - left.length);
}

/**
 * A source sentence is usable only when it contains one unambiguous spelling
 * of the target. This keeps Round 3 tied to the lesson text without guessing
 * which occurrence a learner is meant to recall.
 */
function lessonCloze(entry: VocabQuizEntry): { prompt: string; answer: string } | null {
  const forms = vocabularyForms(entry.word);
  for (const sentence of entry.lessonSentences ?? []) {
    const source = sentence.trim();
    for (const form of forms) {
      if (source.split(form).length !== 2) continue;
      return {
        prompt: `Complete the sentence: ${source.replace(form, CLOZE_BLANK)}`,
        answer: form,
      };
    }
  }
  return null;
}

/** Build exactly one round-specific question for every unique lesson word. */
export function buildDiagnosticRoundQuestions(entries: VocabQuizEntry[], mode: TierMode): VocabAssessmentQuestion[] {
  const config = DIAGNOSTIC_ROUNDS[mode];
  const uniqueEntries = Array.from(new Map(entries.map((entry) => [entry.wordId ?? quizConceptId(entry.word), entry])).values());
  const translationPool = uniqueEntries.map((entry) => entry.translation).filter(Boolean);
  const clozeWordPool = uniqueEntries.map((entry) => vocabularyForms(entry.word)[0]).filter(Boolean);
  const questions = uniqueEntries.map((entry) => {
    const source = entry.assessmentQuestions?.find((assessment) => assessment.level === config.bankLevel);
    const wordId = entry.wordId ?? quizConceptId(entry.word);
    if (mode === "tier1") {
      const correctAnswer = source?.correctAnswer || entry.translation;
      const sourceOptions = source?.options?.length === OPTION_COUNT
        ? source.options
        : [correctAnswer, ...translationPool.filter((value) => value !== correctAnswer)];
      const options = Array.from(new Set([...sourceOptions, ...FILLER_DISTRACTORS])).slice(0, OPTION_COUNT);
      while (options.length < OPTION_COUNT) options.push(`meaning ${options.length + 1}`);
      return {
        questionId: diagnosticQuestionId(entry, mode), wordId, targetWord: entry.word, pinyin: entry.pinyin || toPinyin(entry.word),
        pos: entry.pos || "", simpleEnglishMeaning: entry.translation, level: config.bankLevel, difficultyWeight: 1 as const,
        questionType: config.questionKind, answerFormat: "single_choice" as const, prompt: source?.prompt || `What does ${entry.word} mean?`,
        options: seededShuffle(options, `${wordId}:know_it:options`), correctAnswer,
        acceptedAnswers: source?.acceptedAnswers?.length ? source.acceptedAnswers : [correctAnswer],
        explanation: source?.explanation || `${entry.word} means ${entry.translation}.`,
        ...(source?.audioUrl || entry.audioUrl ? { audioUrl: source?.audioUrl || entry.audioUrl } : {}),
      };
    }
    if (mode === "tier2") {
      // Published lesson data normally carries pinyin (the CSV assessment
      // bank does). Keep the round build total even when an older local story
      // snapshot omitted it; the word itself is a temporary answer sentinel
      // and will be replaced as soon as the canonical pinyin cache is warm.
      const pinyin = entry.pinyin || source?.pinyin || toPinyin(entry.word) || entry.word;
      const acceptedAnswers = Array.from(new Set([
        pinyin,
        ...pinyin.split("/").map((value) => value.trim()).filter(Boolean),
        ...(source?.acceptedAnswers ?? []),
      ]));
      return {
        questionId: diagnosticQuestionId(entry, mode), wordId, targetWord: entry.word, pinyin,
        pos: entry.pos || source?.pos || "", simpleEnglishMeaning: entry.translation, level: config.bankLevel, difficultyWeight: 2 as const,
        questionType: config.questionKind, answerFormat: "free_text" as const, prompt: `Type the pinyin for ${entry.word}.`, options: [],
        correctAnswer: pinyin, acceptedAnswers, explanation: `The pinyin for ${entry.word} is ${pinyin}.`,
        ...(source?.audioUrl || entry.audioUrl ? { audioUrl: source?.audioUrl || entry.audioUrl } : {}),
      };
    }
    // Round 3 ("use it") is a multiple-choice context cloze, not free-text
    // hanzi typing — most students have no Chinese IME. The current workbook
    // stores that complete MCQ on the hard-level row, so use it as-is. Older
    // banks stored a productive-recall hard row and kept the approved cloze
    // options on the medium-level row; retain that fallback for those banks.
    const hardClozeSource = source?.questionType === "context_cloze_mcq" && source.answerFormat === "single_choice"
      ? source
      : undefined;
    const mcqSource = hardClozeSource ?? entry.assessmentQuestions?.find(
      (assessment) => assessment.level === "medium" && assessment.questionType === "context_cloze_mcq",
    );
    const sourceCloze = hardClozeSource ? null : lessonCloze(entry);
    const correctAnswer = hardClozeSource?.correctAnswer || sourceCloze?.answer || source?.correctAnswer || vocabularyForms(entry.word)[0] || entry.word;
    const acceptedAnswers = Array.from(new Set([
      correctAnswer,
      ...(source?.acceptedAnswers || []),
      ...vocabularyForms(entry.word),
    ]));
    const otherWordForms = clozeWordPool.filter((word) => word !== correctAnswer);
    const sourceOptions = mcqSource?.options?.length === OPTION_COUNT && mcqSource.correctAnswer === correctAnswer
      ? mcqSource.options
      : [correctAnswer, ...(mcqSource?.options ?? []).filter((option) => option !== mcqSource?.correctAnswer), ...otherWordForms];
    const options = Array.from(new Set([...sourceOptions, ...FILLER_CLOZE_WORDS])).slice(0, OPTION_COUNT);
    while (options.length < OPTION_COUNT) options.push(`詞${options.length + 1}`);
    return {
      questionId: diagnosticQuestionId(entry, mode), wordId, targetWord: entry.word, pinyin: entry.pinyin || toPinyin(entry.word),
      pos: entry.pos || source?.pos || "", simpleEnglishMeaning: entry.translation, level: config.bankLevel, difficultyWeight: 3 as const,
      questionType: config.questionKind, answerFormat: "single_choice" as const, prompt: hardClozeSource?.prompt || sourceCloze?.prompt || source?.prompt || `Use the Chinese word for “${entry.translation}” in the sentence.`,
      options: seededShuffle(options, `${wordId}:use_it:options`), correctAnswer, acceptedAnswers,
      explanation: source?.explanation || `Use ${correctAnswer} in this context.`,
      ...(source?.audioUrl || entry.audioUrl ? { audioUrl: source?.audioUrl || entry.audioUrl } : {}),
    };
  });
  return seededShuffle(questions, `${config.roundType}:question-order`);
}
