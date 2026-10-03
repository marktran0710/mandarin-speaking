import { describe, expect, it } from "vitest";
import type { VocabQuizEntry } from "@entities/vocabulary";
import { entriesInServerPriorityOrder } from "./useQuizSession";

type PriorityReviewSnapshot = Parameters<typeof entriesInServerPriorityOrder>[1][number];

function makeEntry(word: string, wordId: string): VocabQuizEntry {
  return { word, translation: word, wordId };
}

describe("entriesInServerPriorityOrder", () => {
  it("keeps the server Bottom-K order instead of the local vocabulary order", () => {
    const entries = [makeEntry("first locally", "a"), makeEntry("second locally", "b")];
    const ranked: PriorityReviewSnapshot[] = [
      { wordId: "b", word: "second locally" },
      { wordId: "a", word: "first locally" },
    ];

    expect(entriesInServerPriorityOrder(entries, ranked)).toMatchObject([
      { wordId: "b" }, { wordId: "a" },
    ]);
  });

  it("carries the server's current corrective dimension, not a history of failed question types", () => {
    const entries = [makeEntry("w", "w")];
    const ranked: PriorityReviewSnapshot[] = [{
      wordId: "w", word: "w", observationCount: 5,
      seenQuestionTypes: ["basic_meaning_mcq", "character_to_pinyin_typing"],
      vocabularyState: { practice: { nextDimension: "pinyin" } },
    }];

    const [entry] = entriesInServerPriorityOrder(entries, ranked);

    expect(entry.bktNextDimension).toBe("pinyin");
    expect(entry.bktSeenQuestionKinds).toEqual(["basic_meaning_mcq", "character_to_pinyin_typing"]);
    expect(entry).not.toHaveProperty("bktFailedQuestionKinds");
  });

  it("leaves the dimension unset when the server names none (nothing to repair)", () => {
    const entries = [makeEntry("w", "w")];
    const ranked: PriorityReviewSnapshot[] = [{
      wordId: "w", word: "w", seenQuestionTypes: ["basic_meaning_mcq"],
      vocabularyState: { practice: { nextDimension: null } },
    }];

    const [entry] = entriesInServerPriorityOrder(entries, ranked);

    expect(entry.bktNextDimension).toBeUndefined();
  });
});
