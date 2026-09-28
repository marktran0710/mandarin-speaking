import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "@entities/topic";
import type { VocabAssessmentQuestion, VocabQuizEntry } from "@entities/vocabulary";
import { createVocabQuizAttempt, recordVocabQuizResponse } from "../../../services/database";
import VocabularyQuizPage from "../VocabularyQuizPage";
import { correctAnswer, useQuizSession } from "./useQuizSession";

vi.mock("../../../services/database", () => ({
  canUseDatabase: () => true,
  createVocabQuizAttempt: vi.fn(),
  recordVocabQuizResponse: vi.fn(async () => undefined),
}));
vi.mock("../../../utils/studentSession", () => ({
  getStudentId: () => "student-1",
  getStudentName: () => "Student One",
  getStudentScopeKey: () => "student-1",
  isAdminSession: () => false,
}));
vi.mock("../../../utils/researchContext", () => ({ getCachedResearchContext: () => ({ active: false }) }));
vi.mock("../model/lesson-vocab-progress", () => ({ saveLessonAttempt: vi.fn() }));
vi.mock("./useQuizSessionData", async () => {
  const { useState } = await import("react");
  return {
    useQuizSessionData: () => {
      const [stars, setStars] = useState(0);
      return {
        stars, setStars, setAttempts: vi.fn(), recordLessonEvent: vi.fn(),
        priorityReviewWords: [], weakWords: [], masteryWords: [], strongWords: [],
        dueWords: [], researchDueEntries: [], sessionReady: true,
        refreshWeakWords: vi.fn(async () => undefined), refreshDueWords: vi.fn(async () => undefined),
        studentScope: "student-1",
        lessonProgress: { challenge: { bestScore: 0, attempts: [] } },
      };
    },
  };
});

function makeEntries(count: number): VocabQuizEntry[] {
  return Array.from({ length: count }, (_, index) => {
    const word = `word-${index + 1}`;
    const translation = `meaning-${index + 1}`;
    const assessment: VocabAssessmentQuestion = {
      questionId: `${word}-round1`, wordId: word, targetWord: word,
      pinyin: "ci2", pos: "N", simpleEnglishMeaning: translation,
      round: 1, tier: "tier1", questionType: "basic_meaning_mcq", answerFormat: "single_choice",
      prompt: `Choose the meaning of ${word}.`, options: [translation, "wrong"],
      correctAnswer: translation, acceptedAnswers: [translation], explanation: "",
    };
    return { word, wordId: word, translation, bktValidationStatus: "APPROVED", assessmentQuestions: [assessment] };
  });
}

function loadSession(count: number) {
  const entries = makeEntries(count);
  const onComplete = vi.fn();
  const session = renderHook(() => useQuizSession({ entries, storyId: "lesson-1", level: "easy", studentId: "student-1", onComplete }));
  act(() => session.result.current.startTier("tier1"));
  return { ...session, onComplete };
}

function deferredSave() {
  let resolve!: () => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<void>((saved, failed) => { resolve = saved; reject = failed; });
  vi.mocked(createVocabQuizAttempt).mockReturnValue(promise as never);
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(createVocabQuizAttempt).mockResolvedValue(undefined as never);
});

describe("quiz answer and completion boundaries", () => {
  it("keeps the final answer locked while the completed attempt is saving", async () => {
    const save = deferredSave();
    const { result, onComplete } = loadSession(16);
    for (let index = 0; index < 16; index += 1) {
      act(() => result.current.choose(correctAnswer(result.current.question)));
      act(() => result.current.next());
    }

    expect(result.current.screen).toBe("quiz");
    expect(result.current.results).toHaveLength(16);
    for (let retry = 0; retry < 3; retry += 1) {
      act(() => result.current.choose("wrong"));
      act(() => result.current.next());
    }
    expect(result.current.results).toHaveLength(16);
    expect(result.current.selected).not.toBeNull();
    expect(recordVocabQuizResponse).toHaveBeenCalledTimes(16);
    expect(createVocabQuizAttempt).toHaveBeenCalledTimes(1);

    await act(async () => { save.resolve(); await save.promise; });
    expect(result.current.screen).toBe("summary");
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith(expect.objectContaining({ totalQuestions: 16, correctCount: 16 }));
  });

  it("records only one response when submit is called twice before React renders", () => {
    const { result } = loadSession(2);
    const choose = result.current.choose;
    const answer = correctAnswer(result.current.question);
    act(() => { choose(answer); choose("wrong"); });
    expect(result.current.results).toHaveLength(1);
    expect(result.current.selected).toBe(answer);
    expect(recordVocabQuizResponse).toHaveBeenCalledTimes(1);
  });

  it("does not advance before an answer or reuse handlers from the previous question", () => {
    const { result } = loadSession(3);
    act(() => result.current.next());
    expect(result.current.index).toBe(0);
    act(() => result.current.choose(correctAnswer(result.current.question)));
    const { choose, next } = result.current;
    act(() => { next(); next(); choose("wrong"); });
    expect(result.current.index).toBe(1);
    expect(result.current.selected).toBeNull();
    expect(result.current.results).toHaveLength(1);
    act(() => result.current.choose(correctAnswer(result.current.question)));
    expect(result.current.results).toHaveLength(2);
    expect(recordVocabQuizResponse).toHaveBeenCalledTimes(2);
  });

  it("releases the completion state after a failed save and starts a fresh retry", async () => {
    const save = deferredSave();
    const { result } = loadSession(1);
    act(() => result.current.choose(correctAnswer(result.current.question)));
    act(() => result.current.next());
    await act(async () => { save.reject(new Error("Unavailable")); await save.promise.catch(() => undefined); });
    expect(result.current.screen).toBe("summary");
    act(() => result.current.startTier("tier1"));
    expect(result.current.index).toBe(0);
    expect(result.current.selected).toBeNull();
    expect(result.current.results).toEqual([]);
    act(() => result.current.choose(correctAnswer(result.current.question)));
    expect(result.current.results).toHaveLength(1);
  });
});

it("shows 16/16 and saving feedback on the quiz page until persistence finishes", async () => {
  const save = deferredSave();
  const topic: Topic = {
    id: "lesson-1", name: "Lesson", description: "", skillFocus: "conversation", images: [], vocabulary: {},
    vocabAssessment: makeEntries(16).flatMap((entry) => entry.assessmentQuestions ?? []),
  };
  const { container } = render(<VocabularyQuizPage topic={topic} lessonLabel="Lesson" onFinished={vi.fn()} />);
  fireEvent.click(screen.getAllByRole("button", { name: "開始" })[0]);
  for (let index = 0; index < 16; index += 1) {
    const word = container.querySelector("[data-verification-word]")?.getAttribute("data-verification-word");
    const answer = topic.vocabAssessment?.find((question) => question.targetWord === word)?.correctAnswer;
    fireEvent.click(screen.getByRole("button", { name: new RegExp(`${answer}$`) }));
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
    fireEvent.click(screen.getByRole("button", { name: "下一題" }));
  }

  expect(screen.queryByRole("button", { name: "提交答案" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "儲存中" })).toBeDisabled();
  expect(container.querySelector(".sa-quiz__feedback")).toBeInTheDocument();
  expect(container.querySelector(".sa-quiz__stats")).toHaveTextContent("16 / 16");
  expect(createVocabQuizAttempt).toHaveBeenCalledTimes(1);
  await act(async () => { save.resolve(); await save.promise; });
  await waitFor(() => expect(container.querySelector(".sa-quiz__result-copy")).toHaveTextContent("16 / 16"));
});
