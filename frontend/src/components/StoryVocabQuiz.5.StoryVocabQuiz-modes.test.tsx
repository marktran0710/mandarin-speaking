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

  it("shows the star-ladder screen before any question, offering the three tiers + review", async () => {
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} />);
    await screen.findByRole("group", { name: "Quiz mode" });

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
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(screen.getByRole("button", { name: /Tier 1/ }));
    expect(screen.queryByRole("button", { name: /Finish & see results/ })).not.toBeInTheDocument();
  });

  it("Review mode shows every word's pinyin and translation, and never starts a quiz", async () => {
    const user = userEvent.setup();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} />);
    await screen.findByRole("group", { name: "Quiz mode" });

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
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-timer" />);
    // Settle the initial data-load gate on real timers first — testing-
    // library's polling can't progress once fake timers replace setTimeout.
    await screen.findByRole("group", { name: "Quiz mode" });
    vi.useFakeTimers();
    try {
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
    await screen.findByRole("group", { name: "Quiz mode" });

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
    await screen.findByRole("group", { name: "Quiz mode" });

    await user.click(screen.getByRole("button", { name: /Tier 1/ }));

    // Answer every question wrong: all 5 distinct words land in "missed".
    for (let i = 0; i < entries.length; i += 1) {
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

