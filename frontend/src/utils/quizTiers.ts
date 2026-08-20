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

export interface TierConfig {
  tier: QuizTier;
  mode: TierMode;
  questionCount: number;
  // Minimum correct answers for the run to pass and earn this tier's star.
  passCount: number;
  // Total time cap for the whole run (the Speed-mode engine), or null for
  // an untimed tier.
  timeLimitMs: number | null;
}

export const TIER_CONFIGS: Record<TierMode, TierConfig> = {
  tier1: { tier: 1, mode: "tier1", questionCount: 20, passCount: 14, timeLimitMs: null },
  tier2: { tier: 2, mode: "tier2", questionCount: 22, passCount: 18, timeLimitMs: null },
  tier3: { tier: 3, mode: "tier3", questionCount: 25, passCount: 22, timeLimitMs: 150_000 },
};

export function tierConfigFromMode(mode: string | null | undefined): TierConfig | null {
  if (mode === "tier1" || mode === "tier2" || mode === "tier3") return TIER_CONFIGS[mode];
  return null;
}

/** Preserve a tier's pass ratio when a leak-free planner has fewer distinct
 * concepts than the tier's nominal question count. */
export function effectiveTierPassCount(config: TierConfig, totalQuestions: number): number {
  if (totalQuestions >= config.questionCount) return config.passCount;
  if (totalQuestions <= 0) return config.passCount;
  return Math.max(1, Math.ceil((config.passCount / config.questionCount) * totalQuestions));
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
  const passCount = effectiveTierPassCount(config, totalQuestions ?? config.questionCount);
  return correctCount >= passCount ? config.tier : null;
}

/** Highest star earned across an attempt history (0 = none yet). */
export function starsFromAttempts(
  attempts: Array<{ mode?: string | null; correctCount: number; totalQuestions?: number }>,
): 0 | QuizTier {
  let stars: 0 | QuizTier = 0;
  for (const attempt of attempts) {
    const earned = attemptEarnsStar(attempt.mode, attempt.correctCount, attempt.totalQuestions);
    if (earned !== null && earned > stars) stars = earned;
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
  const byStory: Record<string, 0 | QuizTier> = {};
  for (const attempt of attempts) {
    const earned = attemptEarnsStar(attempt.mode, attempt.correctCount, attempt.totalQuestions);
    const current = byStory[attempt.storyId] ?? 0;
    byStory[attempt.storyId] = earned !== null && earned > current ? earned : current;
  }
  return byStory;
}

/** Tier 1 is always open; each later tier opens once the previous star is
 * earned. */
export function isTierUnlocked(tier: QuizTier, stars: number): boolean {
  if (isAdminSession()) return true;
  return stars >= tier - 1;
}

// Speaking practice unlocks at ⭐⭐, not ⭐: tier 1 is the warm-up, tier 2's
// pass is the gate into the story, and tier 3 stays an optional challenge.
export const PRACTICE_UNLOCK_STARS = 2;

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
  const passCount = effectiveTierPassCount(config, totalQuestions ?? config.questionCount);
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
