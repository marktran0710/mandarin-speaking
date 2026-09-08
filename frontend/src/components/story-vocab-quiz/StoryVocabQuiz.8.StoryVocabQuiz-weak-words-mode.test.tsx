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
  // Clear call history so per-test exact-count / call-index assertions on the
  // recorder mock are not disturbed by an earlier test that answered a question.
  vi.mocked(database.recordVocabQuizResponse).mockClear();
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
    expect(weakWordsRegion).toHaveTextContent("Words you miss will show up here to review.");
    expect(screen.queryByRole("button", { name: /Weak words/ })).not.toBeInTheDocument();
  });

  it("drops a missed word from the interim review once its mastery crosses the threshold", async () => {
    const weakWords = [] as database.VocabWeakWordsResult;
    Object.defineProperty(weakWords, "diagnostic", {
      value: { unlocked: false, requiredDiagnosticQuizzes: 3, completedDiagnosticQuizzes: 0 },
    });
    Object.defineProperty(weakWords, "mastery", {
      value: [
        // Missed once and still weak → stays in the interim review.
        { wordId: "w1", word: "一", pLearned: 0.3, status: "UNASSESSED", observationCount: 1, correctCount: 0, incorrectCount: 1 },
        // Missed once but since relearned (p >= 0.95) → drops off.
        { wordId: "w3", word: "三", pLearned: 0.98, status: "MASTERED", observationCount: 4, correctCount: 3, incorrectCount: 1 },
      ],
    });
    vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(weakWords);
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });
    await waitFor(() => expect(database.getVocabQuizWeakWords).toHaveBeenCalled());

    // Exactly one word ("一") remains; the mastered "三" is gone.
    const card = await screen.findByRole("button", { name: /Review your misses \(1\)/ });
    expect(card).toBeInTheDocument();
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
    expect(weakWordsButton).not.toHaveTextContent("where");
    await userEvent.setup().click(weakWordsButton);
    expect(await screen.findByRole("heading", { name: "哪裡 / 哪兒" })).toBeInTheDocument();
  });

  it("records weak-words practice under the stable word id so mastery accrues to the same concept the diagnostic used", async () => {
    const weakWords = ["哪裡"] as database.VocabWeakWordsResult;
    Object.defineProperty(weakWords, "priorityReview", {
      value: [{
        wordId: "MC1_003",
        word: "哪裡",
        meaning: "where",
        pLearned: 0.2,
        status: "NEEDS_REVIEW",
        observationCount: 3,
        correctCount: 0,
        incorrectCount: 3,
      } satisfies database.VocabPriorityReviewWord],
    });
    vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(weakWords);
    const user = userEvent.setup();

    render(
      <StoryVocabQuiz
        entries={[{ word: "哪裡 / 哪兒", translation: "where", wordId: "MC1_003" }]}
        onDone={vi.fn()}
        storyId="story-1"
        studentId="s1"
      />,
    );
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(await screen.findByRole("button", { name: /Weak words \(1\)/ }));
    await screen.findByRole("heading", { name: "哪裡 / 哪兒" });
    await user.click(optionButtons()[0]);

    await waitFor(() => expect(database.recordVocabQuizResponse).toHaveBeenCalled());
    const payload = vi.mocked(database.recordVocabQuizResponse).mock.calls.at(-1)![0];
    const recorded = payload.questionResults.at(-1)!;
    // The diagnostic recorded this word under "MC1_003"; practice must too, or
    // the correct answers land on a different concept ("哪裡 / 哪兒") and the
    // weak word never leaves the list.
    expect(recorded.conceptId).toBe("MC1_003");
  });

  it("lets a student re-practice a mastered word from the mastered list", async () => {
    const user = userEvent.setup();
    const lesson = [
      { word: "貴", translation: "expensive", wordId: "MC1_108" },
      { word: "便宜", translation: "cheap", wordId: "MC1_105" },
      { word: "商店", translation: "shop", wordId: "MC1_102" },
      { word: "顏色", translation: "color", wordId: "MC1_104" },
    ];
    const weakWords = [] as database.VocabWeakWordsResult;
    Object.defineProperty(weakWords, "diagnostic", {
      value: { unlocked: true, requiredDiagnosticQuizzes: 3, completedDiagnosticQuizzes: 3 },
    });
    Object.defineProperty(weakWords, "mastery", {
      value: [
        { wordId: "MC1_108", word: "貴", meaning: "expensive", pLearned: 0.98, status: "MASTERED", observationCount: 4, correctCount: 4, incorrectCount: 0 },
      ],
    });
    vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(weakWords);

    render(<StoryVocabQuiz entries={lesson} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });
    await waitFor(() => expect(database.getVocabQuizWeakWords).toHaveBeenCalled());

    // The mastered word is tappable — even though it left the weak-word list.
    await user.click(await screen.findByRole("button", { name: /Practice 貴/ }));

    // A real single-word practice question, with distractors drawn from the
    // whole lesson (more than one option).
    expect(await screen.findByRole("heading", { name: "貴" })).toBeInTheDocument();
    expect(optionButtons().length).toBeGreaterThan(1);

    // Answering records it under the stable wordId, so BKT accrues to the same
    // concept and a wrong answer can pull it back into the weak-word list.
    await user.click(optionButtons()[0]);
    await waitFor(() => expect(database.recordVocabQuizResponse).toHaveBeenCalled());
    const payload = vi.mocked(database.recordVocabQuizResponse).mock.calls.at(-1)![0];
    expect(payload.mode).toBe("weak_words");
    expect(payload.questionResults.at(-1)!.conceptId).toBe("MC1_108");
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

  it("records personalized answers immediately so strengthen progress can refresh", async () => {
    const weakWords = ["一"] as database.VocabWeakWordsResult;
    vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(weakWords);
    const user = userEvent.setup();

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(screen.getByRole("button", { name: /Weak words \(1\)/ }));
    await answerCurrentQuestion(user, false);

    await waitFor(() => expect(database.recordVocabQuizResponse).toHaveBeenCalled());
    const calls = vi.mocked(database.recordVocabQuizResponse).mock.calls;
    const partial = calls[calls.length - 1]![0];
    expect(partial.mode).toBe("weak_words");
    expect(partial.questionResults).toHaveLength(1);
    expect(partial.questionResults[0].correct).toBe(false);
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
    expect(weakWordsButton).toHaveTextContent("This story's weak words, starting with the ones you know least.");
    expect(
      within(weakWordsButton).queryByText("Only quizzes the words you got wrong last time."),
    ).not.toBeInTheDocument();
    await user.click(weakWordsButton);

    // The round-progress bar shares the "第 X / Y 題" denominator (the round's
    // question count) rather than the lesson-wide strengthen goal, so the two
    // counters stay in sync — this round has 2 weak words → 2 questions.
    expect(screen.getByRole("region", { name: "Practice round progress" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "0 of 2 questions answered" })).toBeInTheDocument();

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
    expect(weakWordsButton).not.toHaveTextContent("1 observations");
    expect(weakWordsButton).not.toHaveTextContent("一");
    expect(getWeakWords).toHaveBeenCalledTimes(2);
  });
});

