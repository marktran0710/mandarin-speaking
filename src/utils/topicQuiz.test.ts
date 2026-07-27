import { describe, expect, it } from "vitest";
import { topicQuizEntries, type QuizSourceTopic } from "./topicQuiz";
import type { QuizExclusion } from "./quizExclusions";

function makeTopic(quizExclusions: QuizExclusion[]): QuizSourceTopic {
  return {
    images: ["scene-1.png"],
    vocabulary: { 0: ["知道", "一起"] },
    suggestedAnswers: { 0: "我知道，我們一起去。" },
    vocabularyTranslation: { 0: ["to know", "together"] },
    vocabularyDistractors: { 0: [["to see", "to hear"], ["alone", "apart"]] },
    vocabularyCloze: {
      0: [
        [
          { sentence: "我知道了。", distractors: ["不知道"] },
          { sentence: "他不知道這件事。", distractors: ["認識"] },
        ],
        [{ sentence: "我們一起去。", distractors: ["分開"] }],
      ],
    },
    vocabularySynonym: {
      0: [[{ synonym: "曉得", distractors: ["不懂"] }], []],
    },
    vocabularyLookalike: { 0: [["知到"], []] },
    // Cast: quizExclusions is read off sourceStory structurally by
    // storyQuizExclusions, so a minimal stub is enough here.
    sourceStory: { quizExclusions } as unknown as QuizSourceTopic["sourceStory"],
  };
}

describe("topicQuizEntries exclusions", () => {
  it("builds every entry when nothing is excluded", () => {
    const entries = topicQuizEntries(makeTopic([]));
    expect(entries.map((e) => e.word)).toEqual(["知道", "一起"]);
  });

  it("drops a whole word marked excluded, keeping other entries", () => {
    const entries = topicQuizEntries(
      makeTopic([{ word: "知道", kind: "word" }]),
    );
    expect(entries.map((e) => e.word)).toEqual(["一起"]);
  });

  it("removes only the marked cloze/synonym candidate for a word", () => {
    const entries = topicQuizEntries(
      makeTopic([
        { word: "知道", kind: "cloze", index: 0 },
        { word: "知道", kind: "synonym", index: 0 },
      ]),
    );
    const entry = entries.find((e) => e.word === "知道")!;
    expect(entry.aiCloze).toHaveLength(1);
    expect(entry.aiCloze?.[0].sentence).toBe("他不知道這件事。");
    expect(entry.aiSynonym ?? []).toHaveLength(0);
  });
});
