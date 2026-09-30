import { afterEach, describe, expect, it, vi } from "vitest";
import { postSpeechAnalysis } from "./speech-analysis";

describe("postSpeechAnalysis", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends the student session cookie and role header", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await postSpeechAnalysis(new FormData(), true);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/analyze/verified"),
      expect.objectContaining({
        credentials: "include",
        headers: { "X-Client-Role": "student" },
      }),
    );
  });

  it("keeps FastAPI validation details instead of hiding them behind a generic error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      detail: [{ loc: ["body", "scene_index"], msg: "Field required" }],
    }), { status: 422 })));

    await expect(postSpeechAnalysis(new FormData(), true))
      .rejects.toThrow("Field required (body.scene_index)");
  });
});


it("shows structured pronunciation model errors", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
    detail: { code: "llm_http_401", message: "GPT feedback failed. No local feedback was substituted." },
  }), { status: 502 })));
  await expect(postSpeechAnalysis(new FormData(), true)).rejects.toThrow("No local feedback was substituted. (llm_http_401)");
  vi.unstubAllGlobals();
});
