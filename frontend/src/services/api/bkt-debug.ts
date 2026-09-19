import { BACKEND_URL, fetchWithRetry } from "./client";

export interface BktDebugStep {
  index: number;
  correct: boolean;
  pLearned: number;
}

export interface BktDebugResult {
  wordId: string;
  targetWord: string;
  steps: BktDebugStep[];
  finalMastery: number;
  correctCount: number;
  totalCount: number;
  injectedCount: number;
}

export async function injectBktDebugResponses(
  studentId: string,
  storyId: string,
  wordId: string,
  pattern: string,
): Promise<BktDebugResult> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/bkt-debug/inject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ studentId, storyId, wordId, pattern }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Could not inject the debug responses.");
  }
  return response.json() as Promise<BktDebugResult>;
}
