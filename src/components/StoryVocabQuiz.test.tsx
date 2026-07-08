import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

  it("reports a full results summary once reaching the results screen, and only calls onDone once the student continues past it", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    const onDone = vi.fn();

    render(<StoryVocabQuiz entries={entries} onDone={onDone} onComplete={onComplete} />);

    await user.click(screen.getByRole("button", { name: /Free Practice/ }));

    for (let i = 0; i < entries.length; i += 1) {
      const group = screen.getByRole("group");
      const firstOption = within(group).getAllByRole("button")[0];
      await user.click(firstOption);
      await user.click(screen.getByRole("button", { name: /Next question|Start practice/ }));
    }

    // Lands on the results screen first — onComplete fires here, but onDone
    // (which tells the caller to move on to practice) waits for the student
    // to explicitly continue past it.
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onDone).not.toHaveBeenCalled();

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

    await user.click(screen.getByRole("button", { name: /Continue to practice/ }));
    expect(onDone).toHaveBeenCalledTimes(1);
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

describe("StoryVocabQuiz modes", () => {
  const entries = [
    { word: "一", translation: "one" },
    { word: "二", translation: "two" },
    { word: "三", translation: "three" },
    { word: "四", translation: "four" },
    { word: "五", translation: "five" },
  ];
  const translationByWord = Object.fromEntries(entries.map((e) => [e.word, e.translation]));

  function optionButtons() {
    return screen
      .getAllByRole("button")
      .filter((b) => b.className.includes("vocab-quiz-option"));
  }

  async function answerCurrentQuestion(user: ReturnType<typeof userEvent.setup>, correct: boolean) {
    const word = screen.getByRole("heading").textContent!;
    const correctTranslation = translationByWord[word];
    const buttons = optionButtons();
    const target = correct
      ? buttons.find((b) => b.textContent === correctTranslation)
      : buttons.find((b) => b.textContent !== correctTranslation);
    await user.click(target!);
  }

  it("shows a pick-a-mode screen before any question, offering speed/strikes/free", () => {
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Speed/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /3 Strikes/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Free Practice/ })).toBeInTheDocument();
    // No question shown yet.
    expect(screen.queryByRole("group", { name: /What does/ })).not.toBeInTheDocument();
  });

  it("strikes mode ends the run after 3 consecutive wrong answers, before all questions are answered", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onComplete={onComplete} />);

    await user.click(screen.getByRole("button", { name: /3 Strikes/ }));

    for (let i = 0; i < 2; i += 1) {
      await answerCurrentQuestion(user, false);
      await user.click(screen.getByRole("button", { name: /Next question|Start practice/ }));
    }
    await answerCurrentQuestion(user, false);

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const summary: VocabQuizSummary = onComplete.mock.calls[0][0];
    // Ended after the 3rd wrong answer, not all 5 words.
    expect(summary.questionResults).toHaveLength(3);
    expect(summary.correctCount).toBe(0);
  });

  it("strikes mode resets the streak on a correct answer, so 2 wrong + 1 right + 2 wrong does not end the run", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    const sixEntries = [...entries, { word: "六", translation: "six" }];
    const sixTranslationByWord = Object.fromEntries(sixEntries.map((e) => [e.word, e.translation]));
    render(<StoryVocabQuiz entries={sixEntries} onDone={vi.fn()} onComplete={onComplete} />);

    await user.click(screen.getByRole("button", { name: /3 Strikes/ }));

    const sequence = [false, false, true, false, false];
    for (const correct of sequence) {
      const word = screen.getByRole("heading").textContent!;
      const correctTranslation = sixTranslationByWord[word];
      const buttons = optionButtons();
      const target = correct
        ? buttons.find((b) => b.textContent === correctTranslation)
        : buttons.find((b) => b.textContent !== correctTranslation);
      await user.click(target!);
      const nextBtn = screen.queryByRole("button", { name: /Next question|Start practice/ });
      if (nextBtn) await user.click(nextBtn);
    }

    // Never 3 wrong in a row, and a 6th question remains unanswered, so the
    // run should still be going rather than finished (early or otherwise).
    expect(onComplete).not.toHaveBeenCalled();
    expect(screen.getByRole("heading")).toBeInTheDocument();
  });

  it("speed mode shows a countdown and auto-fails the question when it reaches zero", () => {
    vi.useFakeTimers();
    try {
      const onComplete = vi.fn();
      render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onComplete={onComplete} />);

      fireEvent.click(screen.getByRole("button", { name: /Speed/ }));
      expect(screen.getByText("⏱️ 8s")).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(8_100);
      });

      expect(screen.getByText(/Time's up/)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("speed mode ends the whole run once the overall time cap is reached", () => {
    vi.useFakeTimers();
    try {
      const onComplete = vi.fn();
      render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onComplete={onComplete} />);

      fireEvent.click(screen.getByRole("button", { name: /Speed/ }));

      act(() => {
        vi.advanceTimersByTime(60_100);
      });

      expect(onComplete).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("offers a missed-words retry after the run, scoped to only the words gotten wrong, and does not record it as a new attempt", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    const onDone = vi.fn();
    render(<StoryVocabQuiz entries={entries} onDone={onDone} onComplete={onComplete} />);

    await user.click(screen.getByRole("button", { name: /Free Practice/ }));

    // Get the first question wrong, the rest right.
    await answerCurrentQuestion(user, false);
    await user.click(screen.getByRole("button", { name: /Next question|Start practice/ }));
    for (let i = 1; i < entries.length; i += 1) {
      await answerCurrentQuestion(user, true);
      await user.click(screen.getByRole("button", { name: /Next question|Start practice/ }));
    }

    expect(onComplete).toHaveBeenCalledTimes(1);
    const missedList = screen.getByRole("list", { name: "Missed words" });
    expect(within(missedList).getAllByRole("listitem")).toHaveLength(1);
    const missedWord = missedList.querySelector(".vocab-quiz-missed-word")!.textContent;

    await user.click(screen.getByRole("button", { name: /Practice missed words/ }));

    // Retry round: exactly the one missed word, no mode-select screen.
    expect(screen.getByRole("heading").textContent).toBe(missedWord);
    await answerCurrentQuestion(user, true);
    await user.click(screen.getByRole("button", { name: /Next question|Start practice/ }));

    // Retry round completing must not fire a second onComplete/attempt, and
    // its own results screen must not offer yet another retry.
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /Practice missed words/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Continue to practice/ }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});
