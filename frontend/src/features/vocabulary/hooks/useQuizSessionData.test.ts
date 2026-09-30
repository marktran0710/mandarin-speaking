import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { recordLocalStars } from "@entities/vocabulary";
import { createVocabQuizAttempt, getVocabularyProgression, listVocabQuizAttempts } from "../../../services/database";
import { useQuizSessionData } from "./useQuizSessionData";

vi.mock("../../../utils/studentSession", () => ({ getStudentScopeKey: () => "student-1" }));
vi.mock("../../../utils/researchContext", () => ({ getCachedResearchContext: () => ({ active: false }) }));
vi.mock("../../../utils/measurement", () => ({ createMeasurementEvent: vi.fn(), recordMeasurementEvent: vi.fn() }));
vi.mock("../../../services/database", () => ({
  canUseDatabase: () => true,
  createVocabQuizAttempt: vi.fn(),
  getVocabularyProgression: vi.fn(),
  listVocabQuizAttempts: vi.fn(),
  getVocabQuizWeakWords: vi.fn(async () => []),
  getVocabQuizReviewQueue: vi.fn(async () => ({ queue: [] })),
}));

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  recordLocalStars("lesson-1", 3);
  localStorage.setItem("mandarin-speaking.lesson-vocabulary-progress.v1:student-1:lesson-1", JSON.stringify({
    initialStatuses: {}, attempts: [{ id: "deleted-quiz", mode: "tier3", correctCount: 16, totalQuestions: 16 }],
  }));
  vi.mocked(listVocabQuizAttempts).mockResolvedValue([]);
  vi.mocked(getVocabularyProgression).mockResolvedValue({ storyId: "lesson-1", quizStars: 0, requiredStars: 3, tiers: {} as never, speakingUnlocked: false, conversationAvailable: true, conversationUnlocked: false });
});

function loadSession() {
  return renderHook(() => useQuizSessionData({ entries: [], storyId: "lesson-1", studentId: "student-1", quizIdRef: { current: null } }));
}

it("uses zero server stars and does not repost a deleted local quiz", async () => {
  const { result } = loadSession();
  expect(result.current.stars).toBe(0);
  await waitFor(() => expect(result.current.sessionReady).toBe(true));
  expect(result.current.stars).toBe(0);
  expect(result.current.attempts).toEqual([]);
  expect(createVocabQuizAttempt).not.toHaveBeenCalled();
});

it("keeps the authenticated gate closed when progression cannot be validated", async () => {
  vi.mocked(getVocabularyProgression).mockRejectedValue(new Error("Unavailable"));
  const { result } = loadSession();
  await waitFor(() => expect(result.current.sessionReady).toBe(true));
  expect(result.current.stars).toBe(0);
  expect(createVocabQuizAttempt).not.toHaveBeenCalled();
});

it("starts the attempts and progression reads together instead of chaining them", async () => {
  let resolveAttempts!: (value: never[]) => void;
  vi.mocked(listVocabQuizAttempts).mockReturnValue(new Promise<never[]>((resolve) => { resolveAttempts = resolve; }));
  const { result } = loadSession();

  // Attempts are still pending, yet progression has already been requested.
  await waitFor(() => expect(getVocabularyProgression).toHaveBeenCalledTimes(1));
  expect(result.current.sessionReady).toBe(false);

  resolveAttempts([]);
  await waitFor(() => expect(result.current.sessionReady).toBe(true));
});

it("still opens the screen with 0 stars when attempts fail and progression is in flight", async () => {
  vi.mocked(listVocabQuizAttempts).mockRejectedValue(new Error("Unavailable"));
  vi.mocked(getVocabularyProgression).mockRejectedValue(new Error("Also unavailable"));
  const { result } = loadSession();
  await waitFor(() => expect(result.current.sessionReady).toBe(true));
  expect(result.current.stars).toBe(0);
});

const reviewQueue = () => ({
  unlocked: true, requiredDiagnosticQuizzes: 3, completedDiagnosticQuizzes: 3,
  diagnostic: { status: "COMPLETE" }, diagnosticComplete: true, roundPresence: undefined,
  words: [{ wordId: "w1", word: "學習", reviewRank: 1 }],
  mastery: [{ wordId: "w1", word: "學習" }, { wordId: "w2", word: "朋友" }],
  queue: [
    { wordId: "w2", word: "朋友", reviewReason: "due" },
    { wordId: "w1", word: "學習", reviewReason: "weak" },
  ],
});

it("loads weak words and due words from ONE review-queue request", async () => {
  const { getVocabQuizReviewQueue, getVocabQuizWeakWords } = await import("../../../services/database");
  vi.mocked(getVocabQuizReviewQueue).mockResolvedValue(reviewQueue() as never);
  const { result } = renderHook(() => useQuizSessionData({ entries: [], storyId: "lesson-1", studentId: "student-1", quizIdRef: { current: null } }));
  await waitFor(() => expect(result.current.sessionReady).toBe(true));
  await waitFor(() => expect(result.current.dueWords).toHaveLength(1));

  expect(getVocabQuizReviewQueue).toHaveBeenCalledTimes(1);
  expect(getVocabQuizWeakWords).not.toHaveBeenCalled();
  expect(result.current.weakWords).toEqual(["學習"]);
  expect(result.current.priorityReviewWords.map((word) => word.wordId)).toEqual(["w1"]);
  expect(result.current.masteryWords).toHaveLength(2);
  expect(result.current.diagnosticComplete).toBe(true);
  expect(result.current.dueWords.map((word) => word.wordId)).toEqual(["w2"]);
});

it("refreshReview re-reads both lists with a single further request", async () => {
  const { getVocabQuizReviewQueue } = await import("../../../services/database");
  vi.mocked(getVocabQuizReviewQueue).mockResolvedValue(reviewQueue() as never);
  const { result } = renderHook(() => useQuizSessionData({ entries: [], storyId: "lesson-1", studentId: "student-1", quizIdRef: { current: null } }));
  await waitFor(() => expect(result.current.sessionReady).toBe(true));
  vi.mocked(getVocabQuizReviewQueue).mockClear();

  await result.current.refreshReview();
  expect(getVocabQuizReviewQueue).toHaveBeenCalledTimes(1);
});

it("re-reads after an in-flight read instead of trusting data that predates a saved answer", async () => {
  const { getVocabQuizReviewQueue } = await import("../../../services/database");
  let releaseFirst!: (value: never) => void;
  vi.mocked(getVocabQuizReviewQueue)
    .mockReturnValueOnce(new Promise((resolve) => { releaseFirst = resolve as never; }) as never)
    .mockResolvedValue(reviewQueue() as never);
  const { result } = renderHook(() => useQuizSessionData({ entries: [], storyId: "lesson-1", studentId: "student-1", quizIdRef: { current: null } }));
  await waitFor(() => expect(getVocabQuizReviewQueue).toHaveBeenCalledTimes(1));

  // Two refreshes requested while the first read is still pending share ONE follow-up read.
  const refreshes = Promise.all([result.current.refreshReview(), result.current.refreshReview()]);
  expect(getVocabQuizReviewQueue).toHaveBeenCalledTimes(1);
  releaseFirst(reviewQueue() as never);
  await refreshes;

  expect(getVocabQuizReviewQueue).toHaveBeenCalledTimes(2);
  await waitFor(() => expect(result.current.sessionReady).toBe(true));
});
