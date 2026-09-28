import { roundScore, type TierMode } from "@entities/vocabulary";
import type { VocabQuizQuestionResult } from "@entities/vocabulary";

export const TIER_SEQUENCE: TierMode[] = ["tier1", "tier2", "tier3"];
export const ROUND_LABEL: Record<TierMode, string> = { tier1: "Know It", tier2: "Say It", tier3: "Use It" };

export interface RoundResult {
  tier: TierMode;
  correctCount: number;
  totalQuestions: number;
  /** 0–100: first-try correct answers over all questions. */
  score: number;
  /** Words missed on the first try (hanzi only, in question order, unique) —
   * the round's review list. A word fixed on the hinted retry still lands
   * here, since the retry never counts as knowing it. */
  reviewWords: string[];
}

/**
 * Shapes one finished round's raw quiz results into what the round-result
 * screen displays. There is no pass/fail: finishing the round is what
 * unlocks the next one, and the score is reported for the learner only.
 */
export function computeRoundResult(
  tierIndex: number,
  results: VocabQuizQuestionResult[],
): RoundResult {
  const tier = TIER_SEQUENCE[tierIndex];
  const correctCount = results.filter((result) => result.correct).length;
  const totalQuestions = results.length;
  const reviewWords = [...new Set(results.filter((result) => !result.correct).map((result) => result.word))];
  return {
    tier,
    correctCount,
    totalQuestions,
    score: roundScore(correctCount, totalQuestions),
    reviewWords,
  };
}
