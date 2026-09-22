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
    }],
    quizApprovedSnapshot: snapshot,
  };
}

describe("storyToTopic approved question pools", () => {
  it("serves the approved snapshot for the story's single level", () => {
    const topic = storyToTopic(
      story({ easy: [entry("學", "easy")] }),
      "easy",
      "approved",
    );

    expect(topic.quizVocabularyDistractors?.[0]?.[0]).toEqual(["easy"]);
  });

  it("preserves an optional conversation contract for student runtime selection", () => {
    const conversation = [
      { id: "system-1", speaker: "system" as const, text: "你好吗？" },
      { id: "student-1", speaker: "student" as const, text: "我很好。" },
    ];
    const topic = storyToTopic({ ...story({}), conversationTurns: conversation });

    expect(topic.conversationTurns).toEqual(conversation);
  });
});
