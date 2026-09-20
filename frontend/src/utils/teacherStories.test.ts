import { describe, expect, it } from "vitest";
import { storyToTopic, type CustomTeacherStory } from "./teacherStories";

describe("storyToTopic", () => {
  it("maps story-wide learning content into the shared quiz pool", () => {
    const story: CustomTeacherStory = {
      id: "story-wide",
      title: "Shared content",
      frames: [
        { imageUrl: "", prompt: "一", vocabulary: "" },
        { imageUrl: "", prompt: "二", vocabulary: "" },
      ],
      storyVocabulary: {
        easy: {
          vocabulary: "學校, 老師",
          vocabularyPinyin: "xuéxiào, lǎoshī",
          vocabularyPos: "N, N",
          vocabularyTranslation: "school, teacher",
        },
      },
      storyPhrases: {
        easy: { phrases: "在學校", phrasesTranslation: "at school" },
      },
    };

    const topic = storyToTopic(story);
    expect(topic.quizVocabulary?.[0]).toEqual(["學校", "老師"]);
    expect(topic.quizVocabularyTranslation?.[0]).toEqual(["school", "teacher"]);
    expect(topic.phrases?.[0]).toEqual(["在學校"]);
    expect(topic.quizVocabulary?.[1]).toEqual([]);
  });

  it("maps vocabularyPos and vocabularyTranslation onto the topic, keyed by frame index", () => {
    const story: CustomTeacherStory = {
      id: "story-1",
      title: "Restaurant Story",
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
      frames: [
        { imageUrl: "", prompt: "Describe the picture.", vocabulary: "餐廳" },
      ],
    };

    const topic = storyToTopic(story);

    expect(topic.vocabularyPos).toBeUndefined();
    expect(topic.vocabularyTranslation).toBeUndefined();
  });
});

describe("storyToTopic single level", () => {
  const singleStory: CustomTeacherStory = {
    id: "story-3",
    title: "Single-level Story",
    frames: [
      {
        imageUrl: "img-0.png",
        prompt: "你好。",
        vocabulary: "你好",
        suggestedAnswer: "你好嗎？",
      },
    ],
  };

  it("maps the base fields and keeps the story's original id", () => {
    const topic = storyToTopic(singleStory);
    expect(topic.id).toBe("teacher-story-3");
    expect(topic.prompts?.[0]).toBe("你好。");
    expect(topic.vocabulary[0]).toEqual(["你好"]);
    expect(topic.images[0]).toBe("img-0.png");
  });
});

describe("storyToTopic serving mode", () => {
  const story: CustomTeacherStory = {
    id: "story-4",
    title: "Approval Gated Story",
    frames: [
      {
        imageUrl: "",
        prompt: "p",
        vocabulary: "知道",
        vocabularyTranslation: "to know",
        // Live/working material — grown in the background, never reviewed.
        vocabularyDistractors: JSON.stringify([["unreviewed guess"]]),
      },
    ],
  };

  it("'live' (default) reads the current per-word fields, unreviewed or not", () => {
    const topic = storyToTopic(story);
    expect(topic.vocabularyDistractors?.[0]?.[0]).toEqual(["unreviewed guess"]);
  });

  it("'approved' ignores live fields entirely when nothing has been approved yet", () => {
    const topic = storyToTopic(story, "easy", "approved");
    expect(topic.vocabularyDistractors).toBeUndefined();
  });

  it("'approved' serves only the teacher-approved snapshot, by word", () => {
    const approvedStory: CustomTeacherStory = {
      ...story,
      quizApprovedSnapshot: {
        easy: [
          {
            word: "知道",
            translation: "to know",
            distractors: ["to see", "to hear", "to say"],
            cloze: [],
            synonym: [],
          },
        ],
      },
    };
    const topic = storyToTopic(approvedStory, "easy", "approved");
    expect(topic.vocabularyDistractors?.[0]?.[0]).toEqual(["to see", "to hear", "to say"]);
  });

  it("'approved' never leaks live material for a word missing from the snapshot", () => {
    const twoWordStory: CustomTeacherStory = {
      ...story,
      frames: [
        {
          ...story.frames[0],
          vocabulary: "知道, 一起",
          vocabularyTranslation: "to know, together",
          vocabularyDistractors: JSON.stringify([["unreviewed guess"], ["also unreviewed"]]),
        },
      ],
      quizApprovedSnapshot: {
        easy: [
          {
            word: "知道",
            translation: "to know",
            distractors: ["to see", "to hear", "to say"],
            cloze: [],
            synonym: [],
          },
        ],
      },
    };
    const topic = storyToTopic(twoWordStory, "easy", "approved");
    expect(topic.vocabularyDistractors?.[0]?.[0]).toEqual(["to see", "to hear", "to say"]);
    expect(topic.vocabularyDistractors?.[0]?.[1]).toEqual([]);
  });
});
