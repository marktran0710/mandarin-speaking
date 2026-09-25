import { describe, expect, it } from "vitest";
import type { VocabQuizQuestionResult } from "../../../components/story-vocab-quiz/model";
import { computeRoundResult, TIER_SEQUENCE } from "./tierRounds";

function result(correct: boolean): VocabQuizQuestionResult {
  return { word: "詞", correct, timeMs: 1000 };
}

function results(correctCount: number, total: number): VocabQuizQuestionResult[] {
  return [
    ...Array.from({ length: correctCount }, () => result(true)),
    ...Array.from({ length: total - correctCount }, () => result(false)),
  ];
}

describe("computeRoundResult", () => {
  it("resolves the tier and counts from tierIndex + results, tier1 (0.70 ratio, 20 questions)", () => {
    const round = computeRoundResult(0, results(14, 20), true);
    expect(round.tier).toBe(TIER_SEQUENCE[0]);
    expect(round.correctCount).toBe(14);
    expect(round.totalQuestions).toBe(20);
    expect(round.passed).toBe(true);
    expect(round.starGap).toBe(0);
  });

  it("reports a near-miss gap when a tier2 attempt falls short (0.82 ratio, 20 questions)", () => {
    const round = computeRoundResult(1, results(16, 20), false);
    expect(round.tier).toBe(TIER_SEQUENCE[1]);
    expect(round.passed).toBe(false);
    // ceil(0.82 * 20) = 17 needed; got 16 -> 1 more correct answer needed.
    expect(round.starGap).toBe(1);
  });

  it("reports zero gap for a tier3 attempt that clears its higher 0.88 threshold", () => {
    const round = computeRoundResult(2, results(18, 20), true);
    expect(round.tier).toBe(TIER_SEQUENCE[2]);
    expect(round.passed).toBe(true);
    expect(round.starGap).toBe(0);
  });

  it("never re-derives passed itself — it trusts whatever the caller passed in", () => {
    // A caller could (incorrectly) claim `passed: true` for a below-threshold
    // score; this function must not silently correct that, since pass/fail
    // is owned by useQuizSession/attemptEarnsStar, not here.
    const round = computeRoundResult(0, results(1, 20), true);
    expect(round.passed).toBe(true);
    expect(round.starGap).toBeGreaterThan(0);
  });
});
