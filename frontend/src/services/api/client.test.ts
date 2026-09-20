import { fetchWithRetry, SESSION_EXPIRED_EVENT, type SessionExpiredEventDetail } from "./client";

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
});
