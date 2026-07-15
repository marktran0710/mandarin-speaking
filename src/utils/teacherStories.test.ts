import { describe, expect, it } from "vitest";
import { storyHasTierContent, storyToTopic, type CustomTeacherStory } from "./teacherStories";

describe("storyToTopic", () => {
  it("maps vocabularyPos and vocabularyTranslation onto the topic, keyed by frame index", () => {
    const story: CustomTeacherStory = {
      id: "story-1",
      title: "Restaurant Story",
      learningGoal: "Order food",
      frames: [
        {
          imageUrl: "",
          prompt: "Describe the picture.",
          vocabulary: "餐廳, 吃",
          vocabularyPinyin: "cāntīng, chī",
          vocabularyPos: "N, V",
          vocabularyTranslation: "restaurant, to eat",
        },
      ],
    };

    const topic = storyToTopic(story);

    expect(topic.vocabularyPos?.[0]).toEqual(["N", "V"]);
    expect(topic.vocabularyTranslation?.[0]).toEqual(["restaurant", "to eat"]);
  });

  it("omits vocabularyPos/vocabularyTranslation when the frame has none", () => {
    const story: CustomTeacherStory = {
      id: "story-2",
      title: "No POS Story",
      learningGoal: "Goal",
      frames: [
        { imageUrl: "", prompt: "Describe the picture.", vocabulary: "餐廳" },
      ],
    };

    const topic = storyToTopic(story);

    expect(topic.vocabularyPos).toBeUndefined();
    expect(topic.vocabularyTranslation).toBeUndefined();
  });
});

describe("storyToTopic difficulty tiers", () => {
  const tieredStory: CustomTeacherStory = {
    id: "story-3",
    title: "Tiered Story",
    learningGoal: "Practice tiers",
    frames: [
      {
        imageUrl: "img-0.png",
        prompt: "你好。",
        vocabulary: "你好",
        suggestedAnswer: "你好嗎？",
        promptMedium: "你今天好嗎？",
        vocabularyMedium: "你好, 今天",
        suggestedAnswerMedium: "我今天很好。",
        // No Hard tier authored for this frame yet.
      },
    ],
  };

  it("uses the Easy fields by default and keeps the story's original id", () => {
    const topic = storyToTopic(tieredStory);
    expect(topic.id).toBe("teacher-story-3");
    expect(topic.prompts?.[0]).toBe("你好。");
    expect(topic.vocabulary[0]).toEqual(["你好"]);
  });

  it("reads Medium fields and suffixes the topic id when authored", () => {
    const topic = storyToTopic(tieredStory, "medium");
    expect(topic.id).toBe("teacher-story-3-medium");
    expect(topic.prompts?.[0]).toBe("你今天好嗎？");
    expect(topic.vocabulary[0]).toEqual(["你好", "今天"]);
    expect(topic.suggestedAnswers?.[0]).toBe("我今天很好。");
  });

  it("falls back to Easy text when a tier hasn't been authored for that frame", () => {
    const topic = storyToTopic(tieredStory, "hard");
    expect(topic.id).toBe("teacher-story-3-hard");
    expect(topic.prompts?.[0]).toBe("你好。");
    expect(topic.vocabulary[0]).toEqual(["你好"]);
  });

  it("storyHasTierContent reports which tiers were actually authored", () => {
    expect(storyHasTierContent(tieredStory, "medium")).toBe(true);
    expect(storyHasTierContent(tieredStory, "hard")).toBe(false);
  });
});
