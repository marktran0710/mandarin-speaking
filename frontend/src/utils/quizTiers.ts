// The star-tier ladder for the story vocabulary quiz: each story's quiz is
// played as three progressively harder tiers (⭐ / ⭐⭐ / ⭐⭐⭐), unlocked in
// order — pass tier N's threshold once and star N is earned for good. Stars
// are *derived* from vocab_quiz_attempts history (mode = "tier1"|"tier2"|
// "tier3") rather than stored, so teacher analytics and weak-words keep
// working off the same table; the localStorage mirror below covers the
// no-database mode, following the storyLevelProgress.ts pattern.

import { getStudentScopeKey, isAdminSession } from "./studentSession";

export type QuizTier = 1 | 2 | 3;
export type TierMode = "tier1" | "tier2" | "tier3";
export type DiagnosticRoundType = "know_it" | "say_it" | "use_it";
export type DiagnosticKnowledgeDimension = "meaning" | "pinyin_production" | "contextual_recall";

export interface TierConfig {
  tier: QuizTier;
  mode: TierMode;
  /** The source lesson vocabulary determines the run length. */
  passRatio: number;
  // Total time cap for the whole run (the Speed-mode engine), or null for
  // an untimed tier.
  timeLimitMs: number | null;
}

export const TIER_CONFIGS: Record<TierMode, TierConfig> = {
  // These ratios preserve the old difficulty curve without making the quiz
  // depend on a fixed number of words.
  tier1: { tier: 1, mode: "tier1", passRatio: 0.70, timeLimitMs: null },
  tier2: { tier: 2, mode: "tier2", passRatio: 0.82, timeLimitMs: null },
  tier3: { tier: 3, mode: "tier3", passRatio: 0.88, timeLimitMs: 150_000 },
};

export interface DiagnosticRoundConfig {
  mode: TierMode;
  level: "easy" | "medium" | "hard";
  roundType: DiagnosticRoundType;
  knowledgeDimension: DiagnosticKnowledgeDimension;
  questionKind: "basic_meaning_mcq" | "character_to_pinyin_typing" | "contextual_productive_recall";
}

export const DIAGNOSTIC_ROUNDS: Record<TierMode, DiagnosticRoundConfig> = {
  tier1: { mode: "tier1", level: "easy", roundType: "know_it", knowledgeDimension: "meaning", questionKind: "basic_meaning_mcq" },
  tier2: { mode: "tier2", level: "medium", roundType: "say_it", knowledgeDimension: "pinyin_production", questionKind: "character_to_pinyin_typing" },
  tier3: { mode: "tier3", level: "hard", roundType: "use_it", knowledgeDimension: "contextual_recall", questionKind: "contextual_productive_recall" },
};

export function tierConfigFromMode(mode: string | null | undefined): TierConfig | null {
  if (mode === "tier1" || mode === "tier2" || mode === "tier3") return TIER_CONFIGS[mode];
  return null;
}

/** Preserve a tier's pass ratio when a leak-free planner has fewer distinct
 * concepts than the tier's nominal question count. */
export function effectiveTierPassCount(config: TierConfig, totalQuestions: number): number {
  if (totalQuestions <= 0) return 0;
  return Math.max(1, Math.ceil(config.passRatio * totalQuestions));
}

/** The star (tier number) a finished attempt earns, or null if it failed
 * its tier's threshold or wasn't a tier run at all. */
export function attemptEarnsStar(
  mode: string | null | undefined,
  correctCount: number,
  totalQuestions?: number,
): QuizTier | null {
  const config = tierConfigFromMode(mode);
  if (!config) return null;
  const passCount = effectiveTierPassCount(config, totalQuestions ?? 0);
  return correctCount >= passCount ? config.tier : null;
}

/** Highest contiguous star earned across an attempt history (0 = none yet).
 * A later tier is not proof of the earlier tiers: tier 3 by itself must not
 * unlock speaking practice. Attempts may arrive in any order, so we collect
 * all passed tiers first, then walk the ladder from tier 1. */
export function starsFromAttempts(
  attempts: Array<{ mode?: string | null; correctCount: number; totalQuestions?: number }>,
): 0 | QuizTier {
  const earnedTiers = new Set<QuizTier>();
  for (const attempt of attempts) {
    const earned = attemptEarnsStar(attempt.mode, attempt.correctCount, attempt.totalQuestions);
    if (earned !== null) earnedTiers.add(earned);
  }
  let stars: 0 | QuizTier = 0;
  for (const tier of [1, 2, 3] as const) {
    if (!earnedTiers.has(tier)) break;
    stars = tier;
  }
  return stars;
}

/** Per-story stars across a mixed attempt history (every story that appears
 * gets an entry, 0 included) — powers the teacher star board and the story
 * list's earned-star badges. */
export function starsByStory(
  attempts: Array<{
    storyId: string;
    mode?: string | null;
    correctCount: number;
    totalQuestions?: number;
  }>,
): Record<string, 0 | QuizTier> {
  const attemptsByStory: Record<string, Array<{ mode?: string | null; correctCount: number; totalQuestions?: number }>> = {};
  for (const attempt of attempts) {
    (attemptsByStory[attempt.storyId] ??= []).push(attempt);
  }
  const byStory: Record<string, 0 | QuizTier> = {};
  for (const [storyId, storyAttempts] of Object.entries(attemptsByStory)) {
    byStory[storyId] = starsFromAttempts(storyAttempts);
  }
  return byStory;
}

/** Tier 1 is always open; each later tier opens once the previous star is
 * earned. */
export function isTierUnlocked(tier: QuizTier, stars: number): boolean {
  if (isAdminSession()) return true;
  return stars >= tier - 1;
}

// Speaking practice opens only after the complete ⭐ / ⭐⭐ / ⭐⭐⭐ ladder.
// Tier 1 and Tier 2 prepare the learner; Tier 3 confirms the vocabulary
// check is fully complete before the story's speaking work becomes available.
export const PRACTICE_UNLOCK_STARS = 3;

/** Whether this many stars opens the story's speaking practice. */
export function practiceUnlocked(stars: number): boolean {
  if (isAdminSession()) return true;
  return stars >= PRACTICE_UNLOCK_STARS;
}

/** How many more correct answers this run needed to pass its tier — 0 means
 * it passed, null means the run wasn't a tier run. Drives the near-miss
 * message on the summary screen ("just 2 more right answers for ⭐⭐!"). */
export function nextStarGap(
  mode: string | null | undefined,
  correctCount: number,
  totalQuestions?: number,
): number | null {
  const config = tierConfigFromMode(mode);
  if (!config) return null;
  const passCount = effectiveTierPassCount(config, totalQuestions ?? 0);
  return Math.max(0, passCount - correctCount);
}

// ── localStorage mirror ────────────────────────────────────────────────
// Same per-browser map pattern as storyLevelProgress.ts — the source of
// truth when the backend/database is unavailable, and a fast first paint
// before the attempts fetch resolves when it is. Keyed per student so a
// shared classroom device can't leak one student's stars into the next.

const QUIZ_STARS_KEY = "vocabQuizStars";

type StarProgress = Record<string, number>;

function loadStarProgress(): StarProgress {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(`${QUIZ_STARS_KEY}:${getStudentScopeKey()}`);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function loadLocalStars(storyId: string): 0 | QuizTier {
  const stars = loadStarProgress()[storyId];
  return stars === 1 || stars === 2 || stars === 3 ? stars : 0;
}

// Medium/Hard sessions run the same 3-star ladder under tier-suffixed quiz
// ids, so a story's stars are the BEST earned across its text tiers — never
// the sum, which would triple-count one ladder.
const TIER_SUFFIXES = ["", "-medium", "-hard"];

/** Best stars this browser has recorded for a story, across its Easy /
 * Medium / Hard text tiers. `baseTopicId` is the Easy topic id (the one the
 * story picker lists). */
export function loadBestLocalStars(baseTopicId: string): 0 | QuizTier {
  return TIER_SUFFIXES.reduce<0 | QuizTier>((best, suffix) => {
    const stars = loadLocalStars(`${baseTopicId}${suffix}`);
    return stars > best ? stars : best;
  }, 0);
}

/** Records `stars` for `storyId`, keeping the best ever earned — earning a
 * lower star again never demotes the story. */
export function recordLocalStars(storyId: string, stars: QuizTier) {
  if (typeof window === "undefined") return;
  if (stars <= loadLocalStars(storyId)) return;
  const next = { ...loadStarProgress(), [storyId]: stars };
  try {
    window.localStorage.setItem(`${QUIZ_STARS_KEY}:${getStudentScopeKey()}`, JSON.stringify(next));
  } catch {
    /* storage unavailable — stars just won't persist on this device */
  }
}
