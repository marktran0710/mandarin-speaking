import { toPinyin } from "./api";
import { DIAGNOSTIC_ROUNDS, tierConfigFromMode, type TierMode, type QuizTier } from "./progression";
import { toneTrapVariants } from "../../utils/toneTraps";
import { normalizeQuizExposure } from "./quizSessionPlanner";
import type {
  VocabQuizClozeCandidate,
  VocabQuizEntry,
  VocabQuizSynonymCandidate,
} from "./types";
import { MAX_QUESTIONS, OPTION_COUNT, FILLER_DISTRACTORS, buildDiagnosticRoundQuestions, shuffle } from "./quizGeneration";
import { CLOZE_BLANK, quizConceptId } from "./quizTypes";
import { normalizeQuizAnswer } from "./quizValidation";
import type { QuizQuestionBuildContext, QuizQuestionKind } from "./quizSessionPlanner";
import type { VocabAssessmentQuestion } from "./types";
import type {
  VocabQuizClozeQuestion,
  VocabQuizListeningQuestion,
  VocabQuizMode,
  VocabQuizPinyinQuestion,
  VocabQuizPosQuestion,
  VocabQuizQuestion,
  VocabQuizReverseQuestion,
  VocabQuizSynonymQuestion,
  VocabQuizTranslationQuestion,
} from "./quizTypes";

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
  tier2: [["translation", 25], ["pinyin", 15], ["reverse", 15], ["cloze", 15], ["synonym", 10]],
  tier3: [["translation", 15], ["pinyin", 15], ["reverse", 15], ["cloze", 15], ["synonym", 10], ["pos", 10]],
};

function isKindAvailable(kind: QuizQuestionKind, entry: VocabQuizEntry, allEntries: VocabQuizEntry[]): boolean {
  switch (kind) {
    case "translation": return true;
    case "pinyin": return Boolean(entry.pinyin || toPinyin(entry.word));
    case "reverse": return allEntries.length >= 2;
    case "listening": return false;
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
  const failed = mode === "weak_words"
    ? available.filter(([kind]) => (entry.bktFailedQuestionKinds ?? []).some((failedKind) =>
      failedKind === kind
      || (failedKind === "character_to_pinyin_typing" && kind === "pinyin")
      || ((failedKind === "contextual_productive_recall"
        || failedKind === "context_cloze_mcq"
        || failedKind === "productive_recall") && kind === "cloze"),
    ))
    : [];
  const unseen = mode === "weak_words"
    ? available.filter(([kind]) => !entry.bktSeenQuestionKinds?.includes(kind))
    : available;
  // Personalized practice first repairs a failed dimension. Only when that
  // dimension has no available legacy question does it prefer an unseen form.
  const preferred = failed.length ? failed : unseen.length ? unseen : available;
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

// Every extra practice kind, in a stable display order, that weak-word review
// can draw for a word (the three graded rounds are handled separately, via
// buildDiagnosticRoundQuestions). "assessment" is omitted — it's a wrapper for
// the round questions, not a standalone kind.
const PRACTICE_PREVIEW_KINDS: QuizQuestionKind[] = ["translation", "cloze", "pinyin", "pos", "synonym", "reverse"];

function buildPracticeQuestionOfKind(
  kind: QuizQuestionKind,
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
): VocabQuizQuestion | null {
  switch (kind) {
    case "translation": return buildTranslationQuestion(entry, allEntries);
    case "cloze": return buildClozeQuestion(entry, allEntries);
    case "pinyin": return buildPinyinQuestion(entry, allEntries);
    case "pos": return buildPosQuestion(entry, allEntries);
    case "synonym": return buildSynonymQuestion(entry, allEntries);
    case "reverse": return buildReverseQuestion(entry, allEntries);
    case "listening": return buildListeningQuestion(entry, allEntries);
    default: return null;
  }
}

export interface WordRoundVariant { mode: TierMode; round: QuizTier; question: VocabAssessmentQuestion; }
export interface WordPracticeVariant { kind: QuizQuestionKind; question: VocabQuizQuestion; }

/** Every question form a single word can appear as, for admin/teacher review:
 * one entry per graded round (Know it / Say it / Use it) plus every extra
 * practice kind the word's data supports (cloze/pinyin/pos/synonym/…). This
 * enumerates the kinds directly rather than going through the weighted random
 * picker the live quiz uses, so a reviewer sees the full set at once. Option
 * order is still shuffled per build (cosmetic). `allEntries` supplies the
 * distractor pool, so pass the word's whole lesson. */
export function buildWordQuestionVariants(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
): { rounds: WordRoundVariant[]; practice: WordPracticeVariant[] } {
  const wordId = entry.wordId ?? quizConceptId(entry.word);
  const rounds = (["tier1", "tier2", "tier3"] as const)
    .map((mode): WordRoundVariant | null => {
      const question = buildDiagnosticRoundQuestions(allEntries, mode).find((q) => q.wordId === wordId);
      return question ? { mode, round: DIAGNOSTIC_ROUNDS[mode].round, question } : null;
    })
    .filter((value): value is WordRoundVariant => value !== null);
  const practice = PRACTICE_PREVIEW_KINDS
    .filter((kind) => isKindAvailable(kind, entry, allEntries))
    .map((kind): WordPracticeVariant | null => {
      const question = buildPracticeQuestionOfKind(kind, entry, allEntries);
      return question ? { kind, question } : null;
    })
    .filter((value): value is WordPracticeVariant => value !== null);
  return { rounds, practice };
}
