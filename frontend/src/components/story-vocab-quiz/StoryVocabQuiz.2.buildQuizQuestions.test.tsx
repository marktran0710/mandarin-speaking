import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StoryVocabQuiz, {
  buildQuizQuestions,
  collectQuizEntries,
  quizConceptId,
  quizItemId,
  type VocabQuizSummary,
} from "./StoryVocabQuiz";
import * as database from "../../services/database";

vi.mock("../../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/database")>();
  return {
    ...actual,
    canUseDatabase: vi.fn(() => true),
    getVocabQuizWeakWords: vi.fn(async () => []),
    listVocabQuizAttempts: vi.fn(async () => []),
  };
});

// The question-kind picker rolls Math.random() against a weighted list of
// whichever kinds are available for the entry (translation and pinyin are
// always available; cloze/pos/synonym only when the entry has that data —
// see pickQuestionKind in StoryVocabQuiz.tsx). Mocking Math.random() to 0
// always lands on the first-checked kind, translation (weight > 0, checked
// first) — every test in this file defaults to that below, since most were
// written before pinyin/cloze/pos/synonym existed and assume translation
// questions throughout; individual tests override the mock to exercise a
// specific other kind. Mocking it close to 1 always lands on the
// last-available kind — convenient when an entry gives exactly one "extra"
// kind of data, making that the last (and therefore selected) kind.
const FORCE_TRANSLATION = 0;
const FORCE_LAST_AVAILABLE_KIND = 0.999;

beforeEach(() => {
  vi.spyOn(Math, "random").mockReturnValue(FORCE_TRANSLATION);
});

afterEach(() => {
  vi.restoreAllMocks();
});

function optionButtons() {
  return screen
    .getAllByRole("button")
    .filter((b) => b.className.includes("vocab-quiz-option"));
}

/** Answers the currently-shown question, picking a definitely-correct or
 * definitely-wrong option by comparing each rendered option's text against
 * the word's known correct translation — needed since Strikes/Speed have no
 * manual "Finish" button, so tests drive them to a deterministic end (3
 * wrong in a row, or a fixed question count) instead. */
async function answerCurrentQuestion(
  user: ReturnType<typeof userEvent.setup>,
  correct: boolean,
  translationByWord: Record<string, string>,
) {
  const word = screen.getByRole("heading").textContent!;
  const correctTranslation = translationByWord[word];
  const buttons = optionButtons();
  const target = correct
    ? buttons.find((b) => b.textContent === correctTranslation)
    : buttons.find((b) => b.textContent !== correctTranslation);
  await user.click(target!);
}

describe("buildQuizQuestions", () => {
  const entries = [
    { word: "餐廳", translation: "restaurant" },
    { word: "吃", translation: "to eat" },
    { word: "喝", translation: "to drink" },
    { word: "茶", translation: "tea" },
    { word: "水", translation: "water" },
  ];

  it("builds one question per entry, each with the correct translation among its options", () => {
    const questions = buildQuizQuestions(entries);

    expect(questions).toHaveLength(entries.length);
    for (const question of questions) {
      expect(question.options).toContain(question.correctTranslation);
      expect(new Set(question.options).size).toBe(question.options.length);
    }
  });

  it("caps options at 4 per question when there are enough distractors", () => {
    const questions = buildQuizQuestions(entries);
    for (const question of questions) {
      expect(question.options.length).toBe(4);
    }
  });

  it("caps the quiz at 8 questions even with more vocabulary than that", () => {
    const manyEntries = Array.from({ length: 12 }, (_, i) => ({
      word: `word${i}`,
      translation: `meaning${i}`,
    }));

    const questions = buildQuizQuestions(manyEntries);
    expect(questions).toHaveLength(8);
  });

  it("pads with generic filler distractors when the story doesn't have enough of its own translated words", () => {
    const twoEntries = [
      { word: "餐廳", translation: "restaurant" },
      { word: "吃", translation: "to eat" },
    ];

    const questions = buildQuizQuestions(twoEntries);
    expect(questions).toHaveLength(2);
    for (const question of questions) {
      // Still a real 4-option question, not a giveaway with only 2 choices.
      expect(question.options.length).toBe(4);
      expect(question.options).toContain(question.correctTranslation);
      expect(new Set(question.options).size).toBe(4);
    }
  });

  it("still produces a real multiple-choice question from a single translated word", () => {
    const oneEntry = [{ word: "餐廳", translation: "restaurant" }];

    const questions = buildQuizQuestions(oneEntry);
    expect(questions).toHaveLength(1);
    expect(questions[0].options.length).toBe(4);
    expect(questions[0].options).toContain("restaurant");
  });

  it("returns no questions for an empty entry list", () => {
    expect(buildQuizQuestions([])).toEqual([]);
  });

  it("prefers AI-generated distractors over the story's other words and generic filler", () => {
    const entriesWithAi = [
      {
        word: "餐廳",
        translation: "restaurant",
        aiDistractors: ["kitchen", "hotel", "cafeteria"],
      },
      { word: "吃", translation: "to eat" },
      { word: "喝", translation: "to drink" },
    ];

    const questions = buildQuizQuestions(entriesWithAi);
    const question = questions.find((q) => q.word === "餐廳")!;

    expect(question.options).toContain("restaurant");
    // All 3 non-correct options come from the AI list, not "to eat"/"to
    // drink" (the real-word pool) or the generic filler list.
    const wrongOptions = question.options.filter((o) => o !== "restaurant");
    expect(wrongOptions).toHaveLength(3);
    for (const option of wrongOptions) {
      expect(["kitchen", "hotel", "cafeteria"]).toContain(option);
    }
  });

  it("falls back to real-word and filler distractors to fill any slots the AI list doesn't cover", () => {
    const entries = [
      { word: "餐廳", translation: "restaurant", aiDistractors: ["kitchen"] },
      { word: "吃", translation: "to eat" },
      { word: "喝", translation: "to drink" },
    ];

    const questions = buildQuizQuestions(entries);
    const question = questions.find((q) => q.word === "餐廳")!;

    expect(question.options).toHaveLength(4);
    expect(question.options).toContain("restaurant");
    expect(question.options).toContain("kitchen");
    expect(new Set(question.options).size).toBe(4);
  });

  it("never shows the same translation text twice, even when two different words share an identical translation", () => {
    const entriesWithSharedTranslation = [
      { word: "中午", translation: "noon" },
      { word: "然後", translation: "afterwards" },
      { word: "之後", translation: "afterwards" },
      { word: "在家", translation: "at home" },
      { word: "吃飽", translation: "full (satiated)" },
    ];

    for (let i = 0; i < entries.length; i += 1) {
      const questions = buildQuizQuestions(entriesWithSharedTranslation);
      for (const question of questions) {
        expect(new Set(question.options).size).toBe(question.options.length);
      }
    }
  });
});

