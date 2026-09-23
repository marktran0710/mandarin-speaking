import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithRetry } = vi.hoisted(() => ({ fetchWithRetry: vi.fn() }));

vi.mock("./client", () => ({
  BACKEND_URL: "http://backend.test",
  fetchWithRetry,
}));

import { getResearchProbesDue, getVocabularyResearchContext, postResearchProbeResponse } from "./vocabulary-research";

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

describe("getResearchProbesDue", () => {
  beforeEach(() => {
    fetchWithRetry.mockReset();
  });

  it("fetches the due-probes endpoint and returns its questions", async () => {
    fetchWithRetry.mockResolvedValue(
      new Response(
        JSON.stringify({
          questions: [
            { assignmentId: 1, wordId: "生詞", questionType: "mc_translation", prompt: "What does 生詞 mean?", choices: ["A", "B"] },
          ],
        }),
        { status: 200 },
      ),
    );

    const session = await getResearchProbesDue();

    expect(fetchWithRetry).toHaveBeenCalledWith(
      "http://backend.test/api/research/vocabulary/probes/due",
      { method: "GET" },
    );
    expect(session.questions).toHaveLength(1);
    expect(session.questions[0].wordId).toBe("生詞");
  });

  it("throws with the backend's detail message on failure", async () => {
    fetchWithRetry.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not a participant" }), { status: 409 }),
    );

    await expect(getResearchProbesDue()).rejects.toThrow("Not a participant");
  });
});

describe("postResearchProbeResponse", () => {
  beforeEach(() => {
    fetchWithRetry.mockReset();
  });

  it("posts the response and source id and returns the acceptance ack only", async () => {
    fetchWithRetry.mockResolvedValue(
      new Response(JSON.stringify({ accepted: true }), { status: 200 }),
    );

    const result = await postResearchProbeResponse(1, "B", "src-1");

    expect(fetchWithRetry).toHaveBeenCalledWith(
      "http://backend.test/api/research/vocabulary/probes/1/response",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ response: "B", sourceResponseId: "src-1" }),
      },
    );
    expect(result).toEqual({ accepted: true });
  });

  it("throws with the backend's detail message on failure", async () => {
    fetchWithRetry.mockResolvedValue(
      new Response(JSON.stringify({ detail: "No such assignment" }), { status: 404 }),
    );

    await expect(postResearchProbeResponse(999, "A", "src-1")).rejects.toThrow("No such assignment");
  });
});
