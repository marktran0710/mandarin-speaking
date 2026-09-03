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
    recordVocabQuizResponse: vi.fn(async () => undefined),
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

  it("uses the stable word id when the API display form differs from the CSV form", async () => {
    const weakWords = ["哪裡"] as database.VocabWeakWordsResult;
    Object.defineProperty(weakWords, "priorityReview", {
      value: [{
        wordId: "MC1_003",
        word: "哪裡",
        meaning: "where",
        pLearned: 0.2,
        status: "NEEDS_REVIEW",
        observationCount: 1,
        correctCount: 0,
        incorrectCount: 1,
      } satisfies database.VocabPriorityReviewWord],
    });
    vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(weakWords);

    render(
      <StoryVocabQuiz
        entries={[{ word: "哪裡 / 哪兒", translation: "where", wordId: "MC1_003" }]}
        onDone={vi.fn()}
        storyId="story-1"
        studentId="s1"
      />,
    );
    await screen.findByRole("group", { name: "Quiz mode" });

    const weakWordsButton = await screen.findByRole("button", { name: /Weak words \(1\)/ });
    expect(weakWordsButton).toHaveTextContent("where");
  });

  it("records an eligible answer immediately so the first wrong answer can enter BKT", async () => {
    const user = userEvent.setup();
    const approvedEntries = [
      { word: "一", translation: "one", bktValidationStatus: "APPROVED" as const },
      { word: "二", translation: "two", bktValidationStatus: "APPROVED" as const },
    ];
    render(
      <StoryVocabQuiz
        entries={approvedEntries}
        onDone={vi.fn()}
        storyId="story-1"
        studentId="s1"
      />,
    );
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(screen.getByRole("button", { name: /Round 1/ }));
    await answerCurrentQuestion(user, false);

    await waitFor(() => expect(database.recordVocabQuizResponse).toHaveBeenCalledTimes(1));
    const partial = vi.mocked(database.recordVocabQuizResponse).mock.calls[0][0];
    expect(partial.mode).toBe("tier1");
    expect(partial.questionResults).toHaveLength(1);
    expect(partial.questionResults[0].correct).toBe(false);
    expect(partial.questionResults[0].quizId).toBe(partial.id);
  });

  it("refreshes weak words immediately after the server accepts a diagnostic answer", async () => {
    const initialWords = [] as database.VocabWeakWordsResult;
    const refreshedWords = ["一"] as database.VocabWeakWordsResult;
    const getWeakWords = vi.mocked(database.getVocabQuizWeakWords);
    getWeakWords.mockReset();
    getWeakWords.mockResolvedValueOnce(initialWords).mockResolvedValueOnce(refreshedWords);
    vi.mocked(database.recordVocabQuizResponse).mockClear();
    const user = userEvent.setup();

    render(
      <StoryVocabQuiz
        entries={[{ word: "一", translation: "one", bktValidationStatus: "APPROVED" as const }]}
        onDone={vi.fn()}
        storyId="story-1"
        studentId="s1"
      />,
    );
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(screen.getByRole("button", { name: /Round 1/ }));
    await answerCurrentQuestion(user, false);

    await waitFor(() => expect(database.recordVocabQuizResponse).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(getWeakWords).toHaveBeenCalledTimes(2));
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

  it("refreshes the menu with weak words after a completed diagnostic attempt", async () => {
    const initialWords = [] as database.VocabWeakWordsResult;
    const refreshedWords = ["一"] as database.VocabWeakWordsResult;
    Object.defineProperty(refreshedWords, "priorityReview", {
      value: [{
        wordId: "一", word: "一", pLearned: 0.2, status: "UNASSESSED",
        observationCount: 1, correctCount: 0, incorrectCount: 1,
      }],
    });
    const getWeakWords = vi.mocked(database.getVocabQuizWeakWords);
    getWeakWords.mockReset();
    getWeakWords
      .mockResolvedValueOnce(initialWords)
      .mockResolvedValueOnce(refreshedWords);
    const user = userEvent.setup();

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onComplete={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(screen.getByRole("button", { name: /Round 1/ }));
    for (let index = 0; index < 3; index += 1) {
      await answerCurrentQuestion(user, false);
      await user.click(screen.getByRole("button", { name: /Next question|See results/ }));
    }
    await user.click(screen.getByRole("button", { name: /Back to menu/ }));

    const weakWordsButton = await screen.findByRole("button", { name: /Weak words \(1\)/ });
    expect(weakWordsButton).toHaveTextContent("1 observations");
    expect(getWeakWords).toHaveBeenCalledTimes(2);
  });
});

