import { getBackendUrl } from "../../utils/storyRecorderFeedback";

export async function postSpeechAnalysis(formData: FormData, verified: boolean): Promise<unknown> {
  const response = await fetch(`${getBackendUrl()}${verified ? "/api/analyze/verified" : "/api/analyze"}`, {
    method: "POST",
    body: formData,
    signal: AbortSignal.timeout(120_000),
  });
  if (!response.ok) {
    let detail = "Speech analysis failed.";
    try {
      const body = await response.json() as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail.trim()) detail = body.detail;
    } catch {
      // Keep the stable fallback when the backend returns a non-JSON error.
    }
    throw new Error(detail);
  }
  return response.json();
}
