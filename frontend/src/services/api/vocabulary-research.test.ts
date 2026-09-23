import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithRetry } = vi.hoisted(() => ({ fetchWithRetry: vi.fn() }));

vi.mock("./client", () => ({
  BACKEND_URL: "http://backend.test",
  fetchWithRetry,
}));

import { getVocabularyResearchContext } from "./vocabulary-research";

describe("getVocabularyResearchContext", () => {
  beforeEach(() => {
    fetchWithRetry.mockReset();
  });

  it("fetches the student-safe context endpoint and returns its body", async () => {
    fetchWithRetry.mockResolvedValue(
      new Response(
        JSON.stringify({
          active: false,
          coreCompletionPolicy: "production_accuracy",
          practiceAvailable: false,
          reviewAvailable: false,
          probeAvailable: false,
        }),
        { status: 200 },
      ),
    );

    const context = await getVocabularyResearchContext();

    expect(fetchWithRetry).toHaveBeenCalledWith(
      "http://backend.test/api/research/vocabulary/context",
      { method: "GET" },
    );
    expect(context.active).toBe(false);
    expect(context.coreCompletionPolicy).toBe("production_accuracy");
  });

  it("throws with the backend's detail message on failure", async () => {
    fetchWithRetry.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not logged in" }), { status: 401 }),
    );

    await expect(getVocabularyResearchContext()).rejects.toThrow("Not logged in");
  });
});
