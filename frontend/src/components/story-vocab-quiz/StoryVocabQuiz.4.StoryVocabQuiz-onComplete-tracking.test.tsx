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
    await screen.findByRole("group", { name: "Quiz mode" });

    await user.click(screen.getByRole("button", { name: /Round 1/ }));

    for (let i = 0; i < entries.length; i += 1) {
      await answerCurrentQuestion(user, true, translationByWord);
      await user.click(screen.getByRole("button", { name: /Next question|See results/ }));
    }

    // Lands on the results screen first — onComplete fires here, but onDone
    // (which tells the caller to move on to practice) waits for the student
    // to explicitly continue past it.
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    expect(onDone).not.toHaveBeenCalled();

    const summary: VocabQuizSummary = onComplete.mock.calls[0][0];
    expect(summary.totalQuestions).toBe(entries.length);
    expect(summary.questionResults).toHaveLength(entries.length);
    expect(summary.correctCount).toBe(entries.length);
    expect(summary.totalTimeMs).toBeGreaterThanOrEqual(0);
    for (const result of summary.questionResults) {
      expect(entries.some((e) => e.word === result.word)).toBe(true);
      expect(result.timeMs).toBeGreaterThanOrEqual(0);
    }

    // Speaking practice opens only after all three stars, so the road to
    // onDone continues through tier 2 and tier 3. Each scored round reports
    // its own onComplete along the way.
    await user.click(screen.getByRole("button", { name: /Challenge Round 2/ }));
    for (let i = 0; i < entries.length; i += 1) {
      await answerCurrentQuestion(user, true, translationByWord);
      await user.click(screen.getByRole("button", { name: /Next question|See results/ }));
    }
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(2));
    expect(onDone).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /Challenge Round 3/ }));
    for (let i = 0; i < entries.length; i += 1) {
      await answerCurrentQuestion(user, true, translationByWord);
      await user.click(screen.getByRole("button", { name: /Next question|See results/ }));
    }
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(3));
    await user.click(screen.getByRole("button", { name: /Continue to practice/ }));
    expect(onDone).toHaveBeenCalledTimes(1);
    // A 42-question UI walk legitimately outlasts the 5s default timeout.
  }, 20_000);

  it("never offers a skip button, in any mode, on the mode-select screen or mid-quiz", async () => {
    const user = userEvent.setup();
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onBack={vi.fn()} />);
    await screen.findByRole("group", { name: "Quiz mode" });

    expect(screen.queryByRole("button", { name: /Skip/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Round 1/ }));
    expect(screen.queryByRole("button", { name: /Skip/ })).not.toBeInTheDocument();
  });

  it("does not offer a Back to activities button from the quiz flow", async () => {
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onBack={vi.fn()} />);
    await screen.findByRole("group", { name: "Quiz mode" });

    expect(screen.queryByRole("button", { name: /Back to activities/ })).not.toBeInTheDocument();
  });
});

