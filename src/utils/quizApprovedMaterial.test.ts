import { describe, expect, it } from "vitest";
import {
  buildApprovedMaterial,
  buildApprovedMaterialFromApprovals,
  storyApprovedSnapshot,
  storyQuizNeedsReview,
  type ApprovedMaterialEntry,
} from "./quizApprovedMaterial";
import type { QuizSourceTopic } from "./topicQuiz";
import type { QuizApprovalMark } from "./quizPendingApprovals";

function topic(): QuizSourceTopic {
  return {
    images: ["s0.png", "s1.png"],
    vocabulary: { 0: ["知道", "一起"], 1: ["知道"] }, // 知道 repeats in scene 1
    vocabularyTranslation: { 0: ["to know", "together"], 1: ["to know (dup)"] },
    vocabularyDistractors: { 0: [["to see", "to hear"], ["alone"]], 1: [["duplicate-scene-data"]] },
    vocabularyCloze: {
      0: [[{ sentence: "我知道了。", distractors: ["不知道"] }], []],
      1: [[{ sentence: "他不知道這件事。", distractors: ["認識"] }]],
    },
    vocabularySynonym: { 0: [[{ synonym: "曉得", distractors: ["不懂"] }], []], 1: [[]] },
    vocabularyLookalike: { 0: [["知到"], []], 1: [["duplicate-lookalike"]] },
  };
}

describe("buildApprovedMaterial", () => {
  it("builds one entry per distinct word, first scene occurrence wins", () => {
    const entries = buildApprovedMaterial(topic(), []);
    expect(entries.map((e) => e.word)).toEqual(["知道", "一起"]);
    const zhidao = entries.find((e) => e.word === "知道")!;
    expect(zhidao.distractors).toEqual(["to see", "to hear"]);
    expect(zhidao.translation).toBe("to know");
  });

  it("strips a whole excluded word from the output entirely", () => {
    const entries = buildApprovedMaterial(topic(), [{ word: "一起", kind: "word" }]);
    expect(entries.map((e) => e.word)).toEqual(["知道"]);
  });

  it("strips only the excluded pool item, keeping the rest of the word", () => {
    const entries = buildApprovedMaterial(topic(), [
      { word: "知道", kind: "cloze", index: 0 },
    ]);
    const zhidao = entries.find((e) => e.word === "知道")!;
    expect(zhidao.cloze).toEqual([]);
    expect(zhidao.distractors).toEqual(["to see", "to hear"]);
  });

  it("includes lookalike pools alongside the other AI pools", () => {
    const entries = buildApprovedMaterial(topic(), []);
    expect(entries.find((e) => e.word === "知道")!.lookalike).toEqual(["知到"]);
  });
});

describe("published wrong-option cap", () => {
  it("keeps only the three wrong options that validation can verify", () => {
    const draft = topic();
    draft.vocabularyDistractors![0][0] = ["one", "two", "three", "unreviewed fourth"];
    draft.vocabularyCloze![0][0][0].distractors = ["a", "b", "c", "unreviewed fourth"];
    draft.vocabularySynonym![0][0][0].distractors = ["x", "y", "z", "unreviewed fourth"];

    const entry = buildApprovedMaterial(draft, [])[0];
    expect(entry.distractors).toEqual(["one", "two", "three"]);
    expect(entry.cloze[0].distractors).toEqual(["a", "b", "c"]);
    expect(entry.synonym[0].distractors).toEqual(["x", "y", "z"]);
  });
});

describe("storyApprovedSnapshot", () => {
  it("returns null when the tier has never been approved", () => {
    expect(storyApprovedSnapshot({}, "easy")).toBeNull();
    expect(storyApprovedSnapshot({ quizApprovedSnapshot: { medium: [] } }, "easy")).toBeNull();
  });

  it("returns the stored entries for an approved tier, including an empty approved list", () => {
    expect(storyApprovedSnapshot({ quizApprovedSnapshot: { easy: [] } }, "easy")).toEqual([]);
    const entries = [{ word: "知道", distractors: [], cloze: [], synonym: [], lookalike: [] }];
    expect(storyApprovedSnapshot({ quizApprovedSnapshot: { easy: entries } }, "easy")).toEqual(entries);
  });
});

describe("buildApprovedMaterialFromApprovals", () => {
  it("publishes only checked candidates, dropping everything unchecked", () => {
    const approvals: QuizApprovalMark[] = [
      { word: "知道", kind: "distractors" },
      { word: "知道", kind: "cloze", index: 0 },
      // synonym #0 left unchecked on purpose.
    ];
    const entries = buildApprovedMaterialFromApprovals(topic(), approvals, []);
    const zhidao = entries.find((e) => e.word === "知道")!;
    expect(zhidao.distractors).toEqual(["to see", "to hear"]);
    expect(zhidao.cloze).toHaveLength(1);
    expect(zhidao.synonym).toEqual([]);
  });

  it("a word with nothing checked at all still gets an entry, just empty", () => {
    const entries = buildApprovedMaterialFromApprovals(topic(), [], []);
    const zhidao = entries.find((e) => e.word === "知道")!;
    expect(zhidao.distractors).toEqual([]);
    expect(zhidao.cloze).toEqual([]);
    expect(zhidao.synonym).toEqual([]);
  });

  it("a whole-word exclusion still drops the entry entirely, checkboxes aside", () => {
    const entries = buildApprovedMaterialFromApprovals(
      topic(),
      [{ word: "一起", kind: "distractors" }],
      [{ word: "一起", kind: "word" }],
    );
    expect(entries.map((e) => e.word)).toEqual(["知道"]);
  });

  it("lookalike still follows the exclude/trash toggle, not a checkbox", () => {
    const withLookalike = buildApprovedMaterialFromApprovals(topic(), [], []);
    expect(withLookalike.find((e) => e.word === "知道")!.lookalike).toEqual(["知到"]);

    const excluded = buildApprovedMaterialFromApprovals(topic(), [], [
      { word: "知道", kind: "lookalike" },
    ]);
    expect(excluded.find((e) => e.word === "知道")!.lookalike).toEqual([]);
  });
});

describe("storyQuizNeedsReview", () => {
  const withAi: ApprovedMaterialEntry[] = [
    { word: "知道", translation: "to know", distractors: ["a", "b", "c"], cloze: [], synonym: [], lookalike: [] },
  ];
  const noAi: ApprovedMaterialEntry[] = [
    { word: "知道", translation: "to know", distractors: [], cloze: [], synonym: [], lookalike: [] },
  ];

  it("false when the story has no AI material at all — nothing to review", () => {
    expect(storyQuizNeedsReview({}, noAi, "easy")).toBe(false);
    expect(storyQuizNeedsReview({ quizApprovedSnapshot: {} }, [], "easy")).toBe(false);
  });

  it("true when AI material exists but the tier has never been approved", () => {
    expect(storyQuizNeedsReview({}, withAi, "easy")).toBe(true);
  });

  it("false when live material exactly matches what's approved", () => {
    expect(
      storyQuizNeedsReview({ quizApprovedSnapshot: { easy: withAi } }, withAi, "easy"),
    ).toBe(false);
  });

  it("true when live material has drifted from what's approved", () => {
    const changed = [{ ...withAi[0], distractors: ["a", "b", "d"] }];
    expect(
      storyQuizNeedsReview({ quizApprovedSnapshot: { easy: withAi } }, changed, "easy"),
    ).toBe(true);
  });
});
