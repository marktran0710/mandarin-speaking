import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  });

  it("walks through one sampled question per lesson, then submits one attempt per lesson", async () => {
    listCustomStories.mockResolvedValue(makeStories());
    render(<PlacementTestPage />);

    expect(await screen.findByText(/1 \/ 2/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("你好-correct"));
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));

    expect(await screen.findByText(/2 \/ 2/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("wrong1"));
    fireEvent.click(screen.getByRole("button", { name: /Finish/ }));

    await waitFor(() => expect(recordVocabQuizResponse).toHaveBeenCalledTimes(2));
    const [call1, call2] = recordVocabQuizResponse.mock.calls.map((call) => call[0]);
    expect([call1.storyId, call2.storyId].sort()).toEqual(["s1", "s2"]);
    for (const call of [call1, call2]) {
      expect(call.mode).toBe("tier1");
      expect(call.studentId).toBe("student-1");
      expect(call.questionResults).toHaveLength(1);
      expect(call.questionResults[0].itemId).toMatch(/_EASY$/);
    }
    const s1Call = call1.storyId === "s1" ? call1 : call2;
    const s2Call = call1.storyId === "s1" ? call2 : call1;
    expect(s1Call.questionResults[0].correct).toBe(true);
    expect(s2Call.questionResults[0].correct).toBe(false);

    expect(await screen.findByText(/1 \/ 2 correct/)).toBeInTheDocument();
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
