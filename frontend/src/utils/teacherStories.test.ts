import { describe, expect, it } from "vitest";
import { storyToTopic, type CustomTeacherStory } from "./teacherStories";

describe("storyToTopic", () => {
  it("maps story-wide learning content into the shared speaking vocabulary", () => {
    const story: CustomTeacherStory = {
      id: "story-wide",
      title: "Shared content",
      frames: [
        { imageUrl: "", prompt: "Scene one", vocabulary: "" },
        { imageUrl: "", prompt: "Scene two", vocabulary: "" },
      ],
      storyVocabulary: {
        easy: {
          vocabulary: "學校, 老師",
          vocabularyPinyin: "xue2xiao4, lao3shi1",
          vocabularyPos: "N, N",
          vocabularyTranslation: "school, teacher",
        },
      },
      storyPhrases: { easy: { phrases: "在學校", phrasesTranslation: "at school" } },
    };

    const topic = storyToTopic(story);
    expect(topic.vocabulary[0]).toEqual(["學校", "老師"]);
    expect(topic.vocabularyTranslation?.[0]).toEqual(["school", "teacher"]);
    expect(topic.phrases?.[0]).toEqual(["在學校"]);
    expect(topic.vocabulary[1]).toEqual([]);
  });

  it("maps frame vocabulary metadata by scene index", () => {
    const topic = storyToTopic({
      id: "story-1",
      title: "Restaurant Story",
      frames: [{
        imageUrl: "",
        prompt: "Describe the picture.",
        vocabulary: "餐廳, 吃",
        vocabularyPinyin: "can1ting1, chi1",
        vocabularyPos: "N, V",
        vocabularyTranslation: "restaurant, to eat",
      }],
    });
    expect(topic.vocabularyPos?.[0]).toEqual(["N", "V"]);
    expect(topic.vocabularyTranslation?.[0]).toEqual(["restaurant", "to eat"]);
  });

  it("does not expose legacy frame quiz pools", () => {
    const topic = storyToTopic({
      id: "story-2",
      title: "Canonical story",
      frames: [{ imageUrl: "", prompt: "Describe", vocabulary: "餐廳" }],
    });
    expect(topic).not.toHaveProperty("vocabularyDistractors");
    expect(topic).not.toHaveProperty("vocabularyCloze");
    expect(topic).not.toHaveProperty("vocabularySynonym");
    expect(topic).not.toHaveProperty("quizVocabulary");
  });
});
