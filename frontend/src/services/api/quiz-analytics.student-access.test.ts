import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithRetry } = vi.hoisted(() => ({
  fetchWithRetry: vi.fn(async () => new Response(null, { status: 204 })),
}));

vi.mock("./client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./client")>();
  return { ...actual, fetchWithRetry };
});

import { updateVocabularyDistractors } from "./quiz-analytics";

describe("quiz material updates", () => {
  beforeEach(() => {
    fetchWithRetry.mockClear();
    window.history.pushState({}, "", "/");
  });

  it("does not let student quiz completion call teacher-only pool PATCH endpoints", async () => {
    await updateVocabularyDistractors("story-1", [{ frameIndex: 0, wordIndex: 0, distractors: ["x"] }]);

    expect(fetchWithRetry).not.toHaveBeenCalled();
  });

  it("keeps pool PATCH updates available in the teacher app", async () => {
    window.history.pushState({}, "", "/teacher.html");

    await updateVocabularyDistractors("story-1", [{ frameIndex: 0, wordIndex: 0, distractors: ["x"] }]);

    expect(fetchWithRetry).toHaveBeenCalledWith(
      expect.stringContaining("/api/custom-stories/story-1/vocabulary-distractors"),
      expect.objectContaining({ method: "PATCH" }),
    );
  });
});
