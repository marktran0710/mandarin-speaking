import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithRetry } = vi.hoisted(() => ({ fetchWithRetry: vi.fn() }));

vi.mock("@shared/api/client", () => ({
  BACKEND_URL: "http://backend.test",
  clientRoleHeader: vi.fn(() => "student"),
  fetchWithRetry,
  REQUEST_TIMEOUT_MS: 15_000,
  VOCAB_GENERATION_RETRY_STATUSES: [],
}));

import { getStoryReferenceData, listCustomStories } from "./stories-submissions";

describe("story list + reference data requests", () => {
  beforeEach(() => {
    fetchWithRetry.mockReset();
    fetchWithRetry.mockImplementation(async () => new Response(JSON.stringify([]), { status: 200 }));
  });

  it("keeps the full list by default and asks for the slim one on request", async () => {
    await listCustomStories();
    expect(fetchWithRetry.mock.calls[0][0]).toBe("http://backend.test/api/custom-stories");

    await listCustomStories({ includeReferenceData: false });
    expect(fetchWithRetry.mock.calls[1][0]).toBe("http://backend.test/api/custom-stories?include_reference_data=false");
  });

  it("loads one story's reference data by encoded id", async () => {
    fetchWithRetry.mockImplementation(async () => new Response(JSON.stringify({ storyId: "a b", frames: [{}] }), { status: 200 }));
    const data = await getStoryReferenceData("a b");
    expect(fetchWithRetry.mock.calls[0][0]).toBe("http://backend.test/api/custom-stories/a%20b/reference-data");
    expect(data.frames).toHaveLength(1);
  });

  it("rejects when the story's reference data cannot be loaded", async () => {
    fetchWithRetry.mockImplementation(async () => new Response("{}", { status: 404 }));
    await expect(getStoryReferenceData("missing")).rejects.toThrow(/reference data/i);
  });
});
