import { describe, expect, it } from "vitest";
import {
  buildMaterialSnapshot,
  diffWord,
  storyMaterialSnapshot,
  withUpdatedSnapshot,
  type MaterialSnapshot,
  type QuizMaterialTopic,
} from "./quizMaterialDiff";

const topic: QuizMaterialTopic = {
  images: ["a", "b"],
  vocabulary: { 0: ["喝", "茶"], 1: ["錢包"] },
  vocabularyTranslation: { 0: ["to drink", "tea"], 1: ["wallet"] },
  vocabularyDistractors: { 0: [["吃", "看"], ["水"]], 1: [["包包"]] },
  vocabularyCloze: {
    0: [
      [{ sentence: "我____茶。", distractors: ["吃"] }],
      [],
    ],
    1: [[]],
  },
  vocabularySynonym: {
    0: [[{ synonym: "飲", distractors: ["食"] }], []],
    1: [[]],
  },
};

describe("buildMaterialSnapshot", () => {
  it("flattens every scene's words into one array", () => {
    const snapshot = buildMaterialSnapshot(topic);
    expect(snapshot.map((e) => e.word)).toEqual(["喝", "茶", "錢包"]);
    expect(snapshot[0]).toEqual({
      word: "喝",
      translation: "to drink",
      distractors: ["吃", "看"],
      cloze: [{ sentence: "我____茶。", distractors: ["吃"] }],
      synonym: [{ synonym: "飲", distractors: ["食"] }],
    });
  });
});

describe("diffWord", () => {
  const snapshot: MaterialSnapshot = buildMaterialSnapshot(topic);

  it("returns null when there is no snapshot yet", () => {
    expect(
      diffWord("喝", { distractors: ["吃"], cloze: [], synonym: [] }, null),
    ).toBeNull();
  });

  it("flags a word absent from the snapshot as new, all pools new", () => {
    const diff = diffWord(
      "新詞",
      {
        distractors: ["x"],
        cloze: [{ sentence: "s", distractors: ["y"] }],
        synonym: [{ synonym: "z", distractors: ["w"] }],
      },
      snapshot,
    )!;
    expect(diff.status).toBe("new");
    expect(diff.distractorsStatus).toBe("new");
    expect(diff.clozeStatus).toEqual(["new"]);
    expect(diff.synonymStatus).toEqual(["new"]);
  });

  it("identical material is kept, regardless of distractor order", () => {
    const diff = diffWord(
      "喝",
      {
        distractors: ["看", "吃"], // reordered
        cloze: [{ sentence: "我____茶。", distractors: ["吃"] }],
        synonym: [{ synonym: "飲", distractors: ["食"] }],
      },
      snapshot,
    )!;
    expect(diff.status).toBe("kept");
    expect(diff.distractorsStatus).toBe("kept");
    expect(diff.clozeStatus).toEqual(["kept"]);
    expect(diff.synonymStatus).toEqual(["kept"]);
  });

  it("changed distractor set marks the pool (and word) changed", () => {
    const diff = diffWord(
      "喝",
      {
        distractors: ["吃", "喝水"], // different set
        cloze: [{ sentence: "我____茶。", distractors: ["吃"] }],
        synonym: [{ synonym: "飲", distractors: ["食"] }],
      },
      snapshot,
    )!;
    expect(diff.status).toBe("changed");
    expect(diff.distractorsStatus).toBe("changed");
    expect(diff.clozeStatus).toEqual(["kept"]);
  });

  it("a reordered cloze array (same sentences) still matches by content", () => {
    const diff = diffWord(
      "喝",
      {
        distractors: ["吃", "看"],
        cloze: [
          { sentence: "新句子", distractors: ["a"] },
          { sentence: "我____茶。", distractors: ["吃"] },
        ],
        synonym: [{ synonym: "飲", distractors: ["食"] }],
      },
      snapshot,
    )!;
    // The known sentence is kept, the unseen one is new — order doesn't
    // matter, only content identity.
    expect(diff.clozeStatus).toEqual(["new", "kept"]);
    expect(diff.status).toBe("changed"); // because one cloze item is new
  });

  it("a cloze sentence whose distractors changed is flagged changed, not new", () => {
    const diff = diffWord(
      "喝",
      {
        distractors: ["吃", "看"],
        cloze: [{ sentence: "我____茶。", distractors: ["不同"] }],
        synonym: [{ synonym: "飲", distractors: ["食"] }],
      },
      snapshot,
    )!;
    expect(diff.clozeStatus).toEqual(["changed"]);
  });
});

describe("storyMaterialSnapshot / withUpdatedSnapshot", () => {
  const snapshot: MaterialSnapshot = buildMaterialSnapshot(topic);

  it("returns null for a tier that was never saved", () => {
    const story = { quizMaterialSnapshot: { easy: snapshot } };
    expect(storyMaterialSnapshot(story, "medium")).toBeNull();
    expect(storyMaterialSnapshot(story, "easy")).toEqual(snapshot);
  });

  it("a story with no snapshot at all returns null for every tier", () => {
    expect(storyMaterialSnapshot({}, "easy")).toBeNull();
  });

  it("withUpdatedSnapshot replaces only the given tier, keeping others", () => {
    const story = { quizMaterialSnapshot: { easy: snapshot, medium: [] } };
    const updated = withUpdatedSnapshot(story, "hard", snapshot);
    expect(updated).toEqual({ easy: snapshot, medium: [], hard: snapshot });
  });
});
