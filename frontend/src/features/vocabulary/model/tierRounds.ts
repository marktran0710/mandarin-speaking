import { nextStarGap, type TierMode } from "@entities/vocabulary";
import type { VocabQuizQuestionResult } from "@entities/vocabulary";

export const TIER_SEQUENCE: TierMode[] = ["tier1", "tier2", "tier3"];
export const ROUND_LABEL: Record<TierMode, string> = { tier1: "Know It", tier2: "Say It", tier3: "Use It" };

export interface RoundResult {
  tier: TierMode;
  correctCount: number;
  totalQuestions: number;
  passed: boolean;
  /** How many more correct answers this tier's threshold needed — 0 when
   * `passed` is true, for the "2 more correct for ⭐⭐" near-miss message. */
  starGap: number | null;
}

/**
 * Shapes one finished tier's raw quiz results into what the round-result
 * screen displays. `passed` is decided by the caller (from useQuizSession's
 * own post-attempt `stars`, which already ran attemptEarnsStar) — this
 * function never re-derives pass/fail itself, only the score/near-miss
 * numbers around it.
 */
export function computeRoundResult(
  tierIndex: number,
  results: VocabQuizQuestionResult[],
  passed: boolean,
): RoundResult {
  const tier = TIER_SEQUENCE[tierIndex];
  const correctCount = results.filter((result) => result.correct).length;
  const totalQuestions = results.length;
  return {
    tier,
    correctCount,
    totalQuestions,
    passed,
    starGap: nextStarGap(tier, correctCount, totalQuestions),
  };
}
