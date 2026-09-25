import { getBackendUrl } from "../../utils/storyRecorderFeedback";
import { clientRoleHeader, SESSION_EXPIRED_EVENT, type SessionExpiredEventDetail } from "./client";

function formatValidationDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (!Array.isArray(detail)) return null;

  const messages = detail.map((item) => {
    if (typeof item === "string") return item;
    if (item && typeof item === "object") {
      const candidate = item as Record<string, unknown>;
      if (typeof candidate.msg !== "string") return null;
      const location = Array.isArray(candidate.loc)
        ? ` (${candidate.loc.filter((part: unknown): part is string | number => typeof part === "string" || typeof part === "number").join(".")})`
        : "";
      return `${candidate.msg}${location}`;
    }
    return null;
  }).filter((message): message is string => Boolean(message?.trim()));

  return messages.length > 0 ? messages.join("; ") : null;
}

export async function postSpeechAnalysis(formData: FormData, verified: boolean): Promise<unknown> {
  const response = await fetch(`${getBackendUrl()}${verified ? "/api/analyze/verified" : "/api/analyze"}`, {
    method: "POST",
    body: formData,
    credentials: "include",
    headers: { "X-Client-Role": clientRoleHeader() },
    signal: AbortSignal.timeout(120_000),
  });
  if (!response.ok) {
    let detail = "Speech analysis failed.";
    try {
      const body = await response.json() as { detail?: unknown };
      detail = formatValidationDetail(body.detail) ?? detail;
    } catch {
      // Keep the stable fallback when the backend returns a non-JSON error.
    }
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent<SessionExpiredEventDetail>(SESSION_EXPIRED_EVENT, {
        detail: { role: "student" },
      }));
    }
    throw new Error(detail);
  }
  return response.json();
}
