import { describe, expect, it } from "vitest";
import type { VocabPriorityReviewWord } from "../../../services/api/quiz-analytics";
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
        pLearned: 0.1, status: "NEEDS_PRACTICE", observationCount: 3,
        correctCount: 1, incorrectCount: 2,
      },
      {
        wordId: "a", word: "first locally", reviewRank: 2,
        pLearned: 0.2, status: "NEEDS_PRACTICE", observationCount: 3,
        correctCount: 1, incorrectCount: 2,
      },
    ];

    expect(entriesInServerPriorityOrder(entries, ranked)).toMatchObject([
      { wordId: "b" }, { wordId: "a" },
    ]);
  });

  it("carries the server's current corrective dimension, not a history of failed question types", () => {
    const entries = [{ word: "w", wordId: "w" }] as never[];
    const ranked = [{
      wordId: "w", word: "w", status: "NEEDS_PRACTICE", observationCount: 5,
      seenQuestionTypes: ["basic_meaning_mcq", "character_to_pinyin_typing"],
      vocabularyState: { practice: { unresolvedDimensions: ["pinyin"], nextDimension: "pinyin" } },
    }] as unknown as VocabPriorityReviewWord[];

    const [entry] = entriesInServerPriorityOrder(entries, ranked) as Array<Record<string, unknown>>;

    expect(entry.bktNextDimension).toBe("pinyin");
    expect(entry.bktSeenQuestionKinds).toEqual(["basic_meaning_mcq", "character_to_pinyin_typing"]);
    expect(entry).not.toHaveProperty("bktFailedQuestionKinds");
  });

  it("leaves the dimension unset when the server names none (nothing to repair)", () => {
    const entries = [{ word: "w", wordId: "w" }] as never[];
    const ranked = [{
      wordId: "w", word: "w", status: "NEEDS_PRACTICE", seenQuestionTypes: ["basic_meaning_mcq"],
      vocabularyState: { practice: { unresolvedDimensions: [], nextDimension: null } },
    }] as unknown as VocabPriorityReviewWord[];

    const [entry] = entriesInServerPriorityOrder(entries, ranked) as Array<Record<string, unknown>>;

    expect(entry.bktNextDimension).toBeUndefined();
  });
});
