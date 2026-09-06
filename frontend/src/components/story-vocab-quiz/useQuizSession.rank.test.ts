import { describe, expect, it } from "vitest";
import type { VocabPriorityReviewWord } from "../../services/api/quiz-analytics";
import { entriesInServerPriorityOrder } from "./useQuizSession";

describe("entriesInServerPriorityOrder", () => {
  it("keeps the server Bottom-K order instead of the local vocabulary order", () => {
    const entries = [
      { word: "first locally", wordId: "a" },
      { word: "second locally", wordId: "b" },
    ] as never[];
    const ranked: VocabPriorityReviewWord[] = [
      {
        wordId: "b", word: "second locally", reviewRank: 1,
        pLearned: 0.1, status: "NEEDS_REVIEW", observationCount: 3,
        correctCount: 1, incorrectCount: 2,
      },
      {
        wordId: "a", word: "first locally", reviewRank: 2,
        pLearned: 0.2, status: "NEEDS_REVIEW", observationCount: 3,
        correctCount: 1, incorrectCount: 2,
      },
    ];

    expect(entriesInServerPriorityOrder(entries, ranked)).toMatchObject([
      { wordId: "b" }, { wordId: "a" },
    ]);
  });
});
