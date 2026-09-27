import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithRetry } = vi.hoisted(() => ({ fetchWithRetry: vi.fn() }));

vi.mock("@shared/api/client", () => ({
  BACKEND_URL: "http://backend.test",
  clientRoleHeader: vi.fn(() => "student"),
  fetchWithRetry,
  REQUEST_TIMEOUT_MS: 15_000,
  VOCAB_GENERATION_RETRY_STATUSES: [],
}));

import { listVocabQuizAttempts } from "./quiz-analytics";

describe("listVocabQuizAttempts since_days scoping", () => {
  beforeEach(() => {
    fetchWithRetry.mockReset();
    fetchWithRetry.mockImplementation(async () => new Response(JSON.stringify([]), { status: 200 }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("omits since_days by default, so student pages keep seeing full history", async () => {
    await listVocabQuizAttempts("story-1", { studentId: "s1" });
    expect(fetchWithRetry).toHaveBeenLastCalledWith(
      "http://backend.test/api/vocab-quiz-attempts?story_id=story-1&student_id=s1",
    );
  });

  it("forwards sinceDays as since_days for callers that want a bounded window", async () => {
    await listVocabQuizAttempts(undefined, undefined, { includeResults: false, sinceDays: 180 });
    expect(fetchWithRetry).toHaveBeenLastCalledWith(
      "http://backend.test/api/vocab-quiz-attempts?include_results=false&since_days=180",
    );
  });
});
