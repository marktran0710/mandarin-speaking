/**
 * STEP 5/6 of the pre-pilot plumbing: a per-browser-tab session id (a
 * concept that did not exist anywhere in this codebase before -- login
 * identity and "practice session" are different things; see
 * `benchmarking/results/pilot_readiness.md` STEP 1's audit) plus the safe,
 * explicit, opt-in mechanism for enabling assistive feedback on pilot
 * sessions without touching the global `ENABLE_ASSISTIVE_FEEDBACK` default.
 *
 * Global default stays OFF. A session only becomes a "pilot" session when
 * the page is loaded with an explicit `?pilot=1` query parameter -- never
 * inferred, never on by default, never persisted across a fresh visit
 * without the flag being present again. This mirrors the same two-gate
 * discipline this codebase already uses elsewhere for exactly this kind of
 * "deliberately inconvenient to turn on by accident" switch
 * (`OMPAL_STUDY_MODE`, `OMPAL_FINAL_TEST_UNLOCKED`).
 */

const SESSION_STORAGE_KEY = "assistiveFeedbackPilotSessionId";

/** One id per browser tab session (sessionStorage, not localStorage --
 * intentionally does NOT survive closing the tab, so a session boundary
 * means something concrete rather than "however long a device happens to
 * keep localStorage"). */
export function getOrCreatePilotSessionId(): string {
  try {
    const existing = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
    const created = `session-${crypto.randomUUID()}`;
    sessionStorage.setItem(SESSION_STORAGE_KEY, created);
    return created;
  } catch {
    // sessionStorage unavailable (privacy mode, SSR, etc.) -- a session id
    // that doesn't persist across calls is still valid for a single request.
    return `session-${crypto.randomUUID()}`;
  }
}

export interface PilotContext {
  sessionId: string;
  /** "" in ordinary use; "pilot" only when explicitly requested. Never
   * inferred from role, student id, or anything else. */
  studyPhase: "" | "pilot";
}

/** Reads the explicit opt-in query parameter. Safe to call on every
 * analysis request -- cheap, synchronous, no network/storage side effects
 * beyond the session id above. */
export function resolvePilotContext(): PilotContext {
  const studyPhase = isPilotRequested() ? "pilot" : "";
  return { sessionId: getOrCreatePilotSessionId(), studyPhase };
}

function isPilotRequested(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("pilot") === "1";
  } catch {
    return false;
  }
}
