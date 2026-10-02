import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "@entities/topic";
import type { VocabAssessmentQuestion, VocabQuizEntry } from "@entities/vocabulary";
import { createVocabQuizAttempt, recordVocabQuizResponse } from "../../../services/database";
import VocabularyQuizPage from "../VocabularyQuizPage";
import { correctAnswer, useQuizSession } from "./useQuizSession";

const recordLessonEvent = vi.hoisted(() => vi.fn());
const reviewState = vi.hoisted(() => ({
  targetDimension: null as "context" | null,
  dueWords: [] as Array<{ wordId: string; word: string; observationCount: number; seenQuestionTypes: string[] }>,
}));

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
vi.mock("../model/lesson-vocab-progress", () => ({ saveLessonAttempt: vi.fn() }));
vi.mock("./useQuizSessionData", async () => {
  const { useState } = await import("react");
  return {
    useQuizSessionData: () => {
      const [stars, setStars] = useState(0);
      return {
        stars, setStars, setAttempts: vi.fn(), recordLessonEvent,
        priorityReviewWords: reviewState.targetDimension ? [{
          wordId: "word-1", word: "word-1",
          vocabularyState: { practice: { nextDimension: reviewState.targetDimension } },
        }] : [], weakWords: [], masteryWords: [], strongWords: [],
        dueWords: reviewState.dueWords, sessionReady: true,
        refreshReview: vi.fn(async () => undefined),
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
    return {
      word, wordId: word, translation, bktValidationStatus: "APPROVED",
      assessmentQuestions: [assessment, {
        ...assessment,
        questionId: `${word}-round2`, round: 2, tier: "tier2",
        questionType: "character_to_pinyin_typing", answerFormat: "free_text",
        prompt: `Type the pinyin of ${word}.`, options: [], correctAnswer: "cí", acceptedAnswers: ["cí"],
      }],
    };
  });
}

function loadSession(count: number, mode: "tier1" | "tier2" = "tier1") {
  const entries = makeEntries(count);
  const onComplete = vi.fn();
  const session = renderHook(() => useQuizSession({ entries, storyId: "lesson-1", level: "easy", studentId: "student-1", onComplete }));
  act(() => session.result.current.startTier(mode));
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
  reviewState.targetDimension = null;
  reviewState.dueWords = [];
  vi.mocked(createVocabQuizAttempt).mockResolvedValue(undefined as never);
});

describe("quiz answer and completion boundaries", () => {
  it.each([
    [3, "basic_meaning_mcq"],
    [4, "character_to_pinyin_typing"],
    [5, "context_cloze_mcq"],
    [6, "basic_meaning_mcq"],
  ])("starts maintenance using server observation count %s to select %s", (observationCount, expectedKind) => {
    const entries = makeEntries(1);
    const meaning = entries[0].assessmentQuestions![0];
    entries[0].assessmentQuestions!.push({
      ...meaning, questionId: "word-1-round3", round: 3, tier: "tier3", questionType: "context_cloze_mcq",
    });
    reviewState.dueWords = [{
      wordId: "word-1", word: "word-1", observationCount: Number(observationCount),
      seenQuestionTypes: ["basic_meaning_mcq", "character_to_pinyin_typing", "context_cloze_mcq"],
    }];
    const { result } = renderHook(() => useQuizSession({ entries, storyId: "lesson-1", level: "easy", studentId: "student-1" }));
    act(() => result.current.startDueReview());
    expect(result.current.mode).toBe("maintenance_review");
    expect(result.current.question?.kind).toBe("assessment");
    if (result.current.question?.kind !== "assessment") throw new Error("Expected published maintenance item");
    expect(result.current.question.assessment.questionType).toBe(expectedKind);
    expect(recordLessonEvent).not.toHaveBeenCalledWith("personalized_started", expect.anything());
  });

  it.each([false, true])("blocks targeted practice before any round starts (empty bank: %s)", (emptyBank) => {
    const target: VocabQuizEntry = { ...makeEntries(1)[0], bktNextDimension: "context" };
    if (emptyBank) target.assessmentQuestions = [];
    const { result } = renderHook(() => useQuizSession({ entries: [target], storyId: "lesson-1", level: "easy", studentId: "student-1" }));
    act(() => result.current.practiceWord(target));
    expect(result.current.practiceError).toContain("no published context question");
    expect(result.current.screen).toBe("mode-select");
    expect(result.current.mode).toBeNull();
    expect(result.current.question).toBeUndefined();
    expect(recordLessonEvent).not.toHaveBeenCalled();
    expect(recordVocabQuizResponse).not.toHaveBeenCalled();
    expect(createVocabQuizAttempt).not.toHaveBeenCalled();

    // A later valid attempt clears the error and selects the requested dimension.
    act(() => result.current.practiceWord({ ...makeEntries(1)[0], bktNextDimension: "pinyin" }));
    expect(result.current.practiceError).toBeNull();
    expect(result.current.screen).toBe("quiz");
    expect(result.current.question.kind === "assessment" && result.current.question.assessment.questionType).toBe("character_to_pinyin_typing");
  });

  it.each([true, false])("advances directly after an answer (correct: %s)", (correct) => {
    const { result } = loadSession(2);
    const answer = correct ? correctAnswer(result.current.question) : "wrong";
    act(() => result.current.choose(answer));

    expect(result.current.index).toBe(1);
    expect(result.current.selected).toBeNull();
    expect(result.current.results).toHaveLength(1);
    expect(result.current.results[0]).toMatchObject({ selectedAnswer: answer, correct });
    expect(result.current.results[0].hintUsed).toBeUndefined();
    expect(result.current.results[0].retryCorrect).toBeUndefined();
    expect(recordVocabQuizResponse).toHaveBeenCalledTimes(1);
  });

  it("advances after a typed pinyin answer and records its original score", () => {
    const { result } = loadSession(2, "tier2");
    act(() => result.current.choose("ci2"));
    expect(result.current.index).toBe(1);
    expect(result.current.selected).toBeNull();
    expect(result.current.results).toHaveLength(1);
    expect(result.current.results[0]).toMatchObject({ selectedAnswer: "ci2", correct: true, questionKind: "character_to_pinyin_typing" });
    expect(recordVocabQuizResponse).toHaveBeenCalledTimes(1);
  });

  it("keeps the final answer locked while the completed attempt is saving", async () => {
    const save = deferredSave();
    const { result, onComplete } = loadSession(16);
    for (let index = 0; index < 16; index += 1) {
      act(() => result.current.choose(correctAnswer(result.current.question)));
    }

    expect(result.current.screen).toBe("quiz");
    expect(result.current.results).toHaveLength(16);
    for (let retry = 0; retry < 3; retry += 1) {
      act(() => result.current.choose("wrong"));
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
    expect(result.current.selected).toBeNull();
    expect(result.current.index).toBe(1);
    expect(recordVocabQuizResponse).toHaveBeenCalledTimes(1);
  });

  it("does not reuse answer handlers from the previous question", () => {
    const { result } = loadSession(3);
    expect(result.current.index).toBe(0);
    const choose = result.current.choose;
    act(() => result.current.choose(correctAnswer(result.current.question)));
    act(() => { choose("wrong"); choose("wrong"); });
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

it("shows a visible missing-dimension error and keeps the practice menu open", () => {
  reviewState.targetDimension = "context";
  const topic: Topic = {
    id: "lesson-1", name: "Lesson", description: "", skillFocus: "conversation", images: [], vocabulary: {},
    vocabAssessment: makeEntries(1).flatMap((entry) => entry.assessmentQuestions ?? []),
  };
  render(<VocabularyQuizPage topic={topic} lessonLabel="Lesson" onFinished={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "練習需要加強的詞語" }));
  expect(screen.getByRole("alert")).toHaveTextContent("no published context question");
  expect(screen.getByRole("button", { name: "練習需要加強的詞語" })).toBeInTheDocument();
  expect(recordLessonEvent).not.toHaveBeenCalled();
  expect(recordVocabQuizResponse).not.toHaveBeenCalled();
});

it("shows 16/16 and a neutral saving state until persistence finishes", async () => {
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
  }

  expect(screen.queryByRole("button", { name: "提交答案" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "儲存中" })).toBeDisabled();
  expect(container.querySelector(".sa-quiz__feedback")).not.toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "答案選項" })).not.toBeInTheDocument();
  expect(container.querySelector(".sa-quiz__stats")).toHaveTextContent("16 / 16");
  expect(createVocabQuizAttempt).toHaveBeenCalledTimes(1);
  await act(async () => { save.resolve(); await save.promise; });
  await waitFor(() => expect(container.querySelector(".sa-quiz__result-copy")).toHaveTextContent("16 / 16"));
});

it("advances after each answer without exposing correctness or disabling choices", () => {
  const topic: Topic = {
    id: "lesson-1", name: "Lesson", description: "", skillFocus: "conversation", images: [], vocabulary: {},
    vocabAssessment: makeEntries(3).flatMap((entry) => entry.assessmentQuestions ?? []),
  };
  const { container } = render(<VocabularyQuizPage topic={topic} lessonLabel="Lesson" onFinished={vi.fn()} />);
  fireEvent.click(screen.getAllByRole("button", { name: "開始" })[0]);

  const firstWord = container.querySelector("[data-verification-word]")?.getAttribute("data-verification-word");
  const firstAnswer = topic.vocabAssessment?.find((question) => question.targetWord === firstWord)?.correctAnswer;
  const incorrectOption = screen.getAllByRole("button", { name: /^選項 / })
    .find((button) => !button.getAttribute("aria-label")?.endsWith(`：${firstAnswer}`))!;
  fireEvent.click(incorrectOption);
  fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
  expect(screen.getByRole("progressbar", { name: "測驗進度" })).toHaveAttribute("aria-valuenow", "1");
  screen.getAllByRole("button", { name: /^選項 / }).forEach((button) => expect(button).not.toBeDisabled());
  expect(container.querySelector(".sa-quiz__feedback, .sa-quiz__hint, .is-rejected")).not.toBeInTheDocument();
  expect(screen.queryByText("正確率")).not.toBeInTheDocument();
  expect(container.querySelector(".sa-quiz__question-map .is-correct, .sa-quiz__question-map .is-incorrect")).not.toBeInTheDocument();
  expect(screen.getByRole("listitem", { name: "第 1 題，已完成" })).toHaveTextContent("1");
  expect(screen.getByRole("listitem", { name: "第 2 題，目前題目" })).toHaveAttribute("aria-current", "step");

  const word = container.querySelector("[data-verification-word]")?.getAttribute("data-verification-word");
  const answer = topic.vocabAssessment?.find((question) => question.targetWord === word)?.correctAnswer;
  fireEvent.click(screen.getByRole("button", { name: new RegExp(`${answer}$`) }));
  fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
  expect(screen.getByRole("progressbar", { name: "測驗進度" })).toHaveAttribute("aria-valuenow", "2");
  expect(container.querySelector(".sa-quiz__feedback")).not.toBeInTheDocument();
  expect(screen.getByRole("listitem", { name: "第 2 題，已完成" })).toHaveClass("is-done");
  expect(screen.getByRole("listitem", { name: "第 3 題，目前題目" })).toHaveAttribute("aria-current", "step");
});
