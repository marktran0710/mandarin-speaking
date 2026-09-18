import { describe, expect, it } from "vitest";
import { samplePlacementTestQuestions } from "./placementTestSampling";
import type { StoredCustomStory } from "../services/database";
import type { VocabAssessmentQuestion } from "../components/story-vocab-quiz/model";

function easyQuestion(overrides: Partial<VocabAssessmentQuestion>): VocabAssessmentQuestion {
  return {
    questionId: "Q1_EASY",
    wordId: "W1",
    targetWord: "你好",
    pinyin: "nǐ hǎo",
    pos: "phrase",
    simpleEnglishMeaning: "hello",
    level: "easy",
    difficultyWeight: 1,
    questionType: "basic_meaning_mcq",
    answerFormat: "single_choice",
    prompt: "Choose the correct English meaning of 「你好」.",
    options: ["hello", "goodbye", "thanks", "sorry"],
    correctAnswer: "hello",
    acceptedAnswers: ["hello"],
    explanation: "Correct answer: hello.",
    ...overrides,
  };
}

function story(overrides: Partial<StoredCustomStory>): StoredCustomStory {
  return {
    id: "story-1",
    title: "Lesson 1",
    frames: [],
    published: true,
    lessonNumber: 1,
    ...overrides,
  };
}

describe("samplePlacementTestQuestions", () => {
  it("samples up to wordsPerLesson easy-level questions per published story", () => {
    const words = ["你好", "謝謝", "老師", "學生", "朋友"].map((word, i) =>
      easyQuestion({ questionId: `Q${i}_EASY`, wordId: `W${i}`, targetWord: word }),
    );
    const stories = [story({ id: "s1", vocabAssessment: words })];

    const questions = samplePlacementTestQuestions(stories, 3);

    expect(questions).toHaveLength(3);
    expect(questions.every((q) => q.storyId === "s1")).toBe(true);
  });

  it("takes every easy question when a lesson has fewer than wordsPerLesson", () => {
    const words = [easyQuestion({ questionId: "Q0_EASY", wordId: "W0" })];
    const stories = [story({ id: "s1", vocabAssessment: words })];

    const questions = samplePlacementTestQuestions(stories, 5);

    expect(questions).toHaveLength(1);
  });

  it("only samples easy-level (know-it) questions, not medium/hard rounds", () => {
    const words = [
      easyQuestion({ questionId: "Q0_EASY", wordId: "W0", level: "easy" }),
      easyQuestion({ questionId: "Q0_MEDIUM", wordId: "W0", level: "medium", questionType: "character_to_pinyin_typing" }),
      easyQuestion({ questionId: "Q0_HARD", wordId: "W0", level: "hard", questionType: "context_cloze_mcq" }),
    ];
    const stories = [story({ id: "s1", vocabAssessment: words })];

    const questions = samplePlacementTestQuestions(stories, 5);

    expect(questions).toHaveLength(1);
    expect(questions[0].itemId).toBe("Q0_EASY");
  });

  it("skips unpublished stories and stories with no vocabAssessment", () => {
    const stories = [
      story({ id: "s1", published: false, vocabAssessment: [easyQuestion({})] }),
      story({ id: "s2", published: true, vocabAssessment: undefined }),
      story({ id: "s3", published: true, vocabAssessment: [] }),
    ];

    expect(samplePlacementTestQuestions(stories, 3)).toHaveLength(0);
  });

  it("samples across every published lesson, not just the first", () => {
    const stories = [
      story({ id: "s1", lessonNumber: 1, vocabAssessment: [easyQuestion({ questionId: "A", wordId: "WA" })] }),
      story({ id: "s2", lessonNumber: 2, vocabAssessment: [easyQuestion({ questionId: "B", wordId: "WB" })] }),
    ];

    const questions = samplePlacementTestQuestions(stories, 3);

    expect(questions.map((q) => q.storyId).sort()).toEqual(["s1", "s2"]);
  });

  it("carries the exact fields a placement submission needs (itemId, storyId, options, correctAnswer)", () => {
    const stories = [story({ id: "s1", vocabAssessment: [easyQuestion({ questionId: "Q0_EASY", wordId: "W0", targetWord: "你好", correctAnswer: "hello", options: ["hello", "bye"] })] })];

    const [question] = samplePlacementTestQuestions(stories, 1);

    expect(question).toMatchObject({
      storyId: "s1",
      wordId: "W0",
      targetWord: "你好",
      itemId: "Q0_EASY",
      correctAnswer: "hello",
      options: ["hello", "bye"],
      level: "easy",
    });
  });
});
