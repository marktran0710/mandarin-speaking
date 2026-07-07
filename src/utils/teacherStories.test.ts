import { describe, expect, it } from "vitest";
import { storyToTopic, type CustomTeacherStory } from "./teacherStories";

describe("storyToTopic", () => {
  it("maps vocabularyPos and vocabularyTranslation onto the topic, keyed by frame index", () => {
    const story: CustomTeacherStory = {
      id: "story-1",
      title: "Restaurant Story",
      learningGoal: "Order food",
      level: "Beginner",
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
      level: "Beginner",
      frames: [
        { imageUrl: "", prompt: "Describe the picture.", vocabulary: "餐廳" },
      ],
    };

    const topic = storyToTopic(story);

    expect(topic.vocabularyPos).toBeUndefined();
    expect(topic.vocabularyTranslation).toBeUndefined();
  });
});
