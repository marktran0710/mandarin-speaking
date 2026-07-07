import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StoryVocabQuiz, {
  buildQuizQuestions,
  collectQuizEntries,
  type VocabQuizSummary,
} from "./StoryVocabQuiz";

describe("collectQuizEntries", () => {
  it("pairs each word with its translation, skipping words with none", () => {
    const entries = collectQuizEntries(
      ["餐廳", "吃", "喝"],
      ["restaurant", "", undefined],
    );

    expect(entries).toEqual([{ word: "餐廳", translation: "restaurant" }]);
  });

  it("dedupes repeated words (e.g. the same word appearing in two scenes)", () => {
    const entries = collectQuizEntries(
      ["餐廳", "吃", "餐廳"],
      ["restaurant", "to eat", "a different translation"],
    );

    expect(entries).toEqual([
      { word: "餐廳", translation: "restaurant" },
      { word: "吃", translation: "to eat" },
    ]);
  });

  it("trims whitespace-only translations to nothing", () => {
    const entries = collectQuizEntries(["餐廳"], ["   "]);
    expect(entries).toEqual([]);
  });

  it("keeps a word when no suggestedAnswers context is given at all", () => {
    const entries = collectQuizEntries(["餐廳"], ["restaurant"]);
    expect(entries).toEqual([{ word: "餐廳", translation: "restaurant" }]);
  });

  it("keeps a translated word that appears in its scene's suggested-answer sentence", () => {
    const entries = collectQuizEntries(
      ["餐廳"],
      ["restaurant"],
      ["我們去餐廳吃飯。"],
    );
    expect(entries).toEqual([{ word: "餐廳", translation: "restaurant" }]);
  });

  it("drops a translated word that does not appear in its scene's suggested-answer sentence", () => {
    const entries = collectQuizEntries(
      ["餐廳"],
      ["restaurant"],
      ["我們去公園散步。"],
    );
    expect(entries).toEqual([]);
  });

  it("drops a translated word whose scene has no suggested-answer sentence at all", () => {
    const entries = collectQuizEntries(["餐廳"], ["restaurant"], [""]);
    expect(entries).toEqual([]);
  });
});

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
});

describe("StoryVocabQuiz onComplete tracking", () => {
  const entries = [
    { word: "餐廳", translation: "restaurant" },
    { word: "吃", translation: "to eat" },
  ];

  it("reports a full results summary only once, on genuine completion", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    const onDone = vi.fn();

    render(<StoryVocabQuiz entries={entries} onDone={onDone} onComplete={onComplete} />);

    for (let i = 0; i < entries.length; i += 1) {
      const group = screen.getByRole("group");
      const firstOption = within(group).getAllByRole("button")[0];
      await user.click(firstOption);
      await user.click(screen.getByRole("button", { name: /Next question|Start practice/ }));
    }

    expect(onDone).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledTimes(1);

    const summary: VocabQuizSummary = onComplete.mock.calls[0][0];
    expect(summary.totalQuestions).toBe(2);
    expect(summary.questionResults).toHaveLength(2);
    expect(summary.correctCount).toBe(
      summary.questionResults.filter((r) => r.correct).length,
    );
    expect(summary.totalTimeMs).toBeGreaterThanOrEqual(0);
    for (const result of summary.questionResults) {
      expect(entries.some((e) => e.word === result.word)).toBe(true);
      expect(result.timeMs).toBeGreaterThanOrEqual(0);
    }
  });

  it("does not call onComplete when the student skips instead of finishing", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    const onDone = vi.fn();

    render(
      <StoryVocabQuiz
        entries={entries}
        onDone={onDone}
        onComplete={onComplete}
        allowSkip={true}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Skip/ }));

    expect(onDone).toHaveBeenCalledTimes(1);
    expect(onComplete).not.toHaveBeenCalled();
  });
});
