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
