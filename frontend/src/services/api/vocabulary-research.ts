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

/** Epic 1 scaffolding - not called from any real screen yet. Later Epics
 * (starting with Epic 3's progression rewiring) will read this once to
 * decide which VocabularyProgressionPolicy applies for the current student. */
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
