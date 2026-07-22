import { useEffect, useRef, useState } from "react";
import { BiLabel } from "./BiLabel";
import { toPinyin } from "../utils/pinyin";
import { toneTrapVariants } from "../utils/toneTraps";
import {
  TIER_CONFIGS,
  attemptEarnsStar,
  isTierUnlocked,
  loadLocalStars,
  nextStarGap,
  practiceUnlocked,
  recordLocalStars,
  starsFromAttempts,
  tierConfigFromMode,
  type QuizTier,
  type TierMode,
} from "../utils/quizTiers";
import {
  canUseDatabase,
  getVocabQuizWeakWords,
  listVocabQuizAttempts,
} from "../services/database";
import "./StoryVocabQuiz.css";

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
  // Teacher-authored pinyin for this word, if any — falls back to a computed
  // reading (see the Review screen) when absent.
  pinyin?: string;
  // Teacher-authored part of speech (N/V/ADJ/...), if any — undefined means
  // this word never becomes a "part of speech" question.
  pos?: string;
  // AI-generated wrong-but-plausible translations for this word (see
  // buildTranslationQuestion) — undefined/empty falls back to the old
  // real-word-pool + generic-filler distractor logic.
  aiDistractors?: string[];
  // AI-generated fill-in-the-blank sentences for this word (see
  // buildClozeQuestion) — undefined/empty means this word never becomes a
  // cloze question, only a translation one.
  aiCloze?: VocabQuizClozeCandidate[];
  // AI-generated synonym candidates for this word (see
  // buildSynonymQuestion) — undefined/empty means this word never becomes a
  // synonym question.
  aiSynonym?: VocabQuizSynonymCandidate[];
  // AI-generated visually-confusable words (喝/渴) — tier 3's face-confusion
  // traps, leading the distractor pool of reverse/listening questions there
  // (see buildReverseQuestion/buildListeningQuestion). Lower tiers ignore
  // them entirely.
  aiLookalike?: string[];
}

// The blank marker inside a cloze question's sentence — split out at render
// time so it can be styled distinctly from the surrounding text.
export const CLOZE_BLANK = "____";

export interface VocabQuizTranslationQuestion {
  kind: "translation";
  word: string;
  correctTranslation: string;
  options: string[];
  // True when at least one of the shown options came from AI-generated
  // distractors rather than the story's other words / generic filler.
  isAiGenerated: boolean;
}

export interface VocabQuizClozeQuestion {
  kind: "cloze";
  word: string;
  // The candidate's sentence with `word`'s first occurrence replaced by
  // CLOZE_BLANK.
  sentenceWithBlank: string;
  correctWord: string;
  options: string[];
  // Cloze questions only exist via AI generation — always true.
  isAiGenerated: true;
}

export interface VocabQuizPinyinQuestion {
  kind: "pinyin";
  word: string;
  correctPinyin: string;
  options: string[];
  // Pinyin questions are computed deterministically, never AI-generated.
  isAiGenerated: false;
}

export interface VocabQuizPosQuestion {
  kind: "pos";
  word: string;
  correctPos: string;
  options: string[];
  // Part-of-speech questions use teacher-authored data, never AI-generated.
  isAiGenerated: false;
}

export interface VocabQuizSynonymQuestion {
  kind: "synonym";
  word: string;
  correctSynonym: string;
  options: string[];
  // Synonym questions only exist via AI generation — always true.
  isAiGenerated: true;
}

export interface VocabQuizReverseQuestion {
  kind: "reverse";
  word: string;
  // The English translation shown as the prompt — the answer is the word.
  translation: string;
  correctWord: string;
  options: string[];
  // True when at least one option came from the AI look-alike pool (tier 3)
  // rather than the story's other words.
  isAiGenerated: boolean;
}

export interface VocabQuizListeningQuestion {
  kind: "listening";
  word: string;
  // The prompt is spoken (browser TTS), never written — the shown options
  // are Chinese words and the student picks the one they heard.
  correctWord: string;
  options: string[];
  // True when at least one option came from the AI look-alike pool (tier 3)
  // rather than the story's other words.
  isAiGenerated: boolean;
}

export type VocabQuizQuestion =
  | VocabQuizTranslationQuestion
  | VocabQuizClozeQuestion
  | VocabQuizPinyinQuestion
  | VocabQuizPosQuestion
  | VocabQuizSynonymQuestion
  | VocabQuizReverseQuestion
  | VocabQuizListeningQuestion;

export interface VocabQuizQuestionResult {
  word: string;
  correct: boolean;
  timeMs: number;
}

export interface VocabQuizSummary {
  mode: VocabQuizMode;
  totalQuestions: number;
  correctCount: number;
  totalTimeMs: number;
  questionResults: VocabQuizQuestionResult[];
}

// The scored modes are the three star tiers (see quizTiers.ts): a fixed
// question count each, escalating difficulty/distractors, and a star for
// meeting the tier's pass threshold. "weak_words" mirrors "free"'s
// unlimited/no-timer engine but, unlike the same-session missed-words retry
// below, is a real scored mode: it reports via onComplete and gets saved as
// an attempt, so a correct answer there actually clears the word from the
// next weak-words list (see getVocabQuizWeakWords) rather than resetting on
// page leave.
export type VocabQuizMode = TierMode | "free" | "weak_words";

const MAX_QUESTIONS = 8;
const OPTION_COUNT = 4;

const TIMER_TICK_MS = 100;

// Generic filler distractors, used only to pad out a question's wrong
// answers when the story itself doesn't have enough other translated words
// to draw real distractors from (common for a story with just 1-2 glossed
// words so far). Never shown as the correct answer.
const FILLER_DISTRACTORS = [
  "friend", "house", "water", "book", "school",
  "happy", "morning", "money", "food", "family",
  "teacher", "street", "weather", "car", "phone",
];

function shuffle<T>(items: T[]): T[] {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

/** "Would a student read these two options as the same answer?" form:
 * lowercased, trimmed, trailing punctuation stripped. Every question
 * builder compares answers through this so a distractor can never be a
 * disguised second correct option ("Restaurant." vs "restaurant"). */
function normalizeAnswer(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[.。!！?？]+$/u, "")
    .trim();
}

/** The word's reading for sound-based comparisons (authored pinyin first,
 * computed otherwise), normalized for spacing/case differences. */
function normalizeReading(entry: VocabQuizEntry): string {
  return (entry.pinyin || toPinyin(entry.word)).trim().toLowerCase().replace(/\s+/g, " ");
}

/** Dedupes a story's vocabulary (by word, across every scene) down to the
 * entries that have a translation filled in — a question can't be asked
 * about a word the teacher hasn't glossed. When `suggestedAnswers` is given
 * (one entry per word, aligned by index — typically the scene's suggested-
 * answer sentence repeated for each of that scene's words), a word is only
 * kept if it also actually appears in its scene's sentence, confirming it's
 * used in real context rather than an isolated flashcard pair. Without
 * `suggestedAnswers`, every translated word qualifies (no context to check
 * against). */
export function collectQuizEntries(
  words: string[],
  translations: Array<string | undefined>,
  suggestedAnswers?: Array<string | undefined>,
  aiDistractors?: Array<string[] | undefined>,
  pinyins?: Array<string | undefined>,
  aiCloze?: Array<VocabQuizClozeCandidate[] | undefined>,
  partsOfSpeech?: Array<string | undefined>,
  aiSynonym?: Array<VocabQuizSynonymCandidate[] | undefined>,
  aiLookalike?: Array<string[] | undefined>,
): VocabQuizEntry[] {
  const seen = new Set<string>();
  const entries: VocabQuizEntry[] = [];
  words.forEach((word, i) => {
    const translation = translations[i]?.trim();
    if (!translation || seen.has(word)) return;
    const context = suggestedAnswers?.[i];
    if (context !== undefined && !context.includes(word)) return;
    seen.add(word);
    const distractors = aiDistractors?.[i];
    const pinyin = pinyins?.[i]?.trim();
    const pos = partsOfSpeech?.[i]?.trim();
    // A candidate is only usable once it actually has a distractor and its
    // sentence really contains the word — belt-and-suspenders on top of the
    // backend's own validation, in case stale/malformed data slipped through.
    const cloze = (aiCloze?.[i] ?? []).filter(
      (c) => c.distractors.length > 0 && c.sentence.includes(word),
    );
    const synonym = (aiSynonym?.[i] ?? []).filter(
      (c) => c.distractors.length > 0 && c.synonym !== word,
    );
    const lookalike = (aiLookalike?.[i] ?? []).filter((l) => l && l !== word);
    entries.push({
      word,
      translation,
      ...(distractors?.length ? { aiDistractors: distractors } : {}),
      ...(pinyin ? { pinyin } : {}),
      ...(pos ? { pos } : {}),
      ...(cloze.length ? { aiCloze: cloze } : {}),
      ...(synonym.length ? { aiSynonym: synonym } : {}),
      ...(lookalike.length ? { aiLookalike: lookalike } : {}),
    });
  });
  return entries;
}

/** Builds one multiple-choice question for `entry`, offering its correct
 * translation plus up to OPTION_COUNT-1 distractors. AI-generated distractors
 * (near-synonyms, same part of speech — real wrong answers a student might
 * actually pick) are used first when available; the story's other translated
 * words, then generic filler words, pad out any remaining slots — covering
 * both a story with no AI distractors yet and one where the AI returned
 * fewer than OPTION_COUNT-1 for a word. Tier 1 passes `useAiDistractors:
 * false` so its options stay easy to tell apart — the near-miss traps are a
 * tier 2+ difficulty lever, not a starting hurdle. */
function buildTranslationQuestion(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
  useAiDistractors = true,
): VocabQuizTranslationQuestion {
  // Tracked in normalized form so "Restaurant." can never slip in beside
  // "restaurant" as a disguised second correct answer.
  const usedTranslations = new Set([normalizeAnswer(entry.translation)]);

  const aiPool = useAiDistractors
    ? (entry.aiDistractors ?? []).filter((d) => !usedTranslations.has(normalizeAnswer(d)))
    : [];
  const aiDistractors = shuffle(aiPool).slice(0, OPTION_COUNT - 1);
  aiDistractors.forEach((d) => usedTranslations.add(normalizeAnswer(d)));

  const realDistractorPool = Array.from(
    new Set(
      allEntries
        .filter(
          (e) => e.word !== entry.word && !usedTranslations.has(normalizeAnswer(e.translation)),
        )
        .map((e) => e.translation),
    ),
  );
  const realDistractors = shuffle(realDistractorPool).slice(
    0,
    OPTION_COUNT - 1 - aiDistractors.length,
  );
  realDistractors.forEach((d) => usedTranslations.add(normalizeAnswer(d)));

  const fillerPool = FILLER_DISTRACTORS.filter((word) => !usedTranslations.has(normalizeAnswer(word)));
  const fillerDistractors = shuffle(fillerPool).slice(
    0,
    OPTION_COUNT - 1 - aiDistractors.length - realDistractors.length,
  );

  const options = shuffle([
    entry.translation,
    ...aiDistractors,
    ...realDistractors,
    ...fillerDistractors,
  ]);
  return {
    kind: "translation",
    word: entry.word,
    correctTranslation: entry.translation,
    options,
    isAiGenerated: aiDistractors.length > 0,
  };
}

/** Builds one fill-in-the-blank question from a randomly-picked cached AI
 * cloze candidate for `entry` (only called when at least one exists — see
 * buildQuizQuestion). Wrong-word options are drawn the same tiered way as
 * buildTranslationQuestion's distractors: the candidate's own AI-generated
 * words first, then other story words, since there's no Chinese-word
 * equivalent of FILLER_DISTRACTORS to pad out the rest with. */
function buildClozeQuestion(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
): VocabQuizClozeQuestion {
  const candidate = shuffle(entry.aiCloze!)[0];
  const usedWords = new Set([entry.word]);

  const aiWordPool = candidate.distractors.filter((d) => !usedWords.has(d));
  const aiWordDistractors = shuffle(aiWordPool).slice(0, OPTION_COUNT - 1);
  aiWordDistractors.forEach((d) => usedWords.add(d));

  const realWordPool = Array.from(
    new Set(
      allEntries
        .filter(
          (e) =>
            e.word !== entry.word &&
            !usedWords.has(e.word) &&
            // A story word meaning the same thing (高興/開心 both "happy")
            // would fit the blank just as well — a second correct answer.
            normalizeAnswer(e.translation) !== normalizeAnswer(entry.translation),
        )
        .map((e) => e.word),
    ),
  );
  const realWordDistractors = shuffle(realWordPool).slice(
    0,
    OPTION_COUNT - 1 - aiWordDistractors.length,
  );

  const options = shuffle([entry.word, ...aiWordDistractors, ...realWordDistractors]);
  return {
    kind: "cloze",
    word: entry.word,
    sentenceWithBlank: candidate.sentence.replace(entry.word, CLOZE_BLANK),
    correctWord: entry.word,
    options,
    isAiGenerated: true,
  };
}

/** Builds a "how do you read this?" question: the word's correct pinyin
 * (teacher-authored, or computed the same way the Review screen does) among
 * up to OPTION_COUNT-1 wrong readings — always buildable, since every
 * Chinese word has a computed reading even without a teacher-authored one.
 *
 * Distractor sourcing is the tier-difficulty lever: `toneTraps: "primary"`
 * (tier 2+) leads with readings that differ by exactly one syllable's tone
 * (hē chá → hé chá) so the student must really know the tones, while
 * `"pad"` (tier 1 / legacy modes) keeps the easy other-words readings first
 * and only falls back to tone traps when the story is too small to fill the
 * options. */
function buildPinyinQuestion(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
  toneTraps: "primary" | "pad" = "pad",
): VocabQuizPinyinQuestion {
  const correctPinyin = entry.pinyin || toPinyin(entry.word);
  const usedPinyin = new Set([correctPinyin]);

  const otherWordPool = Array.from(
    new Set(
      allEntries
        .filter((e) => e.word !== entry.word)
        .map((e) => e.pinyin || toPinyin(e.word))
        .filter((p) => p && !usedPinyin.has(p)),
    ),
  );
  const trapPool = toneTrapVariants(correctPinyin).filter((p) => !usedPinyin.has(p));

  const distractors: string[] = [];
  const pools = toneTraps === "primary" ? [trapPool, otherWordPool] : [otherWordPool, trapPool];
  for (const pool of pools) {
    for (const candidate of shuffle(pool)) {
      if (distractors.length >= OPTION_COUNT - 1) break;
      if (usedPinyin.has(candidate)) continue;
      usedPinyin.add(candidate);
      distractors.push(candidate);
    }
  }

  const options = shuffle([correctPinyin, ...distractors]);
  return {
    kind: "pinyin",
    word: entry.word,
    correctPinyin,
    options,
    isAiGenerated: false,
  };
}

/** Builds the reverse of a translation question: the English translation is
 * the prompt and the student picks the Chinese word for it. At tier 3
 * (`useLookalikes`) the wrong options lead with the word's AI look-alike
 * characters (喝/渴) — the face-confusion traps — before falling back to the
 * story's other words; either pool excludes any word that means the same
 * thing, which would be a second correct answer for the shown translation. */
function buildReverseQuestion(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
  useLookalikes = false,
): VocabQuizReverseQuestion {
  const usedWords = new Set([entry.word]);

  const lookalikePool = useLookalikes
    ? (entry.aiLookalike ?? []).filter((l) => !usedWords.has(l))
    : [];
  const lookalikeDistractors = shuffle(lookalikePool).slice(0, OPTION_COUNT - 1);
  lookalikeDistractors.forEach((l) => usedWords.add(l));

  const realWordPool = Array.from(
    new Set(
      allEntries
        .filter(
          (e) =>
            !usedWords.has(e.word) &&
            e.word !== entry.word &&
            normalizeAnswer(e.translation) !== normalizeAnswer(entry.translation),
        )
        .map((e) => e.word),
    ),
  );
  const realWordDistractors = shuffle(realWordPool).slice(
    0,
    OPTION_COUNT - 1 - lookalikeDistractors.length,
  );

  return {
    kind: "reverse",
    word: entry.word,
    translation: entry.translation,
    correctWord: entry.word,
    options: shuffle([entry.word, ...lookalikeDistractors, ...realWordDistractors]),
    isAiGenerated: lookalikeDistractors.length > 0,
  };
}

/** Builds a listening question: the word is spoken aloud (browser TTS, see
 * the speak effect in the component) and the student picks the word they
 * heard. At tier 3 (`useLookalikes`) the wrong options lead with the word's
 * AI look-alikes before the story's other words. Words that would also be
 * right by ear or meaning are excluded from either pool: homophones (他/她,
 * identical reading) sound exactly like the answer, and same-translation
 * words are ambiguous the moment the student mentally translates what they
 * heard. */
function buildListeningQuestion(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
  useLookalikes = false,
): VocabQuizListeningQuestion {
  const reading = normalizeReading(entry);
  const usedWords = new Set([entry.word]);

  const lookalikePool = useLookalikes
    ? (entry.aiLookalike ?? []).filter(
        (l) =>
          !usedWords.has(l) &&
          toPinyin(l).trim().toLowerCase().replace(/\s+/g, " ") !== reading,
      )
    : [];
  const lookalikeDistractors = shuffle(lookalikePool).slice(0, OPTION_COUNT - 1);
  lookalikeDistractors.forEach((l) => usedWords.add(l));

  const realWordPool = Array.from(
    new Set(
      allEntries
        .filter(
          (e) =>
            !usedWords.has(e.word) &&
            e.word !== entry.word &&
            normalizeReading(e) !== reading &&
            normalizeAnswer(e.translation) !== normalizeAnswer(entry.translation),
        )
        .map((e) => e.word),
    ),
  );
  const realWordDistractors = shuffle(realWordPool).slice(
    0,
    OPTION_COUNT - 1 - lookalikeDistractors.length,
  );

  return {
    kind: "listening",
    word: entry.word,
    correctWord: entry.word,
    options: shuffle([entry.word, ...lookalikeDistractors, ...realWordDistractors]),
    isAiGenerated: lookalikeDistractors.length > 0,
  };
}

// Fallback pool when a story doesn't have enough distinct teacher-authored
// parts of speech to draw real distractors from — mirrors FILLER_DISTRACTORS
// above, just for POS tags instead of English words.
const FILLER_POS = ["N", "V", "ADJ", "ADV", "MW", "PREP", "CONJ", "PRON"];

/** Builds a "what part of speech is this?" question — only called when
 * `entry.pos` is set (see buildQuizQuestion). Distractors: other story
 * words' POS tags first, then the generic POS pool above. */
function buildPosQuestion(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
): VocabQuizPosQuestion {
  const correctPos = entry.pos!;
  const usedPos = new Set([correctPos]);

  const realPosPool = Array.from(
    new Set(
      allEntries
        .filter((e) => e.word !== entry.word && e.pos && !usedPos.has(e.pos))
        .map((e) => e.pos!),
    ),
  );
  const realDistractors = shuffle(realPosPool).slice(0, OPTION_COUNT - 1);
  realDistractors.forEach((p) => usedPos.add(p));

  const fillerPool = FILLER_POS.filter((p) => !usedPos.has(p));
  const fillerDistractors = shuffle(fillerPool).slice(
    0,
    OPTION_COUNT - 1 - realDistractors.length,
  );

  const options = shuffle([correctPos, ...realDistractors, ...fillerDistractors]);
  return {
    kind: "pos",
    word: entry.word,
    correctPos,
    options,
    isAiGenerated: false,
  };
}

/** Builds a "which word means the same?" question from a randomly-picked
 * cached AI synonym candidate for `entry` (only called when at least one
 * exists — see buildQuizQuestion). Mirrors buildClozeQuestion's tiered
 * wrong-option sourcing: the candidate's own AI-generated distractors
 * first, then other story words. */
function buildSynonymQuestion(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
): VocabQuizSynonymQuestion {
  const candidate = shuffle(entry.aiSynonym!)[0];
  const usedWords = new Set([entry.word, candidate.synonym]);

  const aiWordPool = candidate.distractors.filter((d) => !usedWords.has(d));
  const aiWordDistractors = shuffle(aiWordPool).slice(0, OPTION_COUNT - 1);
  aiWordDistractors.forEach((d) => usedWords.add(d));

  const realWordPool = Array.from(
    new Set(
      allEntries
        .filter(
          (e) =>
            e.word !== entry.word &&
            !usedWords.has(e.word) &&
            // A story word sharing the target's translation is itself a
            // synonym — a second correct "means the same" answer.
            normalizeAnswer(e.translation) !== normalizeAnswer(entry.translation),
        )
        .map((e) => e.word),
    ),
  );
  const realWordDistractors = shuffle(realWordPool).slice(
    0,
    OPTION_COUNT - 1 - aiWordDistractors.length,
  );

  const options = shuffle([candidate.synonym, ...aiWordDistractors, ...realWordDistractors]);
  return {
    kind: "synonym",
    word: entry.word,
    correctSynonym: candidate.synonym,
    options,
    isAiGenerated: true,
  };
}

// Relative weights for picking a question kind among whichever are actually
// available for a given entry (translation and pinyin are always available;
// reverse/listening need at least two story words for their Chinese-word
// options — and listening needs speech synthesis; cloze/pos/synonym only
// when the entry has the matching data — see buildQuizQuestion). Each mode
// mixes its own kinds: tier 1 keeps to the direct forms, tiers 2-3 add the
// harder shapes, and the legacy weights power the free/weak-words rounds.
// Translation stays dominant throughout, appropriate for A1-A2 learners.
type QuestionKind =
  | "translation"
  | "cloze"
  | "pinyin"
  | "pos"
  | "synonym"
  | "reverse"
  | "listening";

// Order matters beyond weighting: availability is checked in list order, so
// tests can force "the last available kind" deterministically.
type KindWeights = Array<[QuestionKind, number]>;
const LEGACY_KIND_WEIGHTS: KindWeights = [
  ["translation", 50],
  ["pinyin", 20],
  ["cloze", 15],
  ["pos", 5],
  ["synonym", 10],
];
const TIER_KIND_WEIGHTS: Record<TierMode, KindWeights> = {
  tier1: [
    ["translation", 50],
    ["pinyin", 20],
    ["reverse", 30],
  ],
  tier2: [
    ["translation", 25],
    ["pinyin", 15],
    ["reverse", 15],
    ["cloze", 15],
    ["synonym", 10],
    ["listening", 20],
  ],
  tier3: [
    ["translation", 15],
    ["pinyin", 15],
    ["reverse", 15],
    ["cloze", 15],
    ["synonym", 10],
    ["pos", 10],
    ["listening", 20],
  ],
};

function canUseSpeechSynthesis(): boolean {
  return (
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    "SpeechSynthesisUtterance" in window
  );
}

function isKindAvailable(
  kind: QuestionKind,
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
): boolean {
  switch (kind) {
    case "translation":
      return true;
    case "pinyin":
      // A word with no authored pinyin and no computable reading (e.g. an
      // English key word) would produce a question whose answer is empty.
      return Boolean(entry.pinyin || toPinyin(entry.word));
    case "reverse":
      return allEntries.length >= 2;
    case "listening":
      return allEntries.length >= 2 && canUseSpeechSynthesis();
    case "cloze":
      return Boolean(entry.aiCloze?.length);
    case "pos":
      return Boolean(entry.pos);
    case "synonym":
      return Boolean(entry.aiSynonym?.length);
  }
}

function pickQuestionKind(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
  mode: VocabQuizMode,
): QuestionKind {
  const weights = tierConfigFromMode(mode)
    ? TIER_KIND_WEIGHTS[mode as TierMode]
    : LEGACY_KIND_WEIGHTS;
  const available = weights.filter(([kind]) => isKindAvailable(kind, entry, allEntries));

  const total = available.reduce((sum, [, weight]) => sum + weight, 0);
  let roll = Math.random() * total;
  for (const [kind, weight] of available) {
    roll -= weight;
    if (roll <= 0) return kind;
  }
  return available[available.length - 1][0];
}

function buildQuizQuestion(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
  mode: VocabQuizMode,
): VocabQuizQuestion {
  const tier = tierConfigFromMode(mode)?.tier ?? null;
  switch (pickQuestionKind(entry, allEntries, mode)) {
    case "cloze":
      return buildClozeQuestion(entry, allEntries);
    case "pinyin":
      // Tone traps lead from tier 2 up; tier 1 and legacy modes keep the
      // easy other-words readings first (traps only pad small stories).
      return buildPinyinQuestion(entry, allEntries, tier !== null && tier >= 2 ? "primary" : "pad");
    case "pos":
      return buildPosQuestion(entry, allEntries);
    case "synonym":
      return buildSynonymQuestion(entry, allEntries);
    case "reverse":
      // Look-alike traps are tier 3's signature difficulty bump.
      return buildReverseQuestion(entry, allEntries, tier === 3);
    case "listening":
      return buildListeningQuestion(entry, allEntries, tier === 3);
    default:
      // Tier 1 keeps its translation options easy — no AI near-miss traps.
      return buildTranslationQuestion(entry, allEntries, tier !== 1);
  }
}

/** Builds up to MAX_QUESTIONS multiple-choice translation questions, one per
 * entry, all at once. The live quiz below generates questions one at a time
 * instead (an endless shuffle-bag, so Speed/Strikes/Free/retry rounds can
 * each set their own question count independently, and mix in cloze — see
 * buildQuizQuestion) — this batch form is kept as a standalone utility. */
export function buildQuizQuestions(entries: VocabQuizEntry[]): VocabQuizTranslationQuestion[] {
  const pool = shuffle(entries).slice(0, MAX_QUESTIONS);
  return pool.map((entry) => buildTranslationQuestion(entry, entries));
}

// The star ladder shown on mode-select: one card per tier, in climbing
// order. Copy stays at A1-A2 chrome level (第一關/第二關/第三關 — "level 1/2/3").
const TIER_CARDS: Array<{
  mode: TierMode;
  icon: string;
  title: string;
  titlePinyin: string;
  titleEn: string;
  desc: string;
  descPinyin: string;
  descEn: string;
}> = [
  {
    mode: "tier1",
    icon: "⭐",
    title: "第一關",
    titlePinyin: "Dì yī guān",
    titleEn: "Tier 1",
    desc: "20 題 — 答對 14 題就過關。",
    descPinyin: "20 tí — dá duì 14 tí jiù guòguān.",
    descEn: "20 questions — 14 right to pass.",
  },
  {
    mode: "tier2",
    icon: "⭐⭐",
    title: "第二關",
    titlePinyin: "Dì èr guān",
    titleEn: "Tier 2",
    desc: "22 題，選項更難 — 答對 18 題就能開始說話練習。",
    descPinyin: "22 tí, xuǎnxiàng gèng nán — dá duì 18 tí jiù néng kāishǐ shuōhuà liànxí.",
    descEn: "22 questions, trickier options — 18 right opens speaking practice.",
  },
  {
    mode: "tier3",
    icon: "⭐⭐⭐",
    title: "第三關",
    titlePinyin: "Dì sān guān",
    titleEn: "Tier 3",
    desc: "25 題，150 秒，有陷阱 — 答對 22 題。",
    descPinyin: "25 tí, 150 miǎo, yǒu xiànjǐng — dá duì 22 tí.",
    descEn: "25 questions in 150s, with traps — 22 right to pass.",
  },
];

const REVIEW_CARD = {
  icon: "📖",
  title: "複習模式",
  titlePinyin: "Fùxí móshì",
  titleEn: "Review",
  desc: "沒有題目限制 — 直接看所有生詞和它們的聲調。",
  descPinyin: "Méiyǒu tímù xiànzhì — zhíjiē kàn suǒyǒu shēngcí hàn tāmen de shēngdiào.",
  descEn: "No question limit — just browse every word and its tones.",
};

/** A multiple-choice vocabulary check covering every glossed word in the
 * story, shown before a student starts practicing any scene, structured as
 * a three-tier star ladder (see quizTiers.ts): speaking practice unlocks at
 * ⭐⭐ (pass tier 1, then tier 2 — see practiceUnlocked), with tier 3 as an
 * optional extra challenge for the last star. Always mandatory — no skip
 * button in any scored mode; `onBack` (if given) is the only way out before
 * finishing, and it doesn't count as completion. Review mode is the
 * exception: it's a browsable list, not a quiz, so it never produces a
 * summary and never unlocks practice on its own. `onComplete`, when given,
 * fires once per scored round with a full results summary — on a genuine
 * finish (every question answered or timed out), never on back-out, and
 * never for the missed-words retry round offered afterward (that round is a
 * same-session drill, not a new scored attempt — unlike Try again, which
 * starts a fresh scored run of the same tier). */
export default function StoryVocabQuiz({
  entries,
  onDone,
  onBack,
  onComplete,
  storyId,
  studentId,
  studentName,
  alreadyCompleted,
}: {
  entries: VocabQuizEntry[];
  onDone: () => void;
  onBack?: () => void;
  onComplete?: (summary: VocabQuizSummary) => void;
  // All three optional and only used to fetch the persistent weak-words
  // list (see getVocabQuizWeakWords) and this story's earned stars —
  // omitting storyId/student identity just means the weak-words card never
  // appears and stars only come from this device's localStorage.
  storyId?: string;
  studentId?: string;
  studentName?: string;
  // True when this student already unlocked practice for this story in a
  // past visit — keeps "Continue to practice" available on the summary even
  // after a failed run (the gate only applies to the first unlock).
  alreadyCompleted?: boolean;
}) {
  const [screen, setScreen] = useState<"mode-select" | "quiz" | "review" | "summary">("mode-select");
  const [mode, setMode] = useState<VocabQuizMode | null>(null);
  const [roundEntries, setRoundEntries] = useState(entries);
  const [isRetryRound, setIsRetryRound] = useState(false);
  // null = unlimited (Free): questions are generated endlessly from a
  // reshuffled bag until the student ends the round. A number bounds the
  // round to exactly that many questions (a tier's configured count, a
  // missed-words retry = exactly that many missed words).
  const [questionLimit, setQuestionLimit] = useState<number | null>(null);

  const [questions, setQuestions] = useState<VocabQuizQuestion[]>([]);
  const bagRef = useRef<VocabQuizEntry[]>([]);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [results, setResults] = useState<VocabQuizQuestionResult[]>([]);
  const [timeLeftMs, setTimeLeftMs] = useState(0);
  const questionStartRef = useRef(Date.now());
  const quizStartRef = useRef(Date.now());

  // This story's earned stars: seeded from this device's localStorage for an
  // instant first paint, then raised (never lowered) by whatever the attempt
  // history on the backend proves — so stars follow the student across
  // devices once attempts sync.
  const [stars, setStars] = useState<0 | QuizTier>(() =>
    storyId ? loadLocalStars(storyId) : 0,
  );
  useEffect(() => {
    if (!storyId || !canUseDatabase()) return;
    let cancelled = false;
    listVocabQuizAttempts(storyId, { studentId, studentName })
      .then((attempts) => {
        if (cancelled) return;
        const derived = starsFromAttempts(attempts);
        setStars((current) => (derived > current ? derived : current));
      })
      .catch(() => {
        /* best-effort — localStorage stars still apply */
      });
    return () => {
      cancelled = true;
    };
  }, [storyId, studentId, studentName]);


  const [weakWords, setWeakWords] = useState<string[]>([]);
  useEffect(() => {
    if (!storyId || !canUseDatabase()) return;
    let cancelled = false;
    getVocabQuizWeakWords(storyId, { studentId, studentName })
      .then((words) => {
        if (!cancelled) setWeakWords(words);
      })
      .catch(() => {
        /* best-effort — the weak-words card just stays hidden */
      });
    return () => {
      cancelled = true;
    };
  }, [storyId, studentId, studentName]);
  const weakEntries = entries.filter((e) => weakWords.includes(e.word));

  const question = questions[index];
  const isLast = questionLimit !== null && index === questionLimit - 1;
  // "free" is no longer offered from mode-select (replaced by Review), but
  // its unlimited/no-timer engine still powers the missed-words retry below
  // — always with a real questionLimit there, so this stays false in
  // practice. Kept rather than deleted in case an unlimited scored mode is
  // ever wanted again.
  const showFinishButton = mode === "free" && questionLimit === null;

  // Draws the next entry from an endlessly-reshuffled "bag" — every entry is
  // asked once before any repeats, rather than pure random-with-replacement.
  const drawFromBag = (pool: VocabQuizEntry[]): VocabQuizEntry => {
    if (bagRef.current.length === 0) bagRef.current = shuffle(pool);
    return bagRef.current.shift()!;
  };

  // Guards against finishing twice: the countdown ticker can fire several
  // times before React re-renders and tears the interval down (e.g. several
  // ticks land past the total-time cap in the same batch), and without this
  // guard each of those would re-report onComplete and re-enter "summary".
  const finishedRef = useRef(false);

  const finish = (finalResults: VocabQuizQuestionResult[]) => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    const correctCount = finalResults.filter((r) => r.correct).length;
    if (!isRetryRound) {
      // A passing tier run earns its star on the spot — recorded locally
      // (and implicitly on the backend via the attempt the caller saves in
      // onComplete, which starsFromAttempts re-derives next visit).
      const earned = attemptEarnsStar(mode, correctCount);
      if (earned !== null) {
        if (storyId) recordLocalStars(storyId, earned);
        setStars((current) => (earned > current ? earned : current));
      }
      onComplete?.({
        mode: mode!,
        totalQuestions: finalResults.length,
        correctCount,
        totalTimeMs: Date.now() - quizStartRef.current,
        questionResults: finalResults,
      });
    }
    setScreen("summary");
  };

  const recordAnswer = (correct: boolean, chosen: string) => {
    setSelected(chosen);
    setResults([
      ...results,
      { word: question.word, correct, timeMs: Date.now() - questionStartRef.current },
    ]);
  };

  const correctAnswer = (q: VocabQuizQuestion) => {
    switch (q.kind) {
      case "translation":
        return q.correctTranslation;
      case "cloze":
        return q.correctWord;
      case "pinyin":
        return q.correctPinyin;
      case "pos":
        return q.correctPos;
      case "synonym":
        return q.correctSynonym;
      case "reverse":
      case "listening":
        return q.correctWord;
    }
  };

  const choose = (option: string) => {
    if (selected) return;
    recordAnswer(option === correctAnswer(question), option);
  };

  const next = () => {
    setSelected(null);
    if (isLast) {
      finish(results);
      return;
    }
    questionStartRef.current = Date.now();
    const nextIndex = index + 1;
    if (!questions[nextIndex]) {
      const nextQuestion = buildQuizQuestion(drawFromBag(roundEntries), roundEntries, mode!);
      setQuestions((qs) => [...qs, nextQuestion]);
    }
    setIndex(nextIndex);
  };

  // The overall time cap for timed tiers (tier 3's 150s) — no per-question
  // timer, just a countdown on the whole run, checked each tick against
  // wall-clock elapsed time (so it survives tab throttling better than a
  // decrementing counter). timeLeftMs is recomputed from that same
  // elapsed-time check purely for display — the finish() call above is
  // still what actually ends the round.
  const timeLimitMs = tierConfigFromMode(mode)?.timeLimitMs ?? null;
  useEffect(() => {
    if (timeLimitMs === null || screen !== "quiz" || selected) return;
    const tick = window.setInterval(() => {
      const remaining = timeLimitMs - (Date.now() - quizStartRef.current);
      if (remaining <= 0) {
        setTimeLeftMs(0);
        finish(results);
        return;
      }
      setTimeLeftMs(remaining);
    }, TIMER_TICK_MS);
    return () => window.clearInterval(tick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeLimitMs, screen, selected, index]);

  // Listening questions have no written prompt — speak the word as soon as
  // the question appears (and again via the replay button in the header).
  const speakWord = (text: string) => {
    if (!canUseSpeechSynthesis()) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "zh-TW";
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  };
  useEffect(() => {
    if (screen !== "quiz" || question?.kind !== "listening" || selected) return;
    speakWord(question.correctWord);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, index, question?.kind]);

  // `entriesForRound`/`limit` are explicit params (not read from state) so
  // a retry launched via practiceMissedWords() below can't read a stale
  // `roundEntries` closure from before its own setRoundEntries takes effect.
  const chooseMode = (
    picked: VocabQuizMode,
    entriesForRound: VocabQuizEntry[],
    limit: number | null,
  ) => {
    setMode(picked);
    setScreen("quiz");
    setRoundEntries(entriesForRound);
    setQuestionLimit(limit);
    setIndex(0);
    setSelected(null);
    setResults([]);
    setTimeLeftMs(tierConfigFromMode(picked)?.timeLimitMs ?? 0);
    bagRef.current = shuffle(entriesForRound);
    setQuestions([buildQuizQuestion(bagRef.current.shift()!, entriesForRound, picked)]);
    quizStartRef.current = Date.now();
    questionStartRef.current = Date.now();
    finishedRef.current = false;
  };

  const startTier = (tierMode: TierMode) => {
    setIsRetryRound(false);
    chooseMode(tierMode, entries, TIER_CONFIGS[tierMode].questionCount);
  };

  const missedWords = results.filter((r) => !r.correct);
  const missedEntries = roundEntries.filter((e) =>
    missedWords.some((r) => r.word === e.word),
  );

  const practiceMissedWords = () => {
    setIsRetryRound(true);
    chooseMode("free", missedEntries, missedEntries.length);
  };

  if (screen === "mode-select") {
    return (
      <section className="story-vocab-quiz vocab-quiz-mode-select" aria-label="Vocabulary quiz">
        {onBack && (
          <button type="button" className="btn-vocab-quiz-back" onClick={onBack}>
            <BiLabel zh="← 回活動" pinyin="← Huí huódòng" en="← Back to activities" />
          </button>
        )}
        <div className="vocab-quiz-header">
          <p className="eyebrow">
            <BiLabel zh="生詞測驗" pinyin="Shēngcí cèyàn" en="Vocabulary Quiz" />
          </p>
          <h1 className="vocab-quiz-mode-title">
            <BiLabel zh="拿到三顆星！" pinyin="Nádào sān kē xīng!" en="Earn all three stars!" />
          </h1>
          <p className="vocab-quiz-star-count" aria-label={`${stars} of 3 stars earned`}>
            {([1, 2, 3] as const).map((tier) => (
              <span key={tier} className={stars >= tier ? "star-earned" : "star-open"}>
                {stars >= tier ? "⭐" : "☆"}
              </span>
            ))}
          </p>
          {!alreadyCompleted && !practiceUnlocked(stars) && (
            <p className="vocab-quiz-unlock-goal">
              <BiLabel
                zh="拿到 ⭐⭐ 就可以開始說話練習"
                pinyin="Nádào ⭐⭐ jiù kěyǐ kāishǐ shuōhuà liànxí"
                en="Earn ⭐⭐ to start speaking practice"
              />
            </p>
          )}
        </div>
        <div className="vocab-quiz-mode-grid" role="group" aria-label="Quiz mode">
          {TIER_CARDS.map((card) => {
            const config = TIER_CONFIGS[card.mode];
            const unlocked = isTierUnlocked(config.tier, stars);
            const earned = stars >= config.tier;
            return (
              <button
                key={card.mode}
                type="button"
                className={`vocab-quiz-mode-card vocab-quiz-mode-${card.mode}${
                  unlocked ? "" : " is-locked"
                }${earned ? " is-earned" : ""}`}
                disabled={!unlocked}
                onClick={() => startTier(card.mode)}
              >
                <span className="vocab-quiz-mode-icon">{unlocked ? card.icon : "🔒"}</span>
                <strong>
                  <BiLabel zh={card.title} pinyin={card.titlePinyin} en={card.titleEn} />
                  {earned && (
                    <span className="vocab-quiz-tier-done" aria-label="Star earned">
                      {" "}✓
                    </span>
                  )}
                </strong>
                <p>
                  {unlocked ? (
                    <BiLabel zh={card.desc} pinyin={card.descPinyin} en={card.descEn} />
                  ) : (
                    <BiLabel
                      zh={`先拿到 ${"⭐".repeat(config.tier - 1)}。`}
                      pinyin={`Xiān nádào ${"⭐".repeat(config.tier - 1)}.`}
                      en={`Earn ${"⭐".repeat(config.tier - 1)} first.`}
                    />
                  )}
                </p>
              </button>
            );
          })}
          <button
            type="button"
            className="vocab-quiz-mode-card vocab-quiz-mode-review"
            onClick={() => setScreen("review")}
          >
            <span className="vocab-quiz-mode-icon">{REVIEW_CARD.icon}</span>
            <strong>
              <BiLabel
                zh={REVIEW_CARD.title}
                pinyin={REVIEW_CARD.titlePinyin}
                en={REVIEW_CARD.titleEn}
              />
            </strong>
            <p>
              <BiLabel
                zh={REVIEW_CARD.desc}
                pinyin={REVIEW_CARD.descPinyin}
                en={REVIEW_CARD.descEn}
              />
            </p>
          </button>
          {weakEntries.length > 0 && (
            <button
              type="button"
              className="vocab-quiz-mode-card vocab-quiz-mode-weak_words"
              onClick={() => {
                setIsRetryRound(false);
                chooseMode("weak_words", weakEntries, weakEntries.length);
              }}
            >
              <span className="vocab-quiz-mode-icon">🎯</span>
              <strong>
                <BiLabel
                  zh={`弱項複習 (${weakEntries.length})`}
                  pinyin="Ruòxiàng fùxí"
                  en={`Weak words (${weakEntries.length})`}
                />
              </strong>
              <p>
                <BiLabel
                  zh="只考你上次答錯的字。"
                  pinyin="Zhǐ kǎo nǐ shàng cì dá cuò de zì."
                  en="Only quizzes the words you got wrong last time."
                />
              </p>
            </button>
          )}
        </div>
      </section>
    );
  }

  if (screen === "review") {
    return (
      <section className="story-vocab-quiz vocab-quiz-review" aria-label="Vocabulary review">
        <button
          type="button"
          className="btn-vocab-quiz-back"
          onClick={() => setScreen("mode-select")}
        >
          <BiLabel zh="← 選模式" pinyin="← Xuǎn móshì" en="← Back to modes" />
        </button>
        <div className="vocab-quiz-header">
          <p className="eyebrow">
            <BiLabel zh="複習模式" pinyin="Fùxí móshì" en="Review Mode" />
          </p>
          <h1 className="vocab-quiz-mode-title">
            <BiLabel zh="所有生詞" pinyin="Suǒyǒu shēngcí" en="All vocabulary" />
          </h1>
        </div>
        <ul className="vocab-quiz-review-list" aria-label="Vocabulary list">
          {entries.map((entry) => (
            <li className="vocab-quiz-review-item" key={entry.word}>
              <span className="vocab-quiz-review-word">{entry.word}</span>
              <span className="vocab-quiz-review-pinyin">
                {entry.pinyin || toPinyin(entry.word)}
              </span>
              <span className="vocab-quiz-review-translation">{entry.translation}</span>
            </li>
          ))}
        </ul>
      </section>
    );
  }

  if (screen === "summary") {
    const correctCount = results.filter((r) => r.correct).length;
    // Star-tier context for this summary: whether the finished run was a
    // tier run, whether it passed, and — for the near-miss nudge — how many
    // more right answers it needed. Retry-round (missed-words drill)
    // summaries stay plain.
    const tierConfig = !isRetryRound ? tierConfigFromMode(mode) : null;
    const passed = tierConfig !== null && correctCount >= tierConfig.passCount;
    const gap = tierConfig !== null ? nextStarGap(mode, correctCount)! : null;
    const nextTierCard =
      tierConfig && passed && tierConfig.tier < 3
        ? TIER_CARDS.find((c) => TIER_CONFIGS[c.mode].tier === tierConfig.tier + 1)!
        : null;
    const starIcons = "⭐".repeat(tierConfig?.tier ?? 0);
    // Practice only opens at ⭐⭐ — earned this session or a previous one
    // (stars persist locally and via attempt history). alreadyCompleted
    // covers students who unlocked practice under an older, looser rule so
    // a rule change never re-locks them.
    const showContinue = alreadyCompleted || practiceUnlocked(stars);
    return (
      <section className="story-vocab-quiz vocab-quiz-summary" aria-label="Vocabulary quiz results">
        <div className="vocab-quiz-header">
          <p className="eyebrow">
            <BiLabel
              zh={isRetryRound ? "複習結果" : "測驗結果"}
              pinyin={isRetryRound ? "Fùxí jiéguǒ" : "Cèyàn jiéguǒ"}
              en={isRetryRound ? "Review results" : "Quiz results"}
            />
          </p>
          <h1 className="vocab-quiz-mode-title">
            <BiLabel
              zh={`答對 ${correctCount} / ${results.length} 題`}
              pinyin={`Dá duì ${correctCount} / ${results.length} tí`}
              en={`${correctCount} / ${results.length} correct`}
            />
          </h1>
          {tierConfig && passed && (
            <p className="vocab-quiz-star-result is-earned">
              <BiLabel
                zh={`你拿到 ${starIcons} 了！`}
                pinyin={`Nǐ nádào ${starIcons} le!`}
                en={`You earned ${starIcons}!`}
              />
            </p>
          )}
          {tierConfig && !passed && (
            <p className="vocab-quiz-star-result is-near-miss">
              <BiLabel
                zh={`再答對 ${gap} 題就拿到 ${starIcons} 了！`}
                pinyin={`Zài dá duì ${gap} tí jiù nádào ${starIcons} le!`}
                en={`Just ${gap} more right for ${starIcons}!`}
              />
            </p>
          )}
        </div>

        {missedWords.length > 0 ? (
          <div className="vocab-quiz-missed-list" role="list" aria-label="Missed words">
            {missedEntries.map((entry) => (
              <div className="vocab-quiz-missed-item" role="listitem" key={entry.word}>
                <span className="vocab-quiz-missed-word">{entry.word}</span>
                <span className="vocab-quiz-missed-translation">{entry.translation}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="vocab-quiz-all-correct">
            <BiLabel zh="全部答對，太棒了！" pinyin="Quánbù dá duì, tài bàng le!" en="Perfect score — nice work!" />
          </p>
        )}

        <div className="vocab-quiz-actions">
          {tierConfig && !passed && (
            <button
              type="button"
              className="btn-vocab-quiz-try-again"
              onClick={() => startTier(tierConfig.mode)}
            >
              <BiLabel zh="🔁 再試一次" pinyin="🔁 Zài shì yí cì" en="🔁 Try again" />
            </button>
          )}
          {nextTierCard && (
            <button
              type="button"
              className="btn-vocab-quiz-challenge"
              onClick={() => startTier(nextTierCard.mode)}
            >
              <BiLabel
                zh={`${nextTierCard.icon} 挑戰${nextTierCard.title}`}
                pinyin={`${nextTierCard.icon} Tiǎozhàn ${nextTierCard.titlePinyin.toLowerCase()}`}
                en={`${nextTierCard.icon} Challenge ${nextTierCard.titleEn}`}
              />
            </button>
          )}
          {missedWords.length > 0 && !isRetryRound && (
            <button type="button" className="btn-vocab-quiz-retry" onClick={practiceMissedWords}>
              <BiLabel zh="🔁 練習答錯的題目" pinyin="🔁 Liànxí dá cuò de tímù" en="🔁 Practice missed words" />
            </button>
          )}
          {showContinue && (
            <button type="button" className="btn-vocab-quiz-next" onClick={onDone}>
              <BiLabel zh="繼續練習 →" pinyin="Jìxù liànxí →" en="Continue to practice →" />
            </button>
          )}
          {!showContinue && (
            <button
              type="button"
              className="btn-vocab-quiz-menu"
              onClick={() => setScreen("mode-select")}
            >
              <BiLabel zh="回選單" pinyin="Huí xuǎndān" en="Back to menu" />
            </button>
          )}
        </div>
        {!showContinue && (
          <p className="vocab-quiz-unlock-note">
            🔒{" "}
            <BiLabel
              zh="拿到 ⭐⭐ 才能開始說話練習"
              pinyin="Nádào ⭐⭐ cáinéng kāishǐ shuōhuà liànxí"
              en="Speaking practice opens at ⭐⭐"
            />
          </p>
        )}
      </section>
    );
  }

  if (!question) {
    return null;
  }

  return (
    <section className="story-vocab-quiz vocab-quiz-question-screen" aria-label="Vocabulary quiz">
      <div className="vocab-quiz-topbar">
        {onBack && (
          <button type="button" className="btn-vocab-quiz-back" onClick={onBack}>
            <BiLabel zh="← 回活動" pinyin="← Huí huódòng" en="← Back to activities" />
          </button>
        )}
        {showFinishButton && (
          <button type="button" className="btn-vocab-quiz-finish" onClick={() => finish(results)}>
            <BiLabel zh="結束，看結果" pinyin="Jiéshù, kàn jiéguǒ" en="Finish & see results" />
          </button>
        )}
      </div>
      <div className="vocab-quiz-header">
        <p className="eyebrow">
          <BiLabel
            zh={isRetryRound ? "複習答錯的題目" : "生詞測驗"}
            pinyin={isRetryRound ? "Fùxí dá cuò de tímù" : "Shēngcí cèyàn"}
            en={isRetryRound ? "Reviewing missed words" : "Vocabulary Quiz"}
          />
        </p>
        {question.kind === "translation" && (
          <p className="vocab-quiz-instruction">
            <BiLabel zh="這是什麼意思？" pinyin="Zhè shì shénme yìsi?" en="What does this word mean?" />
          </p>
        )}
        {question.kind === "cloze" && (
          <p className="vocab-quiz-instruction">
            <BiLabel zh="哪個字可以填進去？" pinyin="Nǎge zì kěyǐ tián jìnqù?" en="Which word fits the blank?" />
          </p>
        )}
        {question.kind === "pinyin" && (
          <p className="vocab-quiz-instruction">
            <BiLabel zh="這個字怎麼念？" pinyin="Zhège zì zěnme niàn?" en="How do you read this word?" />
          </p>
        )}
        {question.kind === "pos" && (
          <p className="vocab-quiz-instruction">
            <BiLabel zh="這是什麼詞類？" pinyin="Zhè shì shénme cílèi?" en="What part of speech is this?" />
          </p>
        )}
        {question.kind === "synonym" && (
          <p className="vocab-quiz-instruction">
            <BiLabel zh="哪個字意思一樣？" pinyin="Nǎge zì yìsi yíyàng?" en="Which word means the same?" />
          </p>
        )}
        {question.kind === "reverse" && (
          <p className="vocab-quiz-instruction">
            <BiLabel zh="哪個是這個意思？" pinyin="Nǎge shì zhège yìsi?" en="Which word means this?" />
          </p>
        )}
        {question.kind === "listening" && (
          <p className="vocab-quiz-instruction">
            <BiLabel zh="聽一聽，選對的字。" pinyin="Tīng yi tīng, xuǎn duì de zì." en="Listen and pick the word you hear." />
          </p>
        )}
        {question.kind === "cloze" ? (
          <h1 className="vocab-quiz-word vocab-quiz-cloze-sentence">
            {question.sentenceWithBlank.split(CLOZE_BLANK).map((part, i, parts) => (
              <span key={i}>
                {part}
                {i < parts.length - 1 && (
                  <span className="vocab-quiz-cloze-blank" aria-hidden="true">
                    {CLOZE_BLANK}
                  </span>
                )}
              </span>
            ))}
            <span className="vocab-quiz-ai-badge" title="AI-generated question" aria-label="AI-generated question">
              ✨
            </span>
          </h1>
        ) : question.kind === "reverse" ? (
          <h1 className="vocab-quiz-word vocab-quiz-reverse-prompt">{question.translation}</h1>
        ) : question.kind === "listening" ? (
          <h1 className="vocab-quiz-word vocab-quiz-listening-prompt">
            <button
              type="button"
              className="btn-vocab-quiz-play"
              aria-label="Play the word"
              onClick={() => speakWord(question.correctWord)}
            >
              🔊
            </button>
          </h1>
        ) : (
          <h1 className="vocab-quiz-word">
            {question.word}
            {question.isAiGenerated && (
              <span className="vocab-quiz-ai-badge" title="AI-generated question" aria-label="AI-generated question">
                ✨
              </span>
            )}
          </h1>
        )}
        <p className="vocab-quiz-progress">
          {questionLimit !== null ? (
            <BiLabel
              zh={`第 ${index + 1} / ${questionLimit} 題`}
              pinyin={`Dì ${index + 1} / ${questionLimit} tí`}
              en={`Question ${index + 1} of ${questionLimit}`}
            />
          ) : (
            <BiLabel zh={`第 ${index + 1} 題`} pinyin={`Dì ${index + 1} tí`} en={`Question ${index + 1}`} />
          )}
        </p>
        {timeLimitMs !== null && (
          <p
            className={`vocab-quiz-timer${timeLeftMs <= 10_000 ? " is-low" : ""}`}
            aria-label={`${Math.ceil(timeLeftMs / 1000)} seconds left`}
          >
            ⏱️ {Math.ceil(timeLeftMs / 1000)}s
          </p>
        )}
      </div>

      <div
        className={`vocab-quiz-options${
          question.kind === "pinyin" ? " vocab-quiz-options-pinyin" : ""
        }`}
        role="group"
        aria-label={
          question.kind === "translation"
            ? `What does ${question.word} mean?`
            : question.kind === "cloze"
              ? "Which word fits the blank?"
              : question.kind === "pinyin"
                ? `How do you read ${question.word}?`
                : question.kind === "pos"
                  ? `What part of speech is ${question.word}?`
                  : question.kind === "reverse"
                    ? `Which word means ${question.translation}?`
                    : question.kind === "listening"
                      ? "Which word did you hear?"
                      : `Which word means the same as ${question.word}?`
        }
      >
        {question.options.map((option) => {
          const isCorrect = option === correctAnswer(question);
          const isChosen = option === selected;
          const state = selected
            ? isCorrect
              ? "correct"
              : isChosen
                ? "incorrect"
                : "neutral"
            : "neutral";
          return (
            <button
              key={option}
              type="button"
              className={`vocab-quiz-option vocab-quiz-option-${state}`}
              onClick={() => choose(option)}
              disabled={Boolean(selected)}
              aria-label={
                state === "correct"
                  ? `${option} (correct answer)`
                  : state === "incorrect"
                    ? `${option} (your answer, incorrect)`
                    : undefined
              }
            >
              {state === "correct" && (
                <span className="vocab-quiz-option-icon" aria-hidden="true">✓ </span>
              )}
              {state === "incorrect" && (
                <span className="vocab-quiz-option-icon" aria-hidden="true">✗ </span>
              )}
              {option}
            </button>
          );
        })}
      </div>

      <div className="vocab-quiz-actions">
        {selected && (
          <button type="button" className="btn-vocab-quiz-next" onClick={next}>
            {isLast ? (
              <BiLabel zh="看結果" pinyin="Kàn jiéguǒ" en="See results" />
            ) : (
              <BiLabel zh="下一題" pinyin="Xià yì tí" en="Next question" />
            )}
          </button>
        )}
      </div>
    </section>
  );
}
