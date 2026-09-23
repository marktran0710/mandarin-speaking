import { BACKEND_URL, fetchWithRetry } from "./client";
import type { VocabularyProgressionPolicy } from "../../utils/vocabularyProgression";

/** Student-safe shape only - see backend/routers/vocab_quiz_research.py.
 * Never carries study id, condition, or any versioning field. */
export interface VocabularyResearchContext {
  active: boolean;
  coreCompletionPolicy: VocabularyProgressionPolicy;
  practiceAvailable: boolean;
  reviewAvailable: boolean;
  probeAvailable: boolean;
}

/** Read once per quiz session (cached by utils/researchContext.ts) to decide
 * which VocabularyProgressionPolicy applies for the current student. */
export async function getVocabularyResearchContext(): Promise<VocabularyResearchContext> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/research/vocabulary/context`, {
    method: "GET",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Could not load vocabulary research context.");
  }
  return response.json() as Promise<VocabularyResearchContext>;
}

/** Epic 4: server-owned word selection for a research participant's
 * practice round. The frontend must not choose these words itself from
 * weakEntries - see backend/application/research_practice_session.py. */
export async function postResearchPracticeSession(): Promise<{ wordIds: string[] }> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/research/vocabulary/practice-session`, {
    method: "POST",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Could not build a research practice session.");
  }
  return response.json() as Promise<{ wordIds: string[] }>;
}

/** Epic 5: which of a research participant's own retention words are due
 * right now. Read-only (no state changes), unlike the practice-session
 * endpoint above, so it is safe to call just to preview a count on the
 * mode-select menu - see backend/application/research_retention.py. */
export async function getResearchReviewSession(): Promise<{ wordIds: string[] }> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/research/vocabulary/review-session`, {
    method: "GET",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Could not load the research review session.");
  }
  return response.json() as Promise<{ wordIds: string[] }>;
}
