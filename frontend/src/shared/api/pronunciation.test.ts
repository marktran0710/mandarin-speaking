import { afterEach, describe, expect, it, vi } from "vitest";
import { evaluatePronunciation, PronunciationRequestError } from "./pronunciation";

const evaluation = {
  status: "scored",
  reason: null,
  score: { total: 84, renormalized: true, dimensions: [] },
  metrics: { tone_similarity: 0.81 },
  words: [],
  feedback: { summary: "Clear overall.", focus_words: [], practice_tip: "Repeat slowly." },
  model: {
    scoring_version: "pronunciation-score-v1",
    acoustic_pipeline_version: "pronunciation-features-v1",
    feedback_model: "gpt-6-luna",
    feedback_source: "llm",
  },
  reference: { key: "story:s1:scene:2", cache_hit: false },
};

describe("evaluatePronunciation", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uploads only the recording and server-owned target identifiers", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.method).toBe("POST");
      expect(init?.body).toBeInstanceOf(FormData);
      const form = init?.body as FormData;
      expect(form.get("story_id")).toBe("s1");
      expect(form.get("scene_index")).toBe("2");
      expect(form.get("expected_text")).toBeNull();
      expect(form.get("file")).toBeInstanceOf(Blob);
      return new Response(JSON.stringify(evaluation), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await evaluatePronunciation(new Blob(["wav"], { type: "audio/wav" }), {
      storyId: "s1",
      sceneIndex: 2,
    });

    expect(result.score.total).toBe(84);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("preserves the backend's stable error code and message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      detail: { code: "reference_audio_missing", message: "Teacher audio is missing." },
    }), {
      status: 409,
      headers: { "Content-Type": "application/json" },
    })));

    try {
      await evaluatePronunciation(new Blob(["wav"], { type: "audio/wav" }), {
        storyId: "s1",
        sceneIndex: 0,
      });
      throw new Error("Expected evaluatePronunciation to reject");
    } catch (error) {
      expect(error).toBeInstanceOf(PronunciationRequestError);
      expect(error).toMatchObject({
        code: "reference_audio_missing",
        message: "Teacher audio is missing.",
        status: 409,
      });
    }
  });
});
