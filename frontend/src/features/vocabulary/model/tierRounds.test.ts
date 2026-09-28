import { describe, expect, it } from "vitest";
import type { VocabQuizQuestionResult } from "@entities/vocabulary";
import { computeRoundResult, TIER_SEQUENCE } from "./tierRounds";

function result(word: string, correct: boolean, extra: Partial<VocabQuizQuestionResult> = {}): VocabQuizQuestionResult {
  return { word, correct, timeMs: 1000, ...extra };
}

describe("computeRoundResult", () => {
  it("scores the round 0–100 from first-try answers, with no pass/fail", () => {
    const round = computeRoundResult(0, [
      result("你好", true),
      result("謝謝", false),
      result("再見", true),
      result("朋友", false),
    ]);
    expect(round.tier).toBe(TIER_SEQUENCE[0]);
    expect(round.correctCount).toBe(2);
    expect(round.totalQuestions).toBe(4);
    expect(round.score).toBe(50);
  });

  it("lists every word missed on the first try for review — including ones fixed on the hinted retry", () => {
    const round = computeRoundResult(1, [
      result("你好", true),
      result("謝謝", false, { hintUsed: true, retryCorrect: true }),
      result("再見", false, { hintUsed: true, retryCorrect: false }),
    ]);
    expect(round.tier).toBe(TIER_SEQUENCE[1]);
    // The retry never changes the score.
    expect(round.score).toBe(33);
    expect(round.reviewWords).toEqual(["謝謝", "再見"]);
  });

  it("de-duplicates review words and handles a perfect round", () => {
    expect(computeRoundResult(2, [result("書", false), result("書", false)]).reviewWords).toEqual(["書"]);
    const perfect = computeRoundResult(2, [result("書", true)]);
    expect(perfect.score).toBe(100);
    expect(perfect.reviewWords).toEqual([]);
  });
});
