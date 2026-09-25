import { BACKEND_URL, fetchWithRetry } from "@shared/api/client";
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

/** Epic 7: one due, unanswered "Learning Check" question from the
 * independent outcome bank - never the correct answer, probe type, or
 * study id (see backend/application/research_probes.py, Task 7.6). */
export interface ResearchProbeQuestion {
  assignmentId: number;
  wordId: string;
  questionType: string;
  prompt: string;
  choices: string[] | null;
}

export async function getResearchProbesDue(): Promise<{ questions: ResearchProbeQuestion[] }> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/research/vocabulary/probes/due`, {
    method: "GET",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Could not load the learning check questions.");
  }
  return response.json() as Promise<{ questions: ResearchProbeQuestion[] }>;
}

/** Epic 7, Task 7.5/7.6: submits one Learning Check answer. Never a
 * quiz-attempt call - the response always just acknowledges receipt, since
 * showing correctness here would itself be an intervention on the outcome
 * measure being read. */
export async function postResearchProbeResponse(
  assignmentId: number,
  response: string,
  sourceResponseId: string,
): Promise<{ accepted: boolean }> {
  const httpResponse = await fetchWithRetry(
    `${BACKEND_URL}/api/research/vocabulary/probes/${assignmentId}/response`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ response, sourceResponseId }),
    },
  );
  if (!httpResponse.ok) {
    const body = await httpResponse.json().catch(() => ({}));
    throw new Error(body.detail || "Could not submit the learning check answer.");
  }
  return httpResponse.json() as Promise<{ accepted: boolean }>;
}
