import { toPinyin } from "../../utils/pinyin";
import type { StudentIconName } from "../StudentIcon";
import { toneTrapVariants } from "../../utils/toneTraps";
import { tierConfigFromMode, type TierMode } from "../../utils/quizTiers";
import {
  normalizeQuizExposure,
  type QuizQuestionBuildContext,
  type QuizQuestionKind,
} from "../../utils/quizSessionPlanner";

export interface VocabQuizClozeCandidate {
  sentence: string;
  distractors: string[];
}

export interface VocabQuizSynonymCandidate {
  synonym: string;
  distractors: string[];
}

export interface VocabQuizEntry {
  word: string;
  translation: string;
  /** Stable identity and teacher-authored observations imported from a CSV bank. */
  wordId?: string;
  assessmentQuestions?: VocabAssessmentQuestion[];
  /** The student-serving snapshot is explicitly approved; live material is
   * draft and must not become research evidence. */
  bktValidationStatus?: "APPROVED" | "DRAFT";
  /** Question types a teacher has removed for this word in Quiz Review. */
  disabledQuestionKinds?: ReadonlyArray<"pinyin" | "reverse">;
  /** Question kinds already used for this learner; weak-word review prefers
   * another validated form when one is available. */
  bktSeenQuestionKinds?: ReadonlyArray<QuizQuestionKind>;
  pinyin?: string;
  pos?: string;
  aiDistractors?: string[];
  aiCloze?: VocabQuizClozeCandidate[];
  aiSynonym?: VocabQuizSynonymCandidate[];
}

export type VocabAssessmentLevel = "easy" | "medium" | "hard";

export interface VocabAssessmentQuestion {
  questionId: string;
  wordId: string;
  targetWord: string;
  pinyin: string;
  pos: string;
  simpleEnglishMeaning: string;
  level: VocabAssessmentLevel;
  difficultyWeight: 1 | 2 | 3;
  questionType: "basic_meaning_mcq" | "context_cloze_mcq" | "productive_recall";
  answerFormat: "single_choice" | "free_text";
  prompt: string;
  options: string[];
  correctAnswer: string;
  acceptedAnswers: string[];
  explanation: string;
}

// The blank marker inside a cloze question's sentence — split out at render
// time so it can be styled distinctly from the surrounding text.
export const CLOZE_BLANK = "____";

export interface VocabQuizTranslationQuestion {
  kind: "translation";
  word: string;
  correctTranslation: string;
  options: string[];
  isAiGenerated: boolean;
}

export interface VocabQuizClozeQuestion {
  kind: "cloze";
  word: string;
  sentenceWithBlank: string;
  correctWord: string;
  options: string[];
  isAiGenerated: true;
}

export interface VocabQuizPinyinQuestion {
  kind: "pinyin";
  word: string;
  correctPinyin: string;
  options: string[];
  isAiGenerated: false;
}

export interface VocabQuizPosQuestion {
  kind: "pos";
  word: string;
  correctPos: string;
  options: string[];
  isAiGenerated: false;
}

export interface VocabQuizSynonymQuestion {
  kind: "synonym";
  word: string;
  correctSynonym: string;
  options: string[];
  isAiGenerated: true;
}

export interface VocabQuizReverseQuestion {
  kind: "reverse";
  word: string;
  translation: string;
  correctWord: string;
  options: string[];
  isAiGenerated: boolean;
}

export interface VocabQuizListeningQuestion {
  kind: "listening";
  word: string;
  correctWord: string;
  options: string[];
  isAiGenerated: boolean;
}

export interface VocabQuizAssessmentQuestion {
  kind: "assessment";
  word: string;
  prompt: string;
  options: string[];
  correctAnswer: string;
  acceptedAnswers: string[];
  explanation: string;
  assessment: VocabAssessmentQuestion;
  isAiGenerated: false;
}

export type VocabQuizQuestion =
  | VocabQuizTranslationQuestion
  | VocabQuizClozeQuestion
  | VocabQuizPinyinQuestion
  | VocabQuizPosQuestion
  | VocabQuizSynonymQuestion
  | VocabQuizReverseQuestion
  | VocabQuizListeningQuestion
  | VocabQuizAssessmentQuestion;

export interface VocabQuizQuestionResult {
  word: string;
  correct: boolean;
  timeMs: number;
  /** Stable identity fields are optional so old attempts remain readable. */
  itemId?: string;
  conceptId?: string;
  questionKind?: QuizQuestionKind | VocabAssessmentQuestion["questionType"];
  level?: "easy" | "medium" | "hard";
  baseStoryId?: string;
  itemVersion?: string;
  isBktEligible?: boolean;
  bktEligibilityErrors?: string[];
  diagnosticExposureId?: string;
  assistedResponse?: boolean;
  bktValidationStatus?: "APPROVED" | "DRAFT";
  selectedAnswer?: string;
  correctAnswer?: string;
  presentedOptions?: string[];
  questionPrompt?: string;
  answeredAt?: string;
  questionIndex?: number;
  lessonId?: string;
  quizId?: string;
}

/** Normalized concept identity shared by all question types and story levels. */
export function quizConceptId(word: string): string {
  return word.normalize("NFKC").trim().replace(/\s+/g, " ");
}

/** Stable across option shuffles and question rerenders. */
export function quizItemId(
  baseStoryId: string,
  word: string,
  questionKind: QuizQuestionKind,
  itemVersion = "v1",
): string {
  return [baseStoryId, quizConceptId(word), questionKind, itemVersion]
    .map((part) => encodeURIComponent(part))
    .join(":");
}

export type VocabQuizMode = TierMode | "free" | "weak_words";

export interface VocabQuizSummary {
  mode: VocabQuizMode;
  totalQuestions: number;
  correctCount: number;
  totalTimeMs: number;
  questionResults: VocabQuizQuestionResult[];
}

export const MAX_QUESTIONS = 8;
export const TIMER_TICK_MS = 100;
const OPTION_COUNT = 4;
const FILLER_DISTRACTORS = [
  "friend", "house", "water", "book", "school",
  "happy", "morning", "money", "food", "family",
  "teacher", "street", "weather", "car", "phone",
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
  { mode: "tier1", title: "第一關", titlePinyin: "Dì yī guān", titleEn: "Tier 1", iconName: "star", desc: "20 題 — 答對 14 題就過關。", descPinyin: "20 tí — dá duì 14 tí jiù guòguān.", descEn: "20 questions — 14 right to pass." },
  { mode: "tier2", title: "第二關", titlePinyin: "Dì èr guān", titleEn: "Tier 2", iconName: "star", desc: "22 題，選項更難 — 答對 18 題就能開始說話練習。", descPinyin: "22 tí, xuǎnxiàng gèng nán — dá duì 18 tí jiù néng kāishǐ shuōhuà liànxí.", descEn: "22 questions, trickier options — 18 right opens speaking practice." },
  { mode: "tier3", title: "第三關", titlePinyin: "Dì sān guān", titleEn: "Tier 3", iconName: "star", desc: "25 題，150 秒 — 答對 22 題。", descPinyin: "25 tí, 150 miǎo — dá duì 22 tí.", descEn: "25 questions in 150s — 22 right to pass." },
];

export const REVIEW_CARD = {
  iconName: "stories" as StudentIconName,
  title: "複習模式",
  titlePinyin: "Fùxí móshì",
  titleEn: "Review",
  desc: "沒有題目限制 — 直接看所有生詞和它們的聲調。",
  descPinyin: "Méiyǒu tímù xiànzhì — zhíjiē kàn suǒyǒu shēngcí hàn tāmen de shēngdiào.",
  descEn: "No question limit — just browse every word and its tones.",
};

export function shuffle<T>(items: T[]): T[] {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

export function normalizeQuizAnswer(text: string): string {
  return text.normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/[\s\p{P}\p{S}_]+/gu, "");
}

export function assessmentAnswerIsCorrect(question: VocabQuizAssessmentQuestion, submittedAnswer: string): boolean {
  const accepted = question.acceptedAnswers.length > 0 ? question.acceptedAnswers : [question.correctAnswer];
  return accepted.some((answer) => normalizeQuizAnswer(answer) === normalizeQuizAnswer(submittedAnswer));
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

function normalizeReading(entry: VocabQuizEntry): string {
  return (entry.pinyin || toPinyin(entry.word)).trim().toLowerCase().replace(/\s+/g, " ");
}

function isForbiddenFutureAnswer(value: string, forbiddenAnswers: ReadonlySet<string>): boolean {
  return forbiddenAnswers.has(normalizeQuizExposure(value));
}

export function collectQuizEntries(
  words: string[],
  translations: Array<string | undefined>,
  suggestedAnswers?: Array<string | undefined>,
  aiDistractors?: Array<string[] | undefined>,
  pinyins?: Array<string | undefined>,
  aiCloze?: Array<VocabQuizClozeCandidate[] | undefined>,
  partsOfSpeech?: Array<string | undefined>,
  aiSynonym?: Array<VocabQuizSynonymCandidate[] | undefined>,
  disabledQuestionKinds?: Array<ReadonlyArray<"pinyin" | "reverse"> | undefined>,
): VocabQuizEntry[] {
  const seen = new Set<string>();
  const entries: VocabQuizEntry[] = [];
  words.forEach((word, i) => {
    const translation = translations[i]?.trim();
    if (!translation || seen.has(word)) return;
    const context = suggestedAnswers?.[i];
    if (context !== undefined && !context.includes(word)) return;
    seen.add(word);
    const safeDistractors = (values: string[] | undefined, extraForbidden: string[] = []) => {
      const forbidden = new Set([word, ...extraForbidden].map(normalizeQuizAnswer));
      return (values ?? []).filter(
        (value) => typeof value === "string" && value.trim() && !forbidden.has(normalizeQuizAnswer(value)),
      );
    };
    const cloze = (aiCloze?.[i] ?? []).filter((c) => c.sentence.split(word).length === 2)
      .map((c) => ({ ...c, distractors: safeDistractors(c.distractors) }))
      .filter((c) => c.distractors.length > 0)
      .slice(0, 1);
    const synonym = (aiSynonym?.[i] ?? [])
      .filter((c) => normalizeQuizAnswer(c.synonym) !== normalizeQuizAnswer(word))
      .map((c) => ({ ...c, distractors: safeDistractors(c.distractors, [c.synonym]) }))
      .filter((c) => c.distractors.length > 0)
      .slice(0, 1);
    const distractors = safeDistractors(aiDistractors?.[i]);
    const pinyin = pinyins?.[i]?.trim();
    const pos = partsOfSpeech?.[i]?.trim();
    entries.push({
      word,
      translation,
      ...(disabledQuestionKinds?.[i]?.length ? { disabledQuestionKinds: disabledQuestionKinds[i] } : {}),
      ...(distractors.length ? { aiDistractors: distractors } : {}),
      ...(pinyin ? { pinyin } : {}),
      ...(pos ? { pos } : {}),
      ...(cloze.length ? { aiCloze: cloze } : {}),
      ...(synonym.length ? { aiSynonym: synonym } : {}),
    });
  });
  return entries;
}

function buildTranslationQuestion(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
  useAiDistractors = true,
  forbiddenAnswers: ReadonlySet<string> = new Set(),
): VocabQuizTranslationQuestion {
  const usedTranslations = new Set([normalizeQuizAnswer(entry.translation)]);
  const aiDistractors = shuffle(
    useAiDistractors
      ? (entry.aiDistractors ?? []).filter(
          (d) => !usedTranslations.has(normalizeQuizAnswer(d)) && !isForbiddenFutureAnswer(d, forbiddenAnswers),
        )
      : [],
  ).slice(0, OPTION_COUNT - 1);
  aiDistractors.forEach((d) => usedTranslations.add(normalizeQuizAnswer(d)));
  const realDistractors = shuffle(Array.from(new Set(
    allEntries
      .filter((e) => e.word !== entry.word && !usedTranslations.has(normalizeQuizAnswer(e.translation))
        && !isForbiddenFutureAnswer(e.translation, forbiddenAnswers))
      .map((e) => e.translation),
  ))).slice(0, OPTION_COUNT - 1 - aiDistractors.length);
  realDistractors.forEach((d) => usedTranslations.add(normalizeQuizAnswer(d)));
  const fillerDistractors = shuffle(FILLER_DISTRACTORS.filter(
    (word) => !usedTranslations.has(normalizeQuizAnswer(word)) && !isForbiddenFutureAnswer(word, forbiddenAnswers),
  )).slice(0, OPTION_COUNT - 1 - aiDistractors.length - realDistractors.length);
  return {
    kind: "translation",
    word: entry.word,
    correctTranslation: entry.translation,
    options: shuffle([entry.translation, ...aiDistractors, ...realDistractors, ...fillerDistractors]),
    isAiGenerated: aiDistractors.length > 0,
  };
}

function buildClozeQuestion(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
  forbiddenAnswers: ReadonlySet<string> = new Set(),
): VocabQuizClozeQuestion {
  const candidate = entry.aiCloze![0];
  const usedWords = new Set([entry.word]);
  const aiWordDistractors = shuffle(candidate.distractors.filter(
    (d) => !usedWords.has(d) && !isForbiddenFutureAnswer(d, forbiddenAnswers),
  )).slice(0, OPTION_COUNT - 1);
  aiWordDistractors.forEach((d) => usedWords.add(d));
  const realWordDistractors = shuffle(Array.from(new Set(
    allEntries.filter((e) => e.word !== entry.word && !usedWords.has(e.word)
      && !isForbiddenFutureAnswer(e.word, forbiddenAnswers)
      && normalizeQuizAnswer(e.translation) !== normalizeQuizAnswer(entry.translation)).map((e) => e.word),
  ))).slice(0, OPTION_COUNT - 1 - aiWordDistractors.length);
  return {
    kind: "cloze",
    word: entry.word,
    sentenceWithBlank: candidate.sentence.replace(entry.word, CLOZE_BLANK),
    correctWord: entry.word,
    options: shuffle([entry.word, ...aiWordDistractors, ...realWordDistractors]),
    isAiGenerated: true,
  };
}

function buildPinyinQuestion(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
  toneTraps: "primary" | "pad" = "pad",
  forbiddenAnswers: ReadonlySet<string> = new Set(),
): VocabQuizPinyinQuestion {
  const correctPinyin = entry.pinyin || toPinyin(entry.word);
  const usedPinyin = new Set([correctPinyin]);
  const otherWordPool = Array.from(new Set(allEntries.filter((e) => e.word !== entry.word)
    .map((e) => e.pinyin || toPinyin(e.word))
    .filter((p) => p && !usedPinyin.has(p) && !isForbiddenFutureAnswer(p, forbiddenAnswers))));
  const trapPool = toneTrapVariants(correctPinyin)
    .filter((p) => !usedPinyin.has(p) && !isForbiddenFutureAnswer(p, forbiddenAnswers));
  const distractors: string[] = [];
  for (const pool of toneTraps === "primary" ? [trapPool, otherWordPool] : [otherWordPool, trapPool]) {
    for (const candidate of shuffle(pool)) {
      if (distractors.length >= OPTION_COUNT - 1) break;
      if (usedPinyin.has(candidate)) continue;
      usedPinyin.add(candidate);
      distractors.push(candidate);
    }
  }
  return { kind: "pinyin", word: entry.word, correctPinyin, options: shuffle([correctPinyin, ...distractors]), isAiGenerated: false };
}

function buildReverseQuestion(entry: VocabQuizEntry, allEntries: VocabQuizEntry[], forbiddenAnswers: ReadonlySet<string> = new Set()): VocabQuizReverseQuestion {
  const usedWords = new Set([entry.word]);
  const distractors = shuffle(Array.from(new Set(allEntries.filter((e) => !usedWords.has(e.word)
    && e.word !== entry.word && !isForbiddenFutureAnswer(e.word, forbiddenAnswers)
    && normalizeQuizAnswer(e.translation) !== normalizeQuizAnswer(entry.translation)).map((e) => e.word)))).slice(0, OPTION_COUNT - 1);
  return { kind: "reverse", word: entry.word, translation: entry.translation, correctWord: entry.word, options: shuffle([entry.word, ...distractors]), isAiGenerated: false };
}

function buildListeningQuestion(entry: VocabQuizEntry, allEntries: VocabQuizEntry[], forbiddenAnswers: ReadonlySet<string> = new Set()): VocabQuizListeningQuestion {
  const reading = normalizeReading(entry);
  const usedWords = new Set([entry.word]);
  const distractors = shuffle(Array.from(new Set(allEntries.filter((e) => !usedWords.has(e.word)
    && e.word !== entry.word && !isForbiddenFutureAnswer(e.word, forbiddenAnswers)
    && normalizeReading(e) !== reading && normalizeQuizAnswer(e.translation) !== normalizeQuizAnswer(entry.translation))
    .map((e) => e.word)))).slice(0, OPTION_COUNT - 1);
  return { kind: "listening", word: entry.word, correctWord: entry.word, options: shuffle([entry.word, ...distractors]), isAiGenerated: false };
}

const FILLER_POS = ["N", "V", "Adj", "Adv", "MW", "Prep", "Conj", "Pron", "Quant", "Time", "Loc", "Vaux", "Particle", "Phrase"];

function buildPosQuestion(entry: VocabQuizEntry, allEntries: VocabQuizEntry[], forbiddenAnswers: ReadonlySet<string> = new Set()): VocabQuizPosQuestion {
  const correctPos = entry.pos!;
  const usedPos = new Set([correctPos]);
  const realDistractors = shuffle(Array.from(new Set(allEntries.filter((e) => e.word !== entry.word && e.pos
    && !usedPos.has(e.pos) && !isForbiddenFutureAnswer(e.pos, forbiddenAnswers)).map((e) => e.pos!)))).slice(0, OPTION_COUNT - 1);
  realDistractors.forEach((p) => usedPos.add(p));
  const fillerDistractors = shuffle(FILLER_POS.filter(
    (p) => !usedPos.has(p) && !isForbiddenFutureAnswer(p, forbiddenAnswers),
  )).slice(0, OPTION_COUNT - 1 - realDistractors.length);
  return { kind: "pos", word: entry.word, correctPos, options: shuffle([correctPos, ...realDistractors, ...fillerDistractors]), isAiGenerated: false };
}

function buildSynonymQuestion(entry: VocabQuizEntry, allEntries: VocabQuizEntry[], forbiddenAnswers: ReadonlySet<string> = new Set()): VocabQuizSynonymQuestion {
  const candidate = entry.aiSynonym![0];
  const usedWords = new Set([entry.word, candidate.synonym]);
  const aiWordDistractors = shuffle(candidate.distractors.filter(
    (d) => !usedWords.has(d) && !isForbiddenFutureAnswer(d, forbiddenAnswers),
  )).slice(0, OPTION_COUNT - 1);
  aiWordDistractors.forEach((d) => usedWords.add(d));
  const realWordDistractors = shuffle(Array.from(new Set(allEntries.filter((e) => e.word !== entry.word
    && !usedWords.has(e.word) && !isForbiddenFutureAnswer(e.word, forbiddenAnswers)
    && normalizeQuizAnswer(e.translation) !== normalizeQuizAnswer(entry.translation)).map((e) => e.word),
  ))).slice(0, OPTION_COUNT - 1 - aiWordDistractors.length);
  return { kind: "synonym", word: entry.word, correctSynonym: candidate.synonym, options: shuffle([candidate.synonym, ...aiWordDistractors, ...realWordDistractors]), isAiGenerated: true };
}

type KindWeights = Array<[QuizQuestionKind, number]>;
const LEGACY_KIND_WEIGHTS: KindWeights = [["translation", 50], ["pinyin", 20], ["cloze", 15], ["pos", 5], ["synonym", 10]];
const TIER_KIND_WEIGHTS: Record<TierMode, KindWeights> = {
  tier1: [["translation", 50], ["pinyin", 20], ["reverse", 30]],
  tier2: [["translation", 25], ["pinyin", 15], ["reverse", 15], ["cloze", 15], ["synonym", 10], ["listening", 20]],
  tier3: [["translation", 15], ["pinyin", 15], ["reverse", 15], ["cloze", 15], ["synonym", 10], ["pos", 10], ["listening", 20]],
};

export function canUseSpeechSynthesis(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
}

function isKindAvailable(kind: QuizQuestionKind, entry: VocabQuizEntry, allEntries: VocabQuizEntry[]): boolean {
  switch (kind) {
    case "translation": return true;
    case "pinyin": return Boolean(entry.pinyin || toPinyin(entry.word));
    case "reverse": return allEntries.length >= 2;
    case "listening": return canUseSpeechSynthesis() && allEntries.length >= 2;
    case "cloze": return Boolean(entry.aiCloze?.length);
    case "pos": return Boolean(entry.pos);
    case "synonym": return Boolean(entry.aiSynonym?.length);
    case "assessment": return false;
  }
}

function pickQuestionKind(entry: VocabQuizEntry, allEntries: VocabQuizEntry[], mode: VocabQuizMode, excludedKinds: ReadonlySet<QuizQuestionKind> = new Set()): QuizQuestionKind | null {
  const weights = tierConfigFromMode(mode) ? TIER_KIND_WEIGHTS[mode as TierMode] : LEGACY_KIND_WEIGHTS;
  const available = weights.filter(([kind]) => !excludedKinds.has(kind)
    && !entry.disabledQuestionKinds?.includes(kind as "pinyin" | "reverse") && isKindAvailable(kind, entry, allEntries));
  if (!available.length) return null;
  const unseen = mode === "weak_words"
    ? available.filter(([kind]) => !entry.bktSeenQuestionKinds?.includes(kind))
    : available;
  const preferred = unseen.length ? unseen : available;
  let roll = Math.random() * preferred.reduce((sum, [, weight]) => sum + weight, 0);
  for (const [kind, weight] of preferred) {
    roll -= weight;
    if (roll <= 0) return kind;
  }
  return available[available.length - 1][0];
}

export function buildQuizQuestion(entry: VocabQuizEntry, allEntries: VocabQuizEntry[], mode: VocabQuizMode): VocabQuizQuestion;
export function buildQuizQuestion(entry: VocabQuizEntry, allEntries: VocabQuizEntry[], mode: VocabQuizMode, context: QuizQuestionBuildContext): VocabQuizQuestion | null;
export function buildQuizQuestion(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
  mode: VocabQuizMode,
  context?: QuizQuestionBuildContext,
): VocabQuizQuestion | null {
  const questionEntries = context?.distractorEntries ?? allEntries;
  const forbiddenAnswers = context?.forbiddenAnswers ?? new Set<string>();
  const tier = tierConfigFromMode(mode)?.tier ?? null;
  switch (pickQuestionKind(entry, questionEntries, mode, context?.excludedKinds)) {
    case "cloze": return buildClozeQuestion(entry, questionEntries, forbiddenAnswers);
    case "pinyin": return buildPinyinQuestion(entry, questionEntries, tier !== null && tier >= 2 ? "primary" : "pad", forbiddenAnswers);
    case "pos": return buildPosQuestion(entry, questionEntries, forbiddenAnswers);
    case "synonym": return buildSynonymQuestion(entry, questionEntries, forbiddenAnswers);
    case "reverse": return buildReverseQuestion(entry, questionEntries, forbiddenAnswers);
    case "listening": return buildListeningQuestion(entry, questionEntries, forbiddenAnswers);
    case "translation": return buildTranslationQuestion(entry, questionEntries, tier !== 1, forbiddenAnswers);
    default: return null;
  }
}

export function buildQuizQuestions(entries: VocabQuizEntry[]): VocabQuizTranslationQuestion[] {
  return shuffle(entries).slice(0, MAX_QUESTIONS).map((entry) => buildTranslationQuestion(entry, entries));
}
