import type { MeasurementEvent } from "../../utils/measurement";

export const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || (import.meta.env.DEV && typeof window !== "undefined" ? window.location.origin : "");
export const REQUEST_TIMEOUT_MS = 15_000;
export const VOCAB_GENERATION_RETRY_STATUSES = [429, 500, 502, 503, 504];

function clientRoleHeader(): "student" | "teacher" | "admin" {
  const pathname = typeof window !== "undefined" ? window.location.pathname : "";
  if (pathname.endsWith("/teacher.html")) return "teacher";
  if (pathname.endsWith("/admin.html")) return "admin";
  return "student";
}

export async function fetchWithRetry(input: RequestInfo | URL, init?: RequestInit, maxAttempts = 3, timeoutMs = REQUEST_TIMEOUT_MS, retryOnStatus: number[] = []): Promise<Response> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(input, { credentials: "include", ...init, headers: (() => { const headers = new Headers(init?.headers); headers.set("X-Client-Role", clientRoleHeader()); return headers; })(), signal: controller.signal });
      clearTimeout(timer);
      if (retryOnStatus.includes(response.status) && attempt < maxAttempts) { await new Promise((resolve) => setTimeout(resolve, 300 * 2 ** (attempt - 1))); continue; }
      return response;
    } catch (error) {
      clearTimeout(timer); lastError = error;
      const isAbort = error instanceof DOMException && error.name === "AbortError";
      const method = (init?.method ?? "GET").toUpperCase();
      if (isAbort || (method !== "GET" && retryOnStatus.length === 0) || attempt === maxAttempts) break;
      await new Promise((resolve) => setTimeout(resolve, 300 * 2 ** (attempt - 1)));
    }
  }
  throw lastError;
}

export function canUseDatabase(): boolean { return Boolean(BACKEND_URL) && import.meta.env.MODE !== "test"; }
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
