import { describe, expect, it } from "vitest";
import {
  applyExclusionsToWord,
  isExcluded,
  toggleExclusion,
  type QuizExclusion,
} from "./quizExclusions";

const material = {
  translation: "to know",
  aiDistractors: ["to see", "to hear"],
  pinyin: "zhīdào",
  aiCloze: [
    { sentence: "我____了。", distractors: ["不知道"] },
    { sentence: "我____一家咖啡廳。", distractors: ["認識"] },
  ],
  aiSynonyms: [{ synonym: "曉得", distractors: ["不懂"] }],
};

describe("quizExclusions", () => {
  it("toggle adds then removes the same mark", () => {
    const mark: QuizExclusion = { word: "知道", kind: "cloze", index: 0 };
    const added = toggleExclusion([], mark);
    expect(isExcluded(added, "知道", "cloze", 0)).toBe(true);
    expect(isExcluded(added, "知道", "cloze", 1)).toBe(false);
    expect(toggleExclusion(added, mark)).toEqual([]);
  });

  it("an index-less mark covers the whole pool", () => {
    const list: QuizExclusion[] = [{ word: "知道", kind: "cloze" }];
    expect(isExcluded(list, "知道", "cloze", 0)).toBe(true);
    expect(isExcluded(list, "知道", "cloze", 5)).toBe(true);
  });

  it("word-level exclusion drops the entry entirely", () => {
    expect(
      applyExclusionsToWord("知道", material, [
        { word: "知道", kind: "word" },
      ]),
    ).toBeNull();
  });

  it("cloze/synonym exclusions remove only the marked candidate", () => {
    const next = applyExclusionsToWord("知道", material, [
      { word: "知道", kind: "cloze", index: 0 },
      { word: "知道", kind: "synonym", index: 0 },
    ])!;
    expect(next.aiCloze).toEqual([material.aiCloze[1]]);
    expect(next.aiSynonyms).toEqual([]);
    // Untouched pools survive.
    expect(next.aiDistractors).toEqual(material.aiDistractors);
  });

  it("distractor exclusions empty their pool", () => {
    const next = applyExclusionsToWord("知道", material, [
      { word: "知道", kind: "distractors" },
    ])!;
    expect(next.aiDistractors).toEqual([]);
    expect(next.aiCloze).toHaveLength(2);
  });

  it("marks for other words never leak", () => {
    const next = applyExclusionsToWord("知道", material, [
      { word: "一起", kind: "word" },
      { word: "一起", kind: "cloze", index: 0 },
    ])!;
    expect(next).toEqual(material);
  });
});
