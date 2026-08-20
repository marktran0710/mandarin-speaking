import { describe, expect, it } from "vitest";
import { protectGeneratedQuizMaterial } from "./quizGenerationGate";

const vocabulary = [
  { word: "知道", translation: "to know" },
  { word: "一起", translation: "together" },
  { word: "今天", translation: "today" },
];

describe("protectGeneratedQuizMaterial", () => {
  it("removes duplicate values and answers belonging to another target", () => {
    const protectedBatch = protectGeneratedQuizMaterial(vocabulary, {
      distractors: [
        { word: "知道", distractors: ["together", "to see", "To see", "today"] },
      ],
      cloze: [],
      synonym: [],
    });

    expect(protectedBatch.distractors).toEqual([
      { word: "知道", distractors: ["to see"] },
    ]);
    expect(protectedBatch.removedCount).toBe(3);
  });

  it("drops a cloze prompt that reveals another vocabulary answer", () => {
    const protectedBatch = protectGeneratedQuizMaterial(vocabulary, {
      distractors: [],
      cloze: [
        {
          word: "知道",
          sentence: "我知道他今天很忙。",
          distractors: ["認為", "明白", "了解"],
        },
      ],
      synonym: [],
    });

    expect(protectedBatch.cloze).toEqual([]);
    expect(protectedBatch.removedCount).toBe(1);
  });

  it("checks the cloze prompt after blanking the target word", () => {
    const protectedBatch = protectGeneratedQuizMaterial(
      [
        { word: "他", translation: "he" },
        { word: "他們", translation: "they" },
      ],
      {
        distractors: [],
        cloze: [
          { word: "他們", sentence: "他們很忙。", distractors: ["我們"] },
        ],
        synonym: [],
      },
    );

    expect(protectedBatch.cloze).toHaveLength(1);
  });

  it("keeps one unique synonym answer and removes it from other option pools", () => {
    const protectedBatch = protectGeneratedQuizMaterial(vocabulary, {
      distractors: [],
      cloze: [],
      synonym: [
        { word: "知道", synonym: "曉得", distractors: ["今天", "忘記", "忘記"] },
        { word: "一起", synonym: "曉得", distractors: ["分開"] },
      ],
    });

    expect(protectedBatch.synonym).toEqual([
      { word: "知道", synonym: "曉得", distractors: ["忘記"] },
    ]);
    expect(protectedBatch.removedCount).toBe(3);
  });
});
