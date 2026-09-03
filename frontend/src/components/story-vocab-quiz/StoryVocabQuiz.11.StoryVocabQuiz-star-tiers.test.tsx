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

function useLocalProgressOnly() {
  vi.mocked(database.canUseDatabase).mockReturnValue(false);
}

beforeEach(() => {
  vi.spyOn(Math, "random").mockReturnValue(FORCE_TRANSLATION);
  vi.mocked(database.canUseDatabase).mockReturnValue(true);
  // The component now actually awaits listVocabQuizAttempts on every mount
  // (previously it fired the call but didn't block on it, so a
  // mockResolvedValueOnce a test queued and never triggered could sit
  // unconsumed and leak into a later test's mount). Reset to this file's
  // plain default before each test so a earlier test's queued one-time
  // reply can't bleed into the next.
  vi.mocked(database.listVocabQuizAttempts).mockReset().mockResolvedValue([]);
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

describe("StoryVocabQuiz star tiers", () => {
  const entries = [
    { word: "一", translation: "one", pinyin: "yī" },
    { word: "二", translation: "two", pinyin: "èr" },
    { word: "三", translation: "three", pinyin: "sān" },
    { word: "四", translation: "four", pinyin: "sì" },
    { word: "五", translation: "five", pinyin: "wǔ" },
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

  it("locks tiers 2 and 3 until the previous star is earned, keeping Review available", async () => {
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    expect(screen.getByRole("button", { name: /Round 1/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Round 2/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Round 3/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Review/ })).toBeEnabled();
  });

  it("unlocks tier 2 (but not 3) once the story has 1 star recorded locally", async () => {
    const { recordLocalStars } = await import("../../utils/quizTiers");
    useLocalProgressOnly();
    recordLocalStars("s1", 1);
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    expect(screen.getByRole("button", { name: /Round 2/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Round 3/ })).toBeDisabled();
  });

  it("mirrors a database-derived three-star result locally for the next activity view", async () => {
    vi.mocked(database.listVocabQuizAttempts).mockResolvedValueOnce([
      { mode: "tier1", correctCount: 20, totalQuestions: 20 },
      { mode: "tier2", correctCount: 22, totalQuestions: 22 },
      { mode: "tier3", correctCount: 25, totalQuestions: 25 },
    ] as any);

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    const { loadLocalStars } = await import("../../utils/quizTiers");
    await waitFor(() => expect(loadLocalStars("s1")).toBe(3));
    expect(screen.getByRole("button", { name: /Round 3/ })).toBeEnabled();
  });

  it("does not let stale local stars mark rounds complete after an authoritative empty database result", async () => {
    const { recordLocalStars } = await import("../../utils/quizTiers");
    recordLocalStars("s1", 3);
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Round 1/ })).not.toHaveClass("is-earned");
    });
    expect(screen.getByRole("button", { name: /Round 2/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Round 3/ })).toBeDisabled();
  });

  it("does not count legacy draft attempts after approved assessment material is attached", async () => {
    vi.mocked(database.listVocabQuizAttempts).mockResolvedValueOnce([
      {
        mode: "tier1",
        correctCount: 20,
        totalQuestions: 20,
        questionResults: [{ bktValidationStatus: "DRAFT" }],
      },
      {
        mode: "tier2",
        correctCount: 22,
        totalQuestions: 22,
        questionResults: [{ bktValidationStatus: "DRAFT" }],
      },
      {
        mode: "tier3",
        correctCount: 25,
        totalQuestions: 25,
        questionResults: [{ bktValidationStatus: "DRAFT" }],
      },
    ] as any);
    const approvedEntries = entries.map((entry) => ({
      ...entry,
      bktValidationStatus: "APPROVED" as const,
    }));

    render(<StoryVocabQuiz entries={approvedEntries} onDone={vi.fn()} storyId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    expect(screen.getByRole("button", { name: /Round 1/ })).not.toHaveClass("is-earned");
    expect(screen.getByRole("button", { name: /Round 2/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Round 3/ })).toBeDisabled();
  });

  it("keeps practice locked until the learner earns all three stars", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    const onDone = vi.fn();
    render(
      <StoryVocabQuiz entries={entries} onDone={onDone} onComplete={onComplete} storyId="s1" />,
    );
    await screen.findByRole("group", { name: "Quiz mode" });

    await user.click(screen.getByRole("button", { name: /Round 1/ }));
    expect(screen.getByText(/Question 1 of 5/)).toBeInTheDocument();
    await playTierRun(user, 5, 5);

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const summary: VocabQuizSummary = onComplete.mock.calls[0][0];
    expect(summary.mode).toBe("tier1");
    expect(summary.totalQuestions).toBe(5);
    expect(summary.correctCount).toBe(5);

    const { loadLocalStars } = await import("../../utils/quizTiers");
    expect(loadLocalStars("s1")).toBe(1);

    // One star isn't enough for practice yet — the summary celebrates and
    // dangles tier 2 as the way in.
    expect(screen.queryByRole("button", { name: /Continue to practice/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Challenge Round 2/ }));
    expect(screen.getByText(/Question 1 of 5/)).toBeInTheDocument();
    await playTierRun(user, 5, 5);

    // ⭐⭐ earned: tier 3 becomes the final gate; practice stays locked.
    expect(loadLocalStars("s1")).toBe(2);
    expect(onComplete).toHaveBeenCalledTimes(2);
    expect(onComplete.mock.calls[1][0].mode).toBe("tier2");
    expect(screen.queryByRole("button", { name: /Continue to practice/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Challenge Round 3/ }));
    await playTierRun(user, 5, 5);

    expect(loadLocalStars("s1")).toBe(3);
    expect(onComplete).toHaveBeenCalledTimes(3);
    expect(onComplete.mock.calls[2][0].mode).toBe("tier3");
    expect(screen.getByRole("button", { name: /Continue to practice/ })).toBeInTheDocument();
    // A 67-question UI walk legitimately outlasts the 5s default timeout.
  }, 20_000);

  it("failing tier 1 near the threshold shows the near-miss gap and a Try again button, without unlocking practice", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onComplete={onComplete} storyId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    await user.click(screen.getByRole("button", { name: /Round 1/ }));
    await playTierRun(user, 5, 3);

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    // The original 14/20 pass ratio scales to 4/5: one more would pass.
    expect(screen.getByText(/1 more/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Continue to practice/ })).not.toBeInTheDocument();
    // A quiet exit back to the tier ladder exists so the student is never
    // trapped between retrying and nothing.
    expect(screen.getByRole("button", { name: /Back to menu/ })).toBeInTheDocument();

    // Try again immediately restarts the same tier as a fresh scored run.
    await user.click(screen.getByRole("button", { name: /Try again/ }));
    expect(screen.getByText(/Question 1 of 5/)).toBeInTheDocument();
  });

  it("does not let a legacy completion flag bypass the three-star requirement", async () => {
    const user = userEvent.setup();
    render(
      <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s1" />,
    );
    await screen.findByRole("group", { name: "Quiz mode" });

    await user.click(screen.getByRole("button", { name: /Round 1/ }));
    await playTierRun(user, 5, 0);

    expect(screen.queryByRole("button", { name: /Continue to practice/ })).not.toBeInTheDocument();
  });

  it("tier 3 runs against a 150-second overall countdown and ends at the cap", async () => {
    const { recordLocalStars } = await import("../../utils/quizTiers");
    useLocalProgressOnly();
    recordLocalStars("s1", 2);
    const onComplete = vi.fn();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onComplete={onComplete} storyId="s1" />);
    // Settle the initial data-load gate on real timers — testing-library's
    // polling can't progress once fake timers replace setTimeout, so fake
    // timers must not switch on until after this resolves.
    await screen.findByRole("group", { name: "Quiz mode" });
    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole("button", { name: /Round 3/ }));
      expect(screen.getByLabelText("150 seconds left")).toBeInTheDocument();

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
    const { recordLocalStars } = await import("../../utils/quizTiers");
    useLocalProgressOnly();
    const user = userEvent.setup();
    const aiEntries = entries.map((e) => ({
      ...e,
      aiDistractors: ["ai-trap-a", "ai-trap-b", "ai-trap-c"],
    }));

    const { unmount } = render(<StoryVocabQuiz entries={aiEntries} onDone={vi.fn()} storyId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(screen.getByRole("button", { name: /Round 1/ }));
    for (const button of optionButtons()) {
      expect(button.textContent).not.toMatch(/ai-trap/);
    }
    unmount();

    recordLocalStars("s1", 1);
    render(<StoryVocabQuiz entries={aiEntries} onDone={vi.fn()} storyId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(screen.getByRole("button", { name: /Round 2/ }));
    expect(optionButtons().some((b) => /ai-trap/.test(b.textContent ?? ""))).toBe(true);
  });

  it("tier 2 pinyin questions use tone-trap distractors (same syllables, different tone)", async () => {
    const { recordLocalStars } = await import("../../utils/quizTiers");
    useLocalProgressOnly();
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
    await screen.findByRole("group", { name: "Quiz mode" });

    await user.click(screen.getByRole("button", { name: /Round 2/ }));
    const options = optionButtons().map((b) => b.textContent);
    expect(options.length).toBeGreaterThan(1);
    const strip = (s: string) => s.normalize("NFD").replace(/\p{Mn}/gu, "");
    for (const option of options) {
      expect(strip(option!)).toBe("he cha");
    }
  });

  it("tier 2 listening questions speak the word and are answered by picking the heard word", async () => {
    const { recordLocalStars } = await import("../../utils/quizTiers");
    useLocalProgressOnly();
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
            { word: "喝茶", translation: "drink tea", pinyin: "hē chá" },
            { word: "餐廳", translation: "restaurant", pinyin: "cān tīng" },
          ]}
          onDone={vi.fn()}
          storyId="s1"
        />,
      );
    await screen.findByRole("group", { name: "Quiz mode" });

      await user.click(screen.getByRole("button", { name: /Round 2/ }));
      // The planner keeps future Chinese-word answers out of earlier
      // options, so the first item is pinyin; listening becomes safe once
      // that first concept has already been tested.
      const firstWord = screen.getByRole("heading").textContent!;
      const firstPinyin = firstWord === "喝茶" ? "hē chá" : "cān tīng";
      await user.click(screen.getByRole("button", { name: firstPinyin }));
      await user.click(screen.getByRole("button", { name: /Next question/ }));
      await waitFor(() => expect(speak).toHaveBeenCalled());
      const spokenWord = speak.mock.calls[0][0].text;

      // The prompt hides the word (it IS the answer) behind a replay button.
      expect(screen.getByRole("button", { name: /Play the word/ })).toBeInTheDocument();
      const correctButton = optionButtons().find((b) => b.textContent === spokenWord)!;
      await user.click(correctButton);
      expect(correctButton.querySelector(".app-icon")).toBeInTheDocument();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("tier 1 reverse questions show the translation and offer Chinese words as options", async () => {
    // With >=2 entries, reverse is the last available kind at tier 1.
    vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    const user = userEvent.setup();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    await user.click(screen.getByRole("button", { name: /Round 1/ }));
    const firstWord = screen.getByRole("heading").textContent!;
    await user.click(
      screen.getByRole("button", {
        name: entries.find((entry) => entry.word === firstWord)!.pinyin,
      }),
    );
    await user.click(screen.getByRole("button", { name: /Next question/ }));
    const prompt = screen.getByRole("heading").textContent!;
    expect(Object.values(translationByWord)).toContain(prompt);

    const expectedWord = Object.keys(translationByWord).find(
      (w) => translationByWord[w] === prompt,
    )!;
    const correctButton = optionButtons().find((b) => b.textContent === expectedWord)!;
    await user.click(correctButton);
    expect(correctButton.querySelector(".app-icon")).toBeInTheDocument();
  });
});
