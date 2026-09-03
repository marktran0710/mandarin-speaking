import { describe, expect, it } from "vitest";
import { storyToTopic } from "./mappers";
import type { CustomTeacherStory } from "./types";

const entry = (word: string, distractor: string) => ({
  word,
  translation: "to learn",
  distractors: [distractor],
  cloze: [],
  synonym: [],
});

function story(snapshot: Record<string, unknown>): CustomTeacherStory {
  return {
    id: "verified-story",
    title: "Verified story",
    frames: [{
      imageUrl: "scene.png",
      prompt: "Describe the scene.",
      vocabulary: "學",
      vocabularyTranslation: "to learn",
      suggestedAnswer: "我學中文。",
      vocabularyMedium: "學",
      vocabularyTranslationMedium: "to learn",
      suggestedAnswerMedium: "我學中文。",
      vocabularyHard: "學",
      vocabularyTranslationHard: "to learn",
      suggestedAnswerHard: "我學中文。",
    }],
    quizApprovedSnapshot: snapshot,
  };
}

describe("storyToTopic approved question pools", () => {
  it("serves a tier snapshot when it stays on the canonical Easy vocabulary", () => {
    const topic = storyToTopic(
      story({ easy: [entry("學", "easy")], medium: [entry("學", "medium")] }),
      "medium",
      "approved",
    );

    expect(topic.quizVocabularyDistractors?.[0]?.[0]).toEqual(["medium"]);
  });

  it("falls back to Easy material when a tier introduces different words", () => {
    const topic = storyToTopic(
      story({ easy: [entry("學", "easy")], medium: [entry("不同", "medium")] }),
      "medium",
      "approved",
    );

    expect(topic.quizVocabularyDistractors?.[0]?.[0]).toEqual(["easy"]);
  });
});
