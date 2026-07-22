import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StoryVocabQuiz, {
  buildQuizQuestions,
  collectQuizEntries,
  type VocabQuizSummary,
} from "./StoryVocabQuiz";
import * as database from "../services/database";

vi.mock("../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/database")>();
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

    // alreadyCompleted: this test drives onComplete/onDone sequencing, not
    // the ⭐⭐ practice gate (covered in the star-tier describe).
    render(
      <StoryVocabQuiz entries={entries} onDone={onDone} onComplete={onComplete} alreadyCompleted />,
    );

    await user.click(screen.getByRole("button", { name: /Tier 1/ }));

    for (let i = 0; i < 20; i += 1) {
      await answerCurrentQuestion(user, true, translationByWord);
      await user.click(screen.getByRole("button", { name: /Next question|See results/ }));
    }

    // Lands on the results screen first — onComplete fires here, but onDone
    // (which tells the caller to move on to practice) waits for the student
    // to explicitly continue past it.
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    expect(onDone).not.toHaveBeenCalled();

    const summary: VocabQuizSummary = onComplete.mock.calls[0][0];
    expect(summary.totalQuestions).toBe(20);
    expect(summary.questionResults).toHaveLength(20);
    expect(summary.correctCount).toBe(20);
    expect(summary.totalTimeMs).toBeGreaterThanOrEqual(0);
    for (const result of summary.questionResults) {
      expect(entries.some((e) => e.word === result.word)).toBe(true);
      expect(result.timeMs).toBeGreaterThanOrEqual(0);
    }

    // Practice opens at ⭐⭐, so the road to onDone runs through tier 2 —
    // each scored round reports its own onComplete along the way.
    await user.click(screen.getByRole("button", { name: /Challenge Tier 2/ }));
    for (let i = 0; i < 22; i += 1) {
      await answerCurrentQuestion(user, true, translationByWord);
      await user.click(screen.getByRole("button", { name: /Next question|See results/ }));
    }
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(2));
    expect(onDone).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /Continue to practice/ }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("never offers a skip button, in any mode, on the mode-select screen or mid-quiz", async () => {
    const user = userEvent.setup();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onBack={vi.fn()} />);

    expect(screen.queryByRole("button", { name: /Skip/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Tier 1/ }));
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

  it("shows the star-ladder screen before any question, offering the three tiers + review", () => {
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Tier 1/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Tier 2/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Tier 3/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Review/ })).toBeInTheDocument();
    // No question shown yet.
    expect(screen.queryByRole("group", { name: /What does/ })).not.toBeInTheDocument();
  });

  it("tier runs show no Finish button — a round always plays out its full question count", async () => {
    const user = userEvent.setup();

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /Tier 1/ }));
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

  it("tier 3 shows a live countdown of seconds remaining", async () => {
    const { recordLocalStars } = await import("../utils/quizTiers");
    localStorage.clear();
    recordLocalStars("s-timer", 2);
    vi.useFakeTimers();
    try {
      render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-timer" />);

      fireEvent.click(screen.getByRole("button", { name: /Tier 3/ }));
      expect(screen.getByText("⏱️ 150s")).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(10_000);
      });
      expect(screen.getByText("⏱️ 140s")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
      localStorage.clear();
    }
  });

  it("untimed tiers show no countdown", async () => {
    const user = userEvent.setup();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /Tier 1/ }));

    expect(screen.queryByText(/⏱️/)).not.toBeInTheDocument();
  });

  it("offers a missed-words retry after the run, scoped to only the words gotten wrong, and does not record it as a new attempt", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    const onDone = vi.fn();
    render(
      <StoryVocabQuiz entries={entries} onDone={onDone} onComplete={onComplete} alreadyCompleted />,
    );

    await user.click(screen.getByRole("button", { name: /Tier 1/ }));

    // Answer every question wrong: all 5 distinct words land in "missed".
    for (let i = 0; i < 20; i += 1) {
      await answerCurrentQuestion(user, false);
      await user.click(screen.getByRole("button", { name: /Next question|See results/ }));
    }

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const missedList = screen.getByRole("list", { name: "Missed words" });
    expect(within(missedList).getAllByRole("listitem")).toHaveLength(5);

    await user.click(screen.getByRole("button", { name: /Practice missed words/ }));

    // Retry round: exactly the 5 missed words, no mode-select screen, and no
    // Finish button (it's bounded, unlike the old Free mode's original round).
    expect(screen.queryByRole("button", { name: /Finish & see results/ })).not.toBeInTheDocument();
    for (let i = 0; i < 5; i += 1) {
      await answerCurrentQuestion(user, true);
      await user.click(screen.getByRole("button", { name: /Next question|See results/ }));
    }

    // Retry round completing must not fire a second onComplete/attempt, and
    // its own results screen must not offer yet another retry.
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /Practice missed words/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Continue to practice/ }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});

describe("StoryVocabQuiz AI badge + cloze questions", () => {
  it("shows the AI badge on a translation question whose options draw from AI-generated distractors", async () => {
    const user = userEvent.setup();
    const entries = [
      { word: "喝", translation: "to drink", aiDistractors: ["to buy", "to look", "to do"] },
    ];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_TRANSLATION);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      expect(screen.getByRole("heading")).toHaveTextContent("喝");
      expect(screen.getByLabelText("AI-generated question")).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("shows no AI badge on a translation question that has no AI-generated distractors", async () => {
    const user = userEvent.setup();
    const entries = [
      { word: "一", translation: "one" },
      { word: "二", translation: "two" },
    ];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_TRANSLATION);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      expect(screen.queryByLabelText("AI-generated question")).not.toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("mixes in a cloze question (sentence with a blank, Chinese-word options) when the word has cached AI cloze candidates", async () => {
    const user = userEvent.setup();
    const entries = [
      {
        word: "喝",
        translation: "to drink",
        aiCloze: [{ sentence: "我要喝水。", distractors: ["買", "看", "做"] }],
      },
    ];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      expect(
        screen.getByRole("group", { name: "Which word fits the blank?" }),
      ).toBeInTheDocument();
      expect(screen.getByRole("heading")).toHaveTextContent("我要____水。");
      expect(screen.getByLabelText("AI-generated question")).toBeInTheDocument();

      const options = optionButtons();
      expect(options.map((o) => o.textContent)).toEqual(
        expect.arrayContaining(["喝", "買", "看", "做"]),
      );

      await user.click(options.find((o) => o.textContent === "喝")!);
      expect(screen.getByRole("button", { name: "喝 (correct answer)" })).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("never asks a cloze question for a word with no cached AI cloze candidates, even when the random roll would allow it", async () => {
    const user = userEvent.setup();
    const entries = [{ word: "一", translation: "one" }];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      // With no cloze/pos/synonym data, pinyin is the only other kind ever
      // available, so a high random roll lands there instead of cloze.
      expect(
        screen.queryByRole("group", { name: "Which word fits the blank?" }),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("group", { name: "How do you read 一?" })).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });
});

describe("StoryVocabQuiz pinyin/pos/synonym questions", () => {
  it("asks a pinyin question (no AI badge) when the random roll lands there, with the reading among the options", async () => {
    const user = userEvent.setup();
    const entries = [
      { word: "喝", translation: "to drink", pinyin: "hē" },
      { word: "看", translation: "to look", pinyin: "kàn" },
      { word: "做", translation: "to do", pinyin: "zuò" },
    ];
    // Only translation + pinyin are ever available for these entries (no
    // cloze/pos/synonym data), so a high roll lands on pinyin — the last
    // kind checked in pickQuestionKind.
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      const word = screen.getByRole("heading").textContent!;
      expect(screen.queryByLabelText("AI-generated question")).not.toBeInTheDocument();
      expect(
        screen.getByRole("group", { name: `How do you read ${word}?` }),
      ).toBeInTheDocument();

      const pinyinByWord: Record<string, string> = { 喝: "hē", 看: "kàn", 做: "zuò" };
      const options = optionButtons();
      expect(options.map((o) => o.textContent)).toContain(pinyinByWord[word]);

      await user.click(options.find((o) => o.textContent === pinyinByWord[word])!);
      expect(
        screen.getByRole("button", { name: `${pinyinByWord[word]} (correct answer)` }),
      ).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("asks a part-of-speech question (no AI badge) only for a word with teacher-authored pos data", async () => {
    const user = userEvent.setup();
    const entries = [
      { word: "貓", translation: "cat", pos: "N" },
      { word: "跑", translation: "to run", pos: "V" },
    ];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      const word = screen.getByRole("heading").textContent!;
      expect(screen.queryByLabelText("AI-generated question")).not.toBeInTheDocument();
      expect(
        screen.getByRole("group", { name: `What part of speech is ${word}?` }),
      ).toBeInTheDocument();

      const posByWord: Record<string, string> = { 貓: "N", 跑: "V" };
      const options = optionButtons();
      expect(options.map((o) => o.textContent)).toContain(posByWord[word]);

      await user.click(options.find((o) => o.textContent === posByWord[word])!);
      expect(
        screen.getByRole("button", { name: `${posByWord[word]} (correct answer)` }),
      ).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("never asks a pinyin question for a word with no computable reading (e.g. an English key word)", async () => {
    const user = userEvent.setup();
    const entries = [{ word: "market", translation: "marketplace" }];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    try {
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      // "market" has no pinyin reading, so even the highest roll must fall
      // back to a translation question instead of one with an empty answer.
      expect(
        screen.queryByRole("group", { name: "How do you read market?" }),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("group", { name: "What does market mean?" })).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("never asks a part-of-speech question for a word with no authored pos data", async () => {
    const user = userEvent.setup();
    const entries = [{ word: "一", translation: "one" }];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      expect(
        screen.queryByRole("group", { name: "What part of speech is 一?" }),
      ).not.toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("asks a synonym question (with AI badge) whose correct answer is the synonym, not the original word", async () => {
    const user = userEvent.setup();
    const entries = [
      {
        word: "高興",
        translation: "happy",
        aiSynonym: [{ synonym: "開心", distractors: ["生氣", "累", "餓"] }],
      },
    ];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      expect(screen.getByRole("heading")).toHaveTextContent("高興");
      expect(screen.getByLabelText("AI-generated question")).toBeInTheDocument();
      expect(
        screen.getByRole("group", { name: "Which word means the same as 高興?" }),
      ).toBeInTheDocument();

      const options = optionButtons();
      expect(options.map((o) => o.textContent)).toEqual(
        expect.arrayContaining(["開心", "生氣", "累", "餓"]),
      );
      // The original word itself must never appear as an option.
      expect(options.map((o) => o.textContent)).not.toContain("高興");

      await user.click(options.find((o) => o.textContent === "開心")!);
      expect(screen.getByRole("button", { name: "開心 (correct answer)" })).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });
});

describe("StoryVocabQuiz weak-words mode", () => {
  const entries = [
    { word: "一", translation: "one" },
    { word: "二", translation: "two" },
    { word: "三", translation: "three" },
  ];
  const translationByWord = Object.fromEntries(entries.map((e) => [e.word, e.translation]));

  async function answerCurrentQuestion(user: ReturnType<typeof userEvent.setup>, correct: boolean) {
    const word = screen.getByRole("heading").textContent!;
    const correctTranslation = translationByWord[word];
    const buttons = optionButtons();
    const target = correct
      ? buttons.find((b) => b.textContent === correctTranslation)
      : buttons.find((b) => b.textContent !== correctTranslation);
    await user.click(target!);
  }

  it("does not offer the weak-words card without a storyId, or when there are no persisted weak words", async () => {
    vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue([]);
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);

    await waitFor(() => expect(database.getVocabQuizWeakWords).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /Weak words/ })).not.toBeInTheDocument();
  });

  it("offers a weak-words card scoped to only the persisted missed words, and reports it as a real 'weak_words' attempt", async () => {
    vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(["一", "三"]);
    const user = userEvent.setup();
    const onComplete = vi.fn();
    const onDone = vi.fn();

    render(
      <StoryVocabQuiz
        entries={entries}
        onDone={onDone}
        onComplete={onComplete}
        storyId="story-1"
        studentId="s1"
        alreadyCompleted
      />,
    );

    const weakWordsButton = await screen.findByRole("button", { name: /Weak words \(2\)/ });
    await user.click(weakWordsButton);

    for (let i = 0; i < 2; i += 1) {
      await answerCurrentQuestion(user, true);
      await user.click(screen.getByRole("button", { name: /Next question|See results/ }));
    }

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const summary: VocabQuizSummary = onComplete.mock.calls[0][0];
    expect(summary.mode).toBe("weak_words");
    expect(summary.totalQuestions).toBe(2);
    expect(summary.questionResults.map((r) => r.word).sort()).toEqual(["一", "三"]);

    await user.click(screen.getByRole("button", { name: /Continue to practice/ }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});

describe("StoryVocabQuiz single-correct-answer guards", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  async function startTier2() {
    const { recordLocalStars } = await import("../utils/quizTiers");
    recordLocalStars("s1", 1);
  }

  it("drops an AI translation distractor that differs from the correct answer only by case/punctuation", async () => {
    await startTier2();
    const user = userEvent.setup();
    render(
      <StoryVocabQuiz
        entries={[
          {
            word: "餐廳",
            translation: "restaurant",
            aiDistractors: ["Restaurant.", "hotel", "kitchen"],
          },
        ]}
        onDone={vi.fn()}
        storyId="s1"
      />,
    );
    await user.click(screen.getByRole("button", { name: /Tier 2/ }));

    const options = optionButtons().map((b) => b.textContent);
    expect(options).toContain("restaurant");
    expect(options).not.toContain("Restaurant.");
  });

  it("never offers a second word with the same translation as a reverse-question option", async () => {
    // Both words translate to "restaurant" — whichever is asked, the other
    // would be a second correct answer and must be filtered out.
    vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    const user = userEvent.setup();
    render(
      <StoryVocabQuiz
        entries={[
          { word: "餐廳", translation: "restaurant" },
          { word: "飯館", translation: "Restaurant." },
        ]}
        onDone={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Tier 1/ }));

    const options = optionButtons().map((b) => b.textContent);
    expect(options).toHaveLength(1);
    expect(["餐廳", "飯館"]).toContain(options[0]);
  });

  it("never offers a homophone of the spoken word as a listening option", async () => {
    await startTier2();
    vi.stubGlobal("speechSynthesis", { speak: vi.fn(), cancel: vi.fn() });
    vi.stubGlobal(
      "SpeechSynthesisUtterance",
      class {
        text: string;
        lang = "";
        constructor(text: string) {
          this.text = text;
        }
      },
    );
    try {
      // 他 and 她 are both read "tā" — by sound alone both would be correct.
      vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
      const user = userEvent.setup();
      render(
        <StoryVocabQuiz
          entries={[
            { word: "他", translation: "he" },
            { word: "她", translation: "she" },
          ]}
          onDone={vi.fn()}
          storyId="s1"
        />,
      );
      await user.click(screen.getByRole("button", { name: /Tier 2/ }));

      const options = optionButtons().map((b) => b.textContent);
      expect(options).toHaveLength(1);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("never pads cloze options with a story word that shares the answer's translation", async () => {
    await startTier2();
    vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    const user = userEvent.setup();
    render(
      <StoryVocabQuiz
        entries={[
          {
            word: "高興",
            translation: "happy",
            aiCloze: [{ sentence: "我今天很高興。", distractors: ["生氣"] }],
          },
          {
            word: "開心",
            translation: "happy",
            aiCloze: [{ sentence: "他玩得很開心。", distractors: ["難過"] }],
          },
        ]}
        onDone={vi.fn()}
        storyId="s1"
      />,
    );
    await user.click(screen.getByRole("button", { name: /Tier 2/ }));

    // Whichever word the blank asks for, the other "happy" word would fit
    // the sentence just as well — it must never appear alongside it.
    const options = optionButtons().map((b) => b.textContent);
    expect(options.includes("高興") && options.includes("開心")).toBe(false);
  });

  it("styles pinyin options with the dedicated pinyin (mono) font class", async () => {
    await startTier2();
    vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    const user = userEvent.setup();
    render(
      <StoryVocabQuiz
        entries={[{ word: "喝茶", translation: "drink tea", pinyin: "hē chá" }]}
        onDone={vi.fn()}
        storyId="s1"
      />,
    );
    await user.click(screen.getByRole("button", { name: /Tier 2/ }));

    const group = screen.getByRole("group", { name: /How do you read/ });
    expect(group.className).toContain("vocab-quiz-options-pinyin");
  });
});

describe("StoryVocabQuiz stable question chrome", () => {
  it("shows an instruction line on every question kind, including plain translation", async () => {
    const user = userEvent.setup();
    render(
      <StoryVocabQuiz
        entries={[
          { word: "喝", translation: "to drink" },
          { word: "吃", translation: "to eat" },
        ]}
        onDone={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Tier 1/ }));

    // Math.random is pinned to 0 → translation question; its instruction
    // keeps the header the same height as every other kind's.
    expect(screen.getByRole("group", { name: /What does/ })).toBeInTheDocument();
    expect(screen.getByText("What does this word mean?")).toBeInTheDocument();
  });
});

describe("StoryVocabQuiz star tiers", () => {
  const entries = [
    { word: "一", translation: "one" },
    { word: "二", translation: "two" },
    { word: "三", translation: "three" },
    { word: "四", translation: "four" },
    { word: "五", translation: "five" },
  ];
  const translationByWord = Object.fromEntries(entries.map((e) => [e.word, e.translation]));

  beforeEach(() => {
    localStorage.clear();
  });

  /** Drives one tier run answering `correctCount` questions right and the
   * rest wrong, ending on the summary screen. */
  async function playTierRun(
    user: ReturnType<typeof userEvent.setup>,
    questionCount: number,
    correctCount: number,
    byWord: Record<string, string> = translationByWord,
  ) {
    for (let i = 0; i < questionCount; i += 1) {
      await answerCurrentQuestion(user, i < correctCount, byWord);
      await user.click(screen.getByRole("button", { name: /Next question|See results/ }));
    }
  }

  it("locks tiers 2 and 3 until the previous star is earned, keeping Review available", () => {
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s1" />);

    expect(screen.getByRole("button", { name: /Tier 1/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Tier 2/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Tier 3/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Review/ })).toBeEnabled();
  });

  it("unlocks tier 2 (but not 3) once the story has 1 star recorded locally", async () => {
    const { recordLocalStars } = await import("../utils/quizTiers");
    recordLocalStars("s1", 1);
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s1" />);

    expect(screen.getByRole("button", { name: /Tier 2/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Tier 3/ })).toBeDisabled();
  });

  it("passing tier 1 earns the star and dangles tier 2, but only a tier-2 pass unlocks practice", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    const onDone = vi.fn();
    render(
      <StoryVocabQuiz entries={entries} onDone={onDone} onComplete={onComplete} storyId="s1" />,
    );

    await user.click(screen.getByRole("button", { name: /Tier 1/ }));
    expect(screen.getByText(/Question 1 of 20/)).toBeInTheDocument();
    await playTierRun(user, 20, 20);

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const summary: VocabQuizSummary = onComplete.mock.calls[0][0];
    expect(summary.mode).toBe("tier1");
    expect(summary.totalQuestions).toBe(20);
    expect(summary.correctCount).toBe(20);

    const { loadLocalStars } = await import("../utils/quizTiers");
    expect(loadLocalStars("s1")).toBe(1);

    // One star isn't enough for practice yet — the summary celebrates and
    // dangles tier 2 as the way in.
    expect(screen.queryByRole("button", { name: /Continue to practice/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Challenge Tier 2/ }));
    expect(screen.getByText(/Question 1 of 22/)).toBeInTheDocument();
    await playTierRun(user, 22, 22);

    // ⭐⭐ earned: practice opens, and the attempt was recorded as tier2.
    expect(loadLocalStars("s1")).toBe(2);
    expect(onComplete).toHaveBeenCalledTimes(2);
    expect(onComplete.mock.calls[1][0].mode).toBe("tier2");
    expect(screen.getByRole("button", { name: /Continue to practice/ })).toBeInTheDocument();
  });

  it("failing tier 1 near the threshold shows the near-miss gap and a Try again button, without unlocking practice", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onComplete={onComplete} storyId="s1" />);

    await user.click(screen.getByRole("button", { name: /Tier 1/ }));
    await playTierRun(user, 20, 13);

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    // 13/20 with a 14 threshold: one more right answer would have passed.
    expect(screen.getByText(/1 more/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Continue to practice/ })).not.toBeInTheDocument();
    // A quiet exit back to the tier ladder exists so the student is never
    // trapped between retrying and nothing.
    expect(screen.getByRole("button", { name: /Back to menu/ })).toBeInTheDocument();

    // Try again immediately restarts the same tier as a fresh scored run.
    await user.click(screen.getByRole("button", { name: /Try again/ }));
    expect(screen.getByText(/Question 1 of 20/)).toBeInTheDocument();
  });

  it("still offers Continue to practice after a failed run when practice was already unlocked earlier", async () => {
    const user = userEvent.setup();
    render(
      <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s1" alreadyCompleted />,
    );

    await user.click(screen.getByRole("button", { name: /Tier 1/ }));
    await playTierRun(user, 20, 0);

    expect(screen.getByRole("button", { name: /Continue to practice/ })).toBeInTheDocument();
  });

  it("tier 3 runs against a 150-second overall countdown and ends at the cap", async () => {
    const { recordLocalStars } = await import("../utils/quizTiers");
    recordLocalStars("s1", 2);
    vi.useFakeTimers();
    try {
      const onComplete = vi.fn();
      render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onComplete={onComplete} storyId="s1" />);

      fireEvent.click(screen.getByRole("button", { name: /Tier 3/ }));
      expect(screen.getByText("⏱️ 150s")).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(150_100);
      });
      expect(onComplete).toHaveBeenCalledTimes(1);
      expect(onComplete.mock.calls[0][0].mode).toBe("tier3");
    } finally {
      vi.useRealTimers();
    }
  });

  it("tier 1 ignores AI translation distractors while tier 2 uses them", async () => {
    const { recordLocalStars } = await import("../utils/quizTiers");
    const user = userEvent.setup();
    const aiEntries = entries.map((e) => ({
      ...e,
      aiDistractors: ["ai-trap-a", "ai-trap-b", "ai-trap-c"],
    }));

    const { unmount } = render(<StoryVocabQuiz entries={aiEntries} onDone={vi.fn()} storyId="s1" />);
    await user.click(screen.getByRole("button", { name: /Tier 1/ }));
    for (const button of optionButtons()) {
      expect(button.textContent).not.toMatch(/ai-trap/);
    }
    unmount();

    recordLocalStars("s1", 1);
    render(<StoryVocabQuiz entries={aiEntries} onDone={vi.fn()} storyId="s1" />);
    await user.click(screen.getByRole("button", { name: /Tier 2/ }));
    expect(optionButtons().some((b) => /ai-trap/.test(b.textContent ?? ""))).toBe(true);
  });

  it("tier 2 pinyin questions use tone-trap distractors (same syllables, different tone)", async () => {
    const { recordLocalStars } = await import("../utils/quizTiers");
    recordLocalStars("s1", 1);
    // A single entry leaves pinyin as the last available kind at tier 2.
    vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    const user = userEvent.setup();
    render(
      <StoryVocabQuiz
        entries={[{ word: "喝茶", translation: "drink tea", pinyin: "hē chá" }]}
        onDone={vi.fn()}
        storyId="s1"
      />,
    );

    await user.click(screen.getByRole("button", { name: /Tier 2/ }));
    const options = optionButtons().map((b) => b.textContent);
    expect(options.length).toBeGreaterThan(1);
    const strip = (s: string) => s.normalize("NFD").replace(/\p{Mn}/gu, "");
    for (const option of options) {
      expect(strip(option!)).toBe("he cha");
    }
  });

  it("tier 2 listening questions speak the word and are answered by picking the heard word", async () => {
    const { recordLocalStars } = await import("../utils/quizTiers");
    recordLocalStars("s1", 1);
    const speak = vi.fn();
    vi.stubGlobal("speechSynthesis", { speak, cancel: vi.fn() });
    vi.stubGlobal(
      "SpeechSynthesisUtterance",
      class {
        text: string;
        lang = "";
        constructor(text: string) {
          this.text = text;
        }
      },
    );
    try {
      // Two entries with no AI data: listening is the last available kind.
      vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
      const user = userEvent.setup();
      render(
        <StoryVocabQuiz
          entries={[
            { word: "喝茶", translation: "drink tea" },
            { word: "餐廳", translation: "restaurant" },
          ]}
          onDone={vi.fn()}
          storyId="s1"
        />,
      );

      await user.click(screen.getByRole("button", { name: /Tier 2/ }));
      await waitFor(() => expect(speak).toHaveBeenCalled());
      const spokenWord = speak.mock.calls[0][0].text;

      // The prompt hides the word (it IS the answer) behind a replay button.
      expect(screen.getByRole("button", { name: /Play the word/ })).toBeInTheDocument();
      const correctButton = optionButtons().find((b) => b.textContent === spokenWord)!;
      await user.click(correctButton);
      expect(correctButton.textContent).toContain("✓");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("tier 1 reverse questions show the translation and offer Chinese words as options", async () => {
    // With >=2 entries, reverse is the last available kind at tier 1.
    vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    const user = userEvent.setup();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s1" />);

    await user.click(screen.getByRole("button", { name: /Tier 1/ }));
    const prompt = screen.getByRole("heading").textContent!;
    expect(Object.values(translationByWord)).toContain(prompt);

    const expectedWord = Object.keys(translationByWord).find(
      (w) => translationByWord[w] === prompt,
    )!;
    const correctButton = optionButtons().find((b) => b.textContent === expectedWord)!;
    await user.click(correctButton);
    expect(correctButton.textContent).toContain("✓");
  });
});
