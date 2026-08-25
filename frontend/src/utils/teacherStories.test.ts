import { describe, expect, it } from "vitest";
import { storyHasTierContent, storyToTopic, type CustomTeacherStory } from "./teacherStories";

describe("storyToTopic", () => {
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

describe("storyToTopic difficulty tiers", () => {
  const tieredStory: CustomTeacherStory = {
    id: "story-3",
    title: "Tiered Story",
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
    expect(topic.quizVocabulary?.[0]).toEqual(["你好"]);
    expect(topic.quizVocabularyTranslation?.[0]).toBeUndefined();
  });

  it("falls back to Easy text when a tier hasn't been authored for that frame", () => {
    const topic = storyToTopic(tieredStory, "hard");
    expect(topic.id).toBe("teacher-story-3-hard");
    expect(topic.prompts?.[0]).toBe("你好。");
    expect(topic.vocabulary[0]).toEqual(["你好"]);
  });

  it("serves each tier's own image when authored, falling back to Easy's when not", () => {
    const storyWithTieredImages: CustomTeacherStory = {
      ...tieredStory,
      frames: [{ ...tieredStory.frames[0], imageUrlMedium: "img-0-medium.png" }],
    };

    expect(storyToTopic(storyWithTieredImages, "easy").images[0]).toBe("img-0.png");
    expect(storyToTopic(storyWithTieredImages, "medium").images[0]).toBe("img-0-medium.png");
    // No imageUrlHard authored — Hard falls back to Easy's image, not blank.
    expect(storyToTopic(storyWithTieredImages, "hard").images[0]).toBe("img-0.png");
  });

  it("storyHasTierContent reports which tiers were actually authored", () => {
    expect(storyHasTierContent(tieredStory, "medium")).toBe(true);
    expect(storyHasTierContent(tieredStory, "hard")).toBe(false);
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

  it("uses the Easy approved snapshot for Medium quiz material by canonical word", () => {
    const mediumStory: CustomTeacherStory = {
      ...story,
      frames: [{
        ...story.frames[0],
        vocabulary: "知道",
        vocabularyMedium: "知道, 一起",
        vocabularyTranslation: "to know",
        vocabularyTranslationMedium: "to know, together",
        vocabularyDistractors: JSON.stringify([["live wrong"]]),
      }],
      quizApprovedSnapshot: {
        easy: [{
          word: "知道",
          translation: "to know",
          distractors: ["to see", "to hear"],
          cloze: [],
          synonym: [],
        }],
        medium: [{
          word: "知道",
          translation: "wrong medium translation",
          distractors: ["wrong medium distractor"],
          cloze: [],
          synonym: [],
        }],
      },
    };
    const topic = storyToTopic(mediumStory, "medium", "approved");

    expect(topic.vocabulary?.[0]).toEqual(["知道", "一起"]);
    expect(topic.quizVocabulary?.[0]).toEqual(["知道"]);
    expect(topic.quizVocabularyTranslation?.[0]).toEqual(["to know"]);
    expect(topic.quizVocabularyDistractors?.[0]).toEqual([["to see", "to hear"]]);
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
