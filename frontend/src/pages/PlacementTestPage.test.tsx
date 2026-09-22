import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";
import PlacementTestPage from "./PlacementTestPage";
import type { StoredCustomStory } from "../services/database";

const listCustomStories = vi.fn();
const recordVocabQuizResponse = vi.fn();

vi.mock("../services/database", () => ({
  canUseDatabase: () => true,
  listCustomStories: (...args: unknown[]) => listCustomStories(...args),
  recordVocabQuizResponse: (...args: unknown[]) => recordVocabQuizResponse(...args),
}));

vi.mock("../utils/studentSession", () => ({
  getStudentId: () => "student-1",
  getStudentName: () => "Ada",
}));

function easyQuestion(word: string, wordId: string, storyId: string) {
  return {
    questionId: `${wordId}_EASY`,
    wordId,
    targetWord: word,
    pinyin: "",
    pos: "N",
    simpleEnglishMeaning: word,
    level: "easy" as const,
    difficultyWeight: 1 as const,
    questionType: "basic_meaning_mcq" as const,
    answerFormat: "single_choice" as const,
    prompt: `Choose the correct English meaning of 「${word}」.`,
    options: [`${word}-correct`, "wrong1", "wrong2", "wrong3"],
    correctAnswer: `${word}-correct`,
    acceptedAnswers: [`${word}-correct`],
    explanation: "",
    storyId,
  };
}

function makeStories(): StoredCustomStory[] {
  return [
    { id: "s1", title: "Lesson 1", frames: [], published: true, lessonNumber: 1, vocabAssessment: [easyQuestion("你好", "W1", "s1")] },
    { id: "s2", title: "Lesson 2", frames: [], published: true, lessonNumber: 2, vocabAssessment: [easyQuestion("謝謝", "W2", "s2")] },
  ];
}

describe("PlacementTestPage", () => {
  beforeEach(() => {
    listCustomStories.mockReset();
    recordVocabQuizResponse.mockReset();
    recordVocabQuizResponse.mockResolvedValue(undefined);
  });

  it("shows a friendly empty state when no lesson has a question bank yet", async () => {
    listCustomStories.mockResolvedValue([]);
    render(<PlacementTestPage />);
    expect(await screen.findByText(/No questions available yet/)).toBeInTheDocument();
    expect(screen.getByText(/No questions available yet/).closest(".student-page-shell"))
      .toHaveClass("student-page-shell--assessment");
    expect(screen.getByText(/No questions available yet/).closest(".student-page-body"))
      .toHaveAttribute("data-student-body", "task");
  });

  it("keeps the compact loading state and primary action hierarchy accessible", async () => {
    let resolveStories!: (stories: StoredCustomStory[]) => void;
    listCustomStories.mockReturnValue(new Promise<StoredCustomStory[]>((resolve) => {
      resolveStories = resolve;
    }));
    render(<PlacementTestPage />);

    expect(screen.getByRole("status")).toHaveClass("placement-test-loading");
    const pageShell = screen.getByRole("status").closest(".student-page-shell");
    expect(pageShell).toHaveAttribute("data-student-template", "assessment");
    resolveStories(makeStories());

    const question = await screen.findByRole("heading", { name: /Choose the correct English meaning/ });
    expect(question.closest(".student-page-shell")).toBe(pageShell);
    expect(question).toHaveClass("vocab-quiz-assessment-prompt");
    const next = screen.getByRole("button", { name: /Next question/ });
    expect(next).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /-correct$/ }));
    expect(next).toBeEnabled();
  });

  it("keeps answer feedback neutral until advance, then submits grouped diagnostic attempts", async () => {
    listCustomStories.mockResolvedValue(makeStories());
    render(<PlacementTestPage />);

    expect(await screen.findByText(/1 \/ 2/)).toBeInTheDocument();
    const questionRegion = screen.getByRole("region", { name: "Placement test question" });
    expect(within(questionRegion).getByText("Placement test")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /See what you already know/ })).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Question 1 of 2");

    const selectedAnswer = screen.getByRole("button", { name: /-correct$/ });
    const otherAnswer = screen.getByRole("button", { name: "wrong1" });
    fireEvent.click(selectedAnswer);

    expect(selectedAnswer).toHaveAttribute("aria-pressed", "true");
    expect(selectedAnswer).toHaveClass("vocab-quiz-option-selected");
    expect(otherAnswer).toHaveAttribute("aria-pressed", "false");
    expect(otherAnswer).toHaveClass("vocab-quiz-option-neutral");
    expect(screen.queryByLabelText(/correct answer|incorrect/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Next/ }));

    expect(await screen.findByText(/2 \/ 2/)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Question 2 of 2");
    fireEvent.click(screen.getByText("wrong1"));
    fireEvent.click(screen.getByRole("button", { name: /Finish/ }));

    await waitFor(() => expect(recordVocabQuizResponse).toHaveBeenCalledTimes(2));
    const [call1, call2] = recordVocabQuizResponse.mock.calls.map((call) => call[0]);
    expect([call1.storyId, call2.storyId].sort()).toEqual(["s1", "s2"]);
    for (const call of [call1, call2]) {
      expect(call.mode).toBe("tier1");
      expect(call.studentId).toBe("student-1");
      expect(call.questionResults).toHaveLength(1);
      expect(call.questionResults[0]).toMatchObject({
        itemId: expect.stringMatching(/_EASY$/),
        questionKind: "basic_meaning_mcq",
        roundType: "know_it",
        knowledgeDimension: "meaning",
        activityType: "diagnostic",
        level: "easy",
        baseStoryId: call.storyId,
        lessonId: call.storyId,
        questionIndex: 0,
      });
    }
    const s1Call = call1.storyId === "s1" ? call1 : call2;
    const s2Call = call1.storyId === "s1" ? call2 : call1;
    expect(s1Call.questionResults[0].correct).toBe(true);
    expect(s2Call.questionResults[0].correct).toBe(false);
    expect(s1Call.questionResults[0].selectedAnswer).toBe(s1Call.questionResults[0].correctAnswer);
    expect(s1Call.questionResults[0].presentedOptions).toContain(s1Call.questionResults[0].selectedAnswer);
    expect(s2Call.questionResults[0].presentedOptions).toContain(s2Call.questionResults[0].selectedAnswer);

    expect(await screen.findByRole("heading", { name: /Placement test complete/ })).toBeInTheDocument();
    expect(screen.getByText(/personalize your review/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Placement test results")).not.toBeInTheDocument();
  });

  it("does not block or throw when a lesson submission fails - still reaches the summary", async () => {
    listCustomStories.mockResolvedValue(makeStories());
    recordVocabQuizResponse.mockRejectedValueOnce(new Error("network"));
    render(<PlacementTestPage />);

    fireEvent.click(await screen.findByText("你好-correct"));
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));
    fireEvent.click(await screen.findByText("謝謝-correct"));
    fireEvent.click(screen.getByRole("button", { name: /Finish/ }));

    expect(await screen.findByText(/Placement test complete/)).toBeInTheDocument();
  });
});
