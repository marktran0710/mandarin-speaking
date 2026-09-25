import { ApiRequestAbortedError, ApiRequestTimeoutError, fetchWithRetry, SESSION_EXPIRED_EVENT, type SessionExpiredEventDetail } from "./client";

describe("fetchWithRetry session-expired signal", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("dispatches a session-expired event with the caller's role on a 401 response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 401 })));
    Object.defineProperty(window, "location", {
      value: { ...window.location, pathname: "/admin.html" },
      writable: true,
    });

    const received: SessionExpiredEventDetail[] = [];
    const handler = (event: Event) => received.push((event as CustomEvent<SessionExpiredEventDetail>).detail);
    window.addEventListener(SESSION_EXPIRED_EVENT, handler);

    const response = await fetchWithRetry("http://backend.test/api/students");

    window.removeEventListener(SESSION_EXPIRED_EVENT, handler);
    expect(response.status).toBe(401);
    expect(received).toEqual([{ role: "admin" }]);
  });

  it("does not dispatch anything for a normal 200 response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));

    const received: SessionExpiredEventDetail[] = [];
    const handler = (event: Event) => received.push((event as CustomEvent<SessionExpiredEventDetail>).detail);
    window.addEventListener(SESSION_EXPIRED_EVENT, handler);

    await fetchWithRetry("http://backend.test/api/students");

    window.removeEventListener(SESSION_EXPIRED_EVENT, handler);
    expect(received).toEqual([]);
  });

  it("turns its own timeout into an actionable error instead of a raw AbortError", async () => {
    vi.stubGlobal("fetch", vi.fn((_input, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("signal is aborted without reason", "AbortError")));
    })));

    await expect(fetchWithRetry("http://backend.test/api/admin/vocabulary-audio-import/preview", undefined, 1, 1))
      .rejects.toBeInstanceOf(ApiRequestTimeoutError);
    await expect(fetchWithRetry("http://backend.test/api/admin/vocabulary-audio-import/preview", undefined, 1, 1))
      .rejects.toThrow("backend did not respond in time");
  });

  it("turns a non-timeout abort into a clear cancellation error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new DOMException("cancelled by caller", "AbortError");
    }));

    await expect(fetchWithRetry("http://backend.test/api/admin/vocabulary-audio-import/preview", undefined, 1, 60_000))
      .rejects.toBeInstanceOf(ApiRequestAbortedError);
  });
});
