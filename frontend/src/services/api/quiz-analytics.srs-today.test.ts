import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithRetry } = vi.hoisted(() => ({ fetchWithRetry: vi.fn() }));
const originalUrl = window.location.href;

vi.mock("@shared/api/client", () => ({
  BACKEND_URL: "http://backend.test",
  clientRoleHeader: vi.fn(() => "student"),
  fetchWithRetry,
  REQUEST_TIMEOUT_MS: 15_000,
  VOCAB_GENERATION_RETRY_STATUSES: [],
}));

import {
  createVocabQuizAttempt,
  getVocabQuizReviewQueue,
  recordVocabQuizResponse,
  type VocabQuizAttempt,
} from "./quiz-analytics";

const attempt: VocabQuizAttempt = {
  id: "review-attempt",
  storyId: "lesson-1",
  studentName: "Student",
  mode: "weak_words",
  completedAt: "2026-09-16T00:00:00Z",
  totalQuestions: 1,
  correctCount: 1,
  totalTimeMs: 900,
  questionResults: [],
};

describe("development SRS today override", () => {
  beforeEach(() => {
    fetchWithRetry.mockReset();
    fetchWithRetry.mockImplementation(async () => new Response(JSON.stringify({ queue: [] }), { status: 200 }));
    vi.stubEnv("DEV", true);
    window.history.replaceState({}, "", "/?today=2026-09-17");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    window.history.replaceState({}, "", originalUrl);
  });

  it("forwards a valid page today parameter to the review queue and review writes", async () => {
    await getVocabQuizReviewQueue("lesson-1", "student-1", { includeAllWeak: true });
    await recordVocabQuizResponse(attempt);
    await createVocabQuizAttempt(attempt);

    expect(fetchWithRetry.mock.calls.map(([url]) => url)).toEqual([
      "http://backend.test/api/students/student-1/review-queue?story_id=lesson-1&include_all=true&today=2026-09-17",
      "http://backend.test/api/vocab-quiz-responses?today=2026-09-17",
      "http://backend.test/api/vocab-quiz-attempts?today=2026-09-17",
    ]);
  });

  it("does not forward malformed values or values outside development", async () => {
    window.history.replaceState({}, "", "/?today=not-a-date");
    await getVocabQuizReviewQueue("lesson-1", "student-1");
    expect(fetchWithRetry).toHaveBeenLastCalledWith("http://backend.test/api/students/student-1/review-queue?story_id=lesson-1");

    vi.stubEnv("DEV", false);
    window.history.replaceState({}, "", "/?today=2026-09-17");
    await recordVocabQuizResponse(attempt);
    expect(fetchWithRetry).toHaveBeenLastCalledWith(
      "http://backend.test/api/vocab-quiz-responses",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
