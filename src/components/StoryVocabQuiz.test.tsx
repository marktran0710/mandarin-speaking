import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StoryVocabQuiz, {
  buildQuizQuestions,
  collectQuizEntries,
  type VocabQuizSummary,
} from "./StoryVocabQuiz";

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

  it("attaches AI distractors aligned by index, and omits the field entirely when none are given for a word", () => {
    const entries = collectQuizEntries(
      ["餐廳", "吃"],
      ["restaurant", "to eat"],
      undefined,
      [["kitchen", "hotel"], undefined],
    );
    expect(entries).toEqual([
      { word: "餐廳", translation: "restaurant", aiDistractors: ["kitchen", "hotel"] },
      { word: "吃", translation: "to eat" },
    ]);
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

    for (let i = 0; i < 20; i += 1) {
      const questions = buildQuizQuestions(entriesWithSharedTranslation);
      for (const question of questions) {
        expect(new Set(question.options).size).toBe(question.options.length);
      }
    }
  });
});

describe("StoryVocabQuiz onComplete tracking", () => {
  const entries = [
    { word: "餐廳", translation: "restaurant" },
    { word: "吃", translation: "to eat" },
  ];
  const translationByWord = Object.fromEntries(entries.map((e) => [e.word, e.translation]));

  it("reports a full results summary once reaching the results screen, and only calls onDone once the student continues past it", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    const onDone = vi.fn();

    render(<StoryVocabQuiz entries={entries} onDone={onDone} onComplete={onComplete} />);

    await user.click(screen.getByRole("button", { name: /3 Strikes/ }));

    // Strikes mode has no manual "Finish" button — 3 consecutive wrong
    // answers is the deterministic way to reach the results screen.
    for (let i = 0; i < 2; i += 1) {
      await answerCurrentQuestion(user, false, translationByWord);
      await user.click(screen.getByRole("button", { name: /Next question|Start practice/ }));
    }
    await answerCurrentQuestion(user, false, translationByWord);

    // Lands on the results screen first — onComplete fires here, but onDone
    // (which tells the caller to move on to practice) waits for the student
    // to explicitly continue past it.
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    expect(onDone).not.toHaveBeenCalled();

    const summary: VocabQuizSummary = onComplete.mock.calls[0][0];
    expect(summary.totalQuestions).toBe(3);
    expect(summary.questionResults).toHaveLength(3);
    expect(summary.correctCount).toBe(0);
    expect(summary.totalTimeMs).toBeGreaterThanOrEqual(0);
    for (const result of summary.questionResults) {
      expect(entries.some((e) => e.word === result.word)).toBe(true);
      expect(result.timeMs).toBeGreaterThanOrEqual(0);
    }

    await user.click(screen.getByRole("button", { name: /Continue to practice/ }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("never offers a skip button, in any mode, on the mode-select screen or mid-quiz", async () => {
    const user = userEvent.setup();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onBack={vi.fn()} />);

    expect(screen.queryByRole("button", { name: /Skip/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /3 Strikes/ }));
    expect(screen.queryByRole("button", { name: /Skip/ })).not.toBeInTheDocument();
  });

  it("does not call onComplete when the student backs out instead of finishing", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    const onDone = vi.fn();
    const onBack = vi.fn();

    render(
      <StoryVocabQuiz entries={entries} onDone={onDone} onComplete={onComplete} onBack={onBack} />,
    );

    await user.click(screen.getByRole("button", { name: /Back to activities/ }));

    expect(onBack).toHaveBeenCalledTimes(1);
    expect(onDone).not.toHaveBeenCalled();
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

  it("shows a pick-a-mode screen before any question, offering speed/strikes/review", () => {
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Speed/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /3 Strikes/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Review/ })).toBeInTheDocument();
    // No question shown yet.
    expect(screen.queryByRole("group", { name: /What does/ })).not.toBeInTheDocument();
  });

  it("neither Speed nor Strikes shows a Finish button (Review replaced the old unlimited Free mode)", async () => {
    const user = userEvent.setup();

    const { unmount: unmountStrikes } = render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /3 Strikes/ }));
    expect(screen.queryByRole("button", { name: /Finish & see results/ })).not.toBeInTheDocument();
    unmountStrikes();

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /Speed/ }));
    expect(screen.queryByRole("button", { name: /Finish & see results/ })).not.toBeInTheDocument();
  });

  it("Review mode shows every word's pinyin and translation, and never starts a quiz", async () => {
    const user = userEvent.setup();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /Review/ }));

    const list = screen.getByRole("list", { name: "Vocabulary list" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(entries.length);
    for (const entry of entries) {
      expect(within(list).getByText(entry.word)).toBeInTheDocument();
      expect(within(list).getByText(entry.translation)).toBeInTheDocument();
    }
    expect(screen.queryByRole("group", { name: /What does/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Back to modes/ }));
    expect(screen.getByRole("button", { name: /Review/ })).toBeInTheDocument();
  });

  it("strikes mode is unlimited — the question pool cycles once every entry has been asked", async () => {
    const user = userEvent.setup();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /3 Strikes/ }));

    // Answer more questions than there are distinct entries (5), always
    // correctly so strikes never triggers — proves the pool cycles/reshuffles
    // instead of running out, and the mode never
    // shows "Start practice" (it has no fixed last question).
    for (let i = 0; i < entries.length + 2; i += 1) {
      expect(screen.getByRole("heading")).toBeInTheDocument();
      await answerCurrentQuestion(user, true);
      expect(screen.queryByRole("button", { name: /Start practice/ })).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: /Next question/ }));
    }
    expect(screen.getByRole("heading")).toBeInTheDocument();
  });

  it("speed mode is a fixed 20-question run", async () => {
    const user = userEvent.setup();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /Speed/ }));
    expect(screen.getByText(/Question 1 of 20/)).toBeInTheDocument();

    for (let i = 0; i < 19; i += 1) {
      await answerCurrentQuestion(user, true);
      await user.click(screen.getByRole("button", { name: /Next question|Start practice/ }));
    }

    expect(screen.getByText(/Question 20 of 20/)).toBeInTheDocument();
    await answerCurrentQuestion(user, true);
    expect(screen.getByRole("button", { name: /Start practice/ })).toBeInTheDocument();
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

    await user.click(screen.getByRole("button", { name: /3 Strikes/ }));

    // Strikes mode has no manual "Finish" — 3 consecutive wrong answers ends
    // the run itself, and (since none were correct) all 3 land in "missed".
    for (let i = 0; i < 2; i += 1) {
      await answerCurrentQuestion(user, false);
      await user.click(screen.getByRole("button", { name: /Next question|Start practice/ }));
    }
    await answerCurrentQuestion(user, false);

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const missedList = screen.getByRole("list", { name: "Missed words" });
    expect(within(missedList).getAllByRole("listitem")).toHaveLength(3);

    await user.click(screen.getByRole("button", { name: /Practice missed words/ }));

    // Retry round: exactly the 3 missed words, no mode-select screen, and no
    // Finish button (it's bounded, unlike the old Free mode's original round).
    expect(screen.queryByRole("button", { name: /Finish & see results/ })).not.toBeInTheDocument();
    for (let i = 0; i < 3; i += 1) {
      await answerCurrentQuestion(user, true);
      await user.click(screen.getByRole("button", { name: /Next question|Start practice/ }));
    }

    // Retry round completing must not fire a second onComplete/attempt, and
    // its own results screen must not offer yet another retry.
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /Practice missed words/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Continue to practice/ }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});
