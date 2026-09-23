/**
 * Ambient, session-scoped cache of the current student's vocabulary
 * research context (Epic 3). Read the same way isAdminSession()/
 * getStudentName() already are - a plain function call, not a prop - so
 * deep call sites (attemptEarnsStar, starsFromAttempts inside
 * useQuizSession.ts) can be policy-aware without threading a new prop
 * through StoryVocabQuiz -> StoryRecorderRuntime.js. That bundle is a
 * committed, minified build artifact with no readable source in this repo;
 * it cannot be edited to pass a new prop through, so this is the only
 * viable way for research policy to reach code called from it.
 *
 * The default (before the first successful fetch, or if the fetch fails)
 * is always the inactive/production context - a network hiccup must never
 * accidentally switch a student into research-mode behavior.
 */
import { getVocabularyResearchContext, type VocabularyResearchContext } from "../services/api/vocabulary-research";

export const DEFAULT_RESEARCH_CONTEXT: VocabularyResearchContext = {
  active: false,
  coreCompletionPolicy: "production_accuracy",
  practiceAvailable: false,
  reviewAvailable: false,
  probeAvailable: false,
};

let cached: VocabularyResearchContext = DEFAULT_RESEARCH_CONTEXT;

/** Synchronous read of whatever was last fetched (or the safe default). */
export function getCachedResearchContext(): VocabularyResearchContext {
  return cached;
}

/** Fetches the real context from the server and updates the cache. Call
 * once per student session (e.g. on workspace mount) - never throws, so a
 * failed fetch just leaves the safe default in place. */
export async function refreshResearchContext(): Promise<VocabularyResearchContext> {
  try {
    cached = await getVocabularyResearchContext();
  } catch {
    cached = DEFAULT_RESEARCH_CONTEXT;
  }
  return cached;
}

/** Test-only: reset the module cache between tests without a full reload. */
export function resetResearchContextCacheForTests(): void {
  cached = DEFAULT_RESEARCH_CONTEXT;
}
