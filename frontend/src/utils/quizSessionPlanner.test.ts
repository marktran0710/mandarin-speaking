import { afterEach, describe, expect, it, vi } from "vitest";
import {
  auditQuizSession,
  planQuizSession,
  quizQuestionAnswer,
  quizQuestionExposure,
  visibleTextContainsAnswer,
} from "./quizSessionPlanner";
import {
  buildQuizQuestion,
  type VocabQuizEntry,
  type VocabQuizQuestion,
} from "../components/story-vocab-quiz/StoryVocabQuiz";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("auditQuizSession", () => {
  it("detects a previous option that reveals a later answer", () => {
    const questions: VocabQuizQuestion[] = [
      {
        kind: "translation",
        word: "狗",
        correctTranslation: "dog",
        options: ["dog", "cat", "book", "school"],
        isAiGenerated: false,
      },
      {
        kind: "translation",
        word: "貓",
        correctTranslation: "cat",
        options: ["cat", "water", "house", "teacher"],
        isAiGenerated: false,
      },
    ];

    expect(auditQuizSession(questions)).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          rule: "forward-answer-leak",
          questionIndex: 0,
          relatedQuestionIndex: 1,
        }),
      ]),
    );
  });

  it("detects repeated concepts even when the question kind changes", () => {
    const questions: VocabQuizQuestion[] = [
      {
        kind: "translation",
        word: "朋友",
        correctTranslation: "friend",
        options: ["friend", "house"],
        isAiGenerated: false,
      },
      {
        kind: "pinyin",
        word: "朋友",
        correctPinyin: "péng you",
        options: ["péng you", "pèng you"],
        isAiGenerated: false,
      },
    ];

    expect(auditQuizSession(questions)).toEqual(
      expect.arrayContaining([expect.objectContaining({ rule: "duplicate-concept" })]),
    );
  });
});

describe("planQuizSession", () => {
  const entries: VocabQuizEntry[] = [
    { word: "朋友", translation: "friend", pinyin: "péng you" },
    { word: "家", translation: "home", pinyin: "jiā" },
    { word: "書", translation: "book", pinyin: "shū" },
    { word: "水", translation: "water", pinyin: "shuǐ" },
  ];

  it("builds a full session with unique concepts and no forward answer leaks", () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    const plan = planQuizSession(entries, "tier1", entries.length, (entry, mode, context) =>
      buildQuizQuestion(entry, entries, mode, context),
    );

    expect(plan.questions).toHaveLength(entries.length);
    expect(plan.reducedCount).toBe(0);
    expect(auditQuizSession(plan.questions)).toEqual([]);
    expect(new Set(plan.questions.map((question) => question.word)).size).toBe(entries.length);

    for (let later = 1; later < plan.questions.length; later += 1) {
      const answer = quizQuestionAnswer(plan.questions[later]);
      for (let earlier = 0; earlier < later; earlier += 1) {
        expect(
          quizQuestionExposure(plan.questions[earlier]).some((visible) =>
            visibleTextContainsAnswer(visible, answer),
          ),
        ).toBe(false);
      }
    }
  });

  it("reduces the session instead of repeating concepts when the pool is too small", () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    const plan = planQuizSession(entries.slice(0, 2), "tier1", 20, (entry, mode, context) =>
      buildQuizQuestion(entry, entries.slice(0, 2), mode, context),
    );

    expect(plan.questions).toHaveLength(2);
    expect(plan.reducedCount).toBe(18);
    expect(auditQuizSession(plan.questions)).toEqual([]);
  });

  it("collapses different words that share the same answer concept", () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    const shared: VocabQuizEntry[] = [
      { word: "快樂", translation: "happy" },
      { word: "高興", translation: "happy" },
      { word: "難過", translation: "sad" },
    ];
    const plan = planQuizSession(shared, "tier1", 3, (entry, mode, context) =>
      buildQuizQuestion(entry, shared, mode, context),
    );

    expect(plan.questions).toHaveLength(2);
    expect(plan.questions.filter((question) => question.word === "快樂" || question.word === "高興"))
      .toHaveLength(1);
  });
});
