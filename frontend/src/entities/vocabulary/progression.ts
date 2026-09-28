// The round ladder for the story vocabulary quiz: each story's quiz is
// played as three progressively harder rounds (Know It / Say It / Use It),
// unlocked in order — finish round N once and "star" N is earned for good.
// There is no accuracy threshold: finishing a round is what counts, and the
// round's score (0–100) is reported alongside, never used as a gate. Stars
// are *derived* from vocab_quiz_attempts history (mode = "tier1"|"tier2"|
// "tier3") rather than stored, so teacher analytics and weak-words keep
// working off the same table; the localStorage mirror below covers the
// no-database mode, following the storyLevelProgress.ts pattern.

import { getCachedResearchContext } from "../../utils/researchContext";
import { getStudentScopeKey, isAdminSession } from "../../utils/studentSession";
import { topicHasQuiz, type QuizSourceTopic } from "./model";

export type QuizTier = 1 | 2 | 3;
export type TierMode = "tier1" | "tier2" | "tier3";
export type DiagnosticKnowledgeDimension = "meaning" | "pinyin_production" | "contextual_recall";

export interface TierConfig {
  tier: QuizTier;
  mode: TierMode;
  // Total time cap for the whole run (the Speed-mode engine), or null for
  // an untimed tier.
  timeLimitMs: number | null;
}

export const TIER_CONFIGS: Record<TierMode, TierConfig> = {
  tier1: { tier: 1, mode: "tier1", timeLimitMs: null },
  tier2: { tier: 2, mode: "tier2", timeLimitMs: null },
  tier3: { tier: 3, mode: "tier3", timeLimitMs: 150_000 },
};

export interface DiagnosticRoundConfig {
  mode: TierMode;
  // The external quiz bank's difficulty label for this round's question — used
  // only to look up the round's bank question (the bank is owned by the quiz
  // pipeline and keeps these labels). The round dimension itself is `mode`
  // (tier1/2/3); the stored quiz_level uses that round key, not this label.
  round: QuizTier;
  knowledgeDimension: DiagnosticKnowledgeDimension;
  questionKind: "basic_meaning_mcq" | "character_to_pinyin_typing" | "context_cloze_mcq";
}

// Round 3 ("use it") is a multiple-choice context cloze, not free-text hanzi
// typing — most students have no Chinese IME, so a bare text input made the
// round practically unplayable. bankLevel stays "hard" so the round still
// grades against that level's published correctAnswer/acceptedAnswers; the
// MCQ options are built separately (see buildDiagnosticRoundQuestions).
export const DIAGNOSTIC_ROUNDS: Record<TierMode, DiagnosticRoundConfig> = {
  tier1: { mode: "tier1", round: 1, knowledgeDimension: "meaning", questionKind: "basic_meaning_mcq" },
  tier2: { mode: "tier2", round: 2, knowledgeDimension: "pinyin_production", questionKind: "character_to_pinyin_typing" },
  tier3: { mode: "tier3", round: 3, knowledgeDimension: "contextual_recall", questionKind: "context_cloze_mcq" },
};

export function tierConfigFromMode(mode: string | null | undefined): TierConfig | null {
  if (mode === "tier1" || mode === "tier2" || mode === "tier3") return TIER_CONFIGS[mode];
  return null;
}

/** The time limit that actually applies to a tier right now (Epic 3, Task
 * 3.7): production uses the tier's configured limit (only tier3 has one);
 * an active research participant never gets a timer, so speed pressure
 * cannot become an uncontrolled confound in round completion. */
export function effectiveTimeLimitMs(mode: string | null | undefined): number | null {
  if (getCachedResearchContext().coreCompletionPolicy === "research_coverage") return null;
  return tierConfigFromMode(mode)?.timeLimitMs ?? null;
}

/** A round's score on a 0–100 scale: the share of questions answered
 * correctly on the first try (a hinted retry never changes it). */
export function roundScore(correctCount: number, totalQuestions: number): number {
  if (totalQuestions <= 0) return 0;
  return Math.round((100 * Math.max(0, Math.min(correctCount, totalQuestions))) / totalQuestions);
}

/** The star (round number) a finished attempt earns, or null if it wasn't a
 * finished tier run at all. Finishing the round is the only requirement —
 * the score is shown to the learner but does not gate the next round or the
 * speaking practice (the same rule research participants always had). This
 * is the single point where star derivation is decided — every caller
 * (starsFromAttempts below, TopicSelector, StudentSidebar, MyStoriesPage,
 * the quiz session itself) inherits it. */
export function attemptEarnsStar(
  mode: string | null | undefined,
  _correctCount: number,
  totalQuestions?: number,
): QuizTier | null {
  const config = tierConfigFromMode(mode);
  if (!config) return null;
  // Only ever called with a finished round's totals, so a positive
  // totalQuestions is the completion signal.
  return (totalQuestions ?? 0) > 0 ? config.tier : null;
}

/** The most recent score (0–100) of each round, from an attempt history in
 * any order. Rounds never finished are absent. */
export function latestRoundScores(
  attempts: Array<{ mode?: string | null; correctCount: number; totalQuestions?: number; completedAt?: string }>,
): Partial<Record<TierMode, number>> {
  const latest: Partial<Record<TierMode, { at: string; score: number }>> = {};
  for (const attempt of attempts) {
    const config = tierConfigFromMode(attempt.mode);
    if (!config || !(attempt.totalQuestions && attempt.totalQuestions > 0)) continue;
    const at = attempt.completedAt ?? "";
    const current = latest[config.mode];
    if (!current || at >= current.at) {
      latest[config.mode] = { at, score: roundScore(attempt.correctCount, attempt.totalQuestions) };
    }
  }
  return Object.fromEntries(Object.entries(latest).map(([mode, entry]) => [mode, entry!.score])) as Partial<Record<TierMode, number>>;
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

/** Replace the offline mirror with the server's current result, including
 * demotion after quiz evidence is reset or deleted. */
export function syncLocalStars(storyId: string, stars: 0 | QuizTier) {
  if (typeof window === "undefined") return;
  const next = { ...loadStarProgress(), [storyId]: stars };
  try {
    window.localStorage.setItem(`${QUIZ_STARS_KEY}:${getStudentScopeKey()}`, JSON.stringify(next));
  } catch {
    /* storage unavailable */
  }
}

export interface QuizStarsSummary {
  quizStars: number;
  maxQuizStars: number;
}

/** Sidebar Stars widget total: sum of best-ever stars across every story
 * that actually runs a quiz (stories with no glossed vocabulary have no
 * quiz and so contribute no stars either way). Reads localStorage directly
 * on every call — deliberately not memoizable on `topics`, since stars
 * change via quiz completion writes that never touch the topics list. */
export function computeQuizStarsSummary(topics: (QuizSourceTopic & { id: string })[]): QuizStarsSummary {
  const quizStoryTopics = topics.filter((topic) => topicHasQuiz(topic));
  const quizStars = quizStoryTopics.reduce((sum, topic) => sum + loadLocalStars((topic as { sourceStory?: { id?: string } }).sourceStory?.id ?? topic.id), 0);
  return { quizStars, maxQuizStars: quizStoryTopics.length * 3 };
}
