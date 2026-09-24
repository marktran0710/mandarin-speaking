import { describe, expect, it } from "vitest";
import { storyToTopic } from "./mappers";
import type { CustomTeacherStory } from "./types";

const story: CustomTeacherStory = {
  id: "verified-story",
  title: "Verified story",
  frames: [{
    imageUrl: "scene.png",
    prompt: "Describe the scene.",
    vocabulary: "學習",
    vocabularyTranslation: "to learn",
  }],
  vocabAssessment: [{
    questionId: "learn-easy",
    wordId: "learn-1",
    targetWord: "學習",
    pinyin: "xuéxí",
    pos: "V",
    simpleEnglishMeaning: "to learn",
    level: "easy",
    difficultyWeight: 1,
    questionType: "basic_meaning_mcq",
    answerFormat: "single_choice",
    prompt: "What does 學習 mean?",
    options: ["to learn", "to eat"],
    correctAnswer: "to learn",
    acceptedAnswers: ["to learn"],
    explanation: "",
  }],
};

describe("storyToTopic canonical mapping", () => {
  it("passes vocab_assessment through without frame-pool compatibility fields", () => {
    const topic = storyToTopic(story);
    expect(topic.vocabAssessment).toEqual(story.vocabAssessment);
    expect(topic.vocabularyTranslation?.[0]).toEqual(["to learn"]);
    expect(topic).not.toHaveProperty("quizVocabulary");
    expect(topic).not.toHaveProperty("vocabularyDistractors");
  });

  it("preserves the conversation contract for student runtime selection", () => {
    const conversation = [
      { id: "system-1", speaker: "system" as const, text: "Listen." },
      { id: "student-1", speaker: "student" as const, text: "學習" },
    ];
    expect(storyToTopic({ ...story, conversationTurns: conversation }).conversationTurns).toEqual(conversation);
  });
});
