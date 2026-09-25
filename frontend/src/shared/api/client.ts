import type { MeasurementEvent } from "../../utils/measurement";
import { getBackendUrl, isTestRuntime } from "../../config/runtimeEnv";

export const BACKEND_URL = getBackendUrl();
export const REQUEST_TIMEOUT_MS = 15_000;
export const VOCAB_GENERATION_RETRY_STATUSES = [429, 500, 502, 503, 504];

export class ApiRequestTimeoutError extends Error {
  constructor() {
    super("The backend did not respond in time. Check that the admin backend is running and healthy, then try again.");
    this.name = "ApiRequestTimeoutError";
  }
}

export class ApiRequestAbortedError extends Error {
  constructor() {
    super("The request was cancelled. Please try again.");
    this.name = "ApiRequestAbortedError";
  }
}

// Dispatched whenever any request comes back 401: the caller's client-side
// "am I logged in" state (a localStorage flag, checked independently of the
// actual httpOnly session cookie) can otherwise go stale - the cookie
// expires or gets cleared, but the flag persists, so the UI keeps acting
// authenticated while every request fails with the same generic "could not
// load data" error. Each app shell listens for this and clears its own
// stale flag instead of leaving the user stuck until they think to log out
// and back in manually.
export const SESSION_EXPIRED_EVENT = "app:session-expired";
export interface SessionExpiredEventDetail {
  role: "student" | "teacher" | "admin";
}

export function clientRoleHeader(): "student" | "teacher" | "admin" {
  const pathname = typeof window !== "undefined" ? window.location.pathname : "";
  if (pathname.endsWith("/admin.html")) return "admin";
  if (pathname.endsWith("/teacher.html") || pathname.startsWith("/manage")) {
    if (typeof window !== "undefined" && window.localStorage.getItem("adminConsoleSession") === "true") return "admin";
    return "teacher";
  }
  return "student";
}

export async function fetchWithRetry(input: RequestInfo | URL, init?: RequestInit, maxAttempts = 3, timeoutMs = REQUEST_TIMEOUT_MS, retryOnStatus: number[] = []): Promise<Response> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    try {
      const response = await fetch(input, { credentials: "include", ...init, headers: (() => { const headers = new Headers(init?.headers); headers.set("X-Client-Role", clientRoleHeader()); return headers; })(), signal: controller.signal });
      clearTimeout(timer);
      if (retryOnStatus.includes(response.status) && attempt < maxAttempts) { await new Promise((resolve) => setTimeout(resolve, 300 * 2 ** (attempt - 1))); continue; }
      if (response.status === 401 && typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent<SessionExpiredEventDetail>(SESSION_EXPIRED_EVENT, { detail: { role: clientRoleHeader() } }));
      }
      return response;
    } catch (error) {
      clearTimeout(timer);
      if (timedOut) throw new ApiRequestTimeoutError();
      const isAbort = error instanceof DOMException && error.name === "AbortError";
      if (isAbort) throw new ApiRequestAbortedError();
      lastError = error;
      const method = (init?.method ?? "GET").toUpperCase();
      if ((method !== "GET" && retryOnStatus.length === 0) || attempt === maxAttempts) break;
      await new Promise((resolve) => setTimeout(resolve, 300 * 2 ** (attempt - 1)));
    }
  }
  throw lastError;
}

export function canUseDatabase(): boolean { return Boolean(BACKEND_URL) && !isTestRuntime(); }
export async function persistMeasurementEvent(event: MeasurementEvent): Promise<void> {
  if (!canUseDatabase()) return;
  const response = await fetchWithRetry(`${BACKEND_URL}/api/measurement-events`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(event) }, 1);
  if (!response.ok) throw new Error("Could not persist measurement event.");
}
export async function listMeasurementEvents(): Promise<MeasurementEvent[]> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/measurement-events`);
  if (!response.ok) throw new Error("Could not load measurement events.");
  const data = await response.json(); return Array.isArray(data) ? data as MeasurementEvent[] : [];
}
