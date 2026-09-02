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

  it("shows an empty weak-words component when there are no persisted weak words", async () => {
    const emptyWeakWords = [] as database.VocabWeakWordsResult;
    Object.defineProperty(emptyWeakWords, "diagnostic", {
      value: { unlocked: false, requiredDiagnosticQuizzes: 3, completedDiagnosticQuizzes: 0 },
    });
    vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(emptyWeakWords);
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    await waitFor(() => expect(database.getVocabQuizWeakWords).toHaveBeenCalled());
    const weakWordsRegion = screen.getByRole("region", { name: "Weak words" });
    expect(weakWordsRegion).toHaveTextContent("No weak words yet. Complete a quiz to build your review list.");
    expect(screen.queryByRole("button", { name: /Weak words/ })).not.toBeInTheDocument();
  });

  it("offers a personalized priority-review card and reports it as a real 'weak_words' attempt", async () => {
    const weakWords = ["一", "三"] as database.VocabWeakWordsResult;
    Object.defineProperty(weakWords, "diagnostic", {
      value: { unlocked: false, requiredDiagnosticQuizzes: 3, completedDiagnosticQuizzes: 0 },
    });
    vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(weakWords);
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
    await screen.findByRole("group", { name: "Quiz mode" });

    const weakWordsButton = await screen.findByRole("button", { name: /Weak words \(2\)/ });
    expect(weakWordsButton).toHaveTextContent("A cumulative list across this story's difficulty levels, starting with the words you know least.");
    expect(
      within(weakWordsButton).queryByText("Only quizzes the words you got wrong last time."),
    ).not.toBeInTheDocument();
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

    // Weak-word review does not award the tier stars, so its normal exit is
    // the mode menu rather than the speaking-practice continuation CTA.
    await user.click(screen.getByRole("button", { name: /Back to menu/ }));
    expect(onDone).not.toHaveBeenCalled();
  });
});

