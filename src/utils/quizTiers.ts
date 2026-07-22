// The star-tier ladder for the story vocabulary quiz: each story's quiz is
// played as three progressively harder tiers (⭐ / ⭐⭐ / ⭐⭐⭐), unlocked in
// order — pass tier N's threshold once and star N is earned for good. Stars
// are *derived* from vocab_quiz_attempts history (mode = "tier1"|"tier2"|
// "tier3") rather than stored, so teacher analytics and weak-words keep
// working off the same table; the localStorage mirror below covers the
// no-database mode, following the storyLevelProgress.ts pattern.

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

/** The star (tier number) a finished attempt earns, or null if it failed
 * its tier's threshold or wasn't a tier run at all. */
export function attemptEarnsStar(
  mode: string | null | undefined,
  correctCount: number,
): QuizTier | null {
  const config = tierConfigFromMode(mode);
  if (!config) return null;
  return correctCount >= config.passCount ? config.tier : null;
}

/** Highest star earned across an attempt history (0 = none yet). */
export function starsFromAttempts(
  attempts: Array<{ mode?: string | null; correctCount: number }>,
): 0 | QuizTier {
  let stars: 0 | QuizTier = 0;
  for (const attempt of attempts) {
    const earned = attemptEarnsStar(attempt.mode, attempt.correctCount);
    if (earned !== null && earned > stars) stars = earned;
  }
  return stars;
}

/** Tier 1 is always open; each later tier opens once the previous star is
 * earned. */
export function isTierUnlocked(tier: QuizTier, stars: number): boolean {
  return stars >= tier - 1;
}

// Speaking practice unlocks at ⭐⭐, not ⭐: tier 1 is the warm-up, tier 2's
// pass is the gate into the story, and tier 3 stays an optional challenge.
export const PRACTICE_UNLOCK_STARS = 2;

/** Whether this many stars opens the story's speaking practice. */
export function practiceUnlocked(stars: number): boolean {
  return stars >= PRACTICE_UNLOCK_STARS;
}

/** How many more correct answers this run needed to pass its tier — 0 means
 * it passed, null means the run wasn't a tier run. Drives the near-miss
 * message on the summary screen ("just 2 more right answers for ⭐⭐!"). */
export function nextStarGap(
  mode: string | null | undefined,
  correctCount: number,
): number | null {
  const config = tierConfigFromMode(mode);
  if (!config) return null;
  return Math.max(0, config.passCount - correctCount);
}

// ── localStorage mirror ────────────────────────────────────────────────
// Same flat per-browser map pattern as storyLevelProgress.ts — the source
// of truth when the backend/database is unavailable, and a fast first paint
// before the attempts fetch resolves when it is.

const QUIZ_STARS_KEY = "vocabQuizStars";

type StarProgress = Record<string, number>;

function loadStarProgress(): StarProgress {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(QUIZ_STARS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function loadLocalStars(storyId: string): 0 | QuizTier {
  const stars = loadStarProgress()[storyId];
  return stars === 1 || stars === 2 || stars === 3 ? stars : 0;
}

/** Records `stars` for `storyId`, keeping the best ever earned — earning a
 * lower star again never demotes the story. */
export function recordLocalStars(storyId: string, stars: QuizTier) {
  if (typeof window === "undefined") return;
  if (stars <= loadLocalStars(storyId)) return;
  const next = { ...loadStarProgress(), [storyId]: stars };
  try {
    window.localStorage.setItem(QUIZ_STARS_KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable — stars just won't persist on this device */
  }
}
