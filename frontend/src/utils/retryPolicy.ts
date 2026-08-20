/**
 * STEP 3's bounded retry flow, as a pure decision function -- no endless
 * retry loop, no forced threshold passing, no lesson blockage.
 *
 *   whole-sentence attempt -> feedback -> at most ONE focused retry for
 *   flagged (CHECK_THIS_TONE) syllables -> optional final whole-sentence
 *   attempt -> continue (always).
 *
 * `NO_AUTOMATIC_JUDGMENT` (UNCERTAIN) must always allow progression --
 * `shouldOfferRetry` never returns true for it; a retry is only ever
 * OFFERED for `CHECK_THIS_TONE` (NEEDS_PRACTICE), and only ever offered
 * once per attempt.
 */

import type { AssistiveState } from "./assistiveFeedback";

/** Fixed, per this task's STEP 3 spec ("at most one focused retry") --
 * not a tunable, not sourced from any research artifact. */
export const MAX_AUTOMATIC_RETRIES = 1;

export function shouldOfferRetry(state: AssistiveState | null, retriesUsed: number): boolean {
  if (state !== "NEEDS_PRACTICE") return false;
  return retriesUsed < MAX_AUTOMATIC_RETRIES;
}

/** Progression is NEVER blocked by this policy -- true for every state,
 * always. Kept as an explicit function (rather than inlined `true`
 * everywhere) so the "no hard gating" invariant has one named, testable
 * home instead of being implicit at every call site. */
export function canAlwaysProgress(_state: AssistiveState | null): boolean {
  return true;
}

export type ProgressionOutcome =
  | "continued_immediately"
  | "continued_after_retry"
  | "continued_after_cap";

/** What STEP 6's research log should record for one syllable's outcome,
 * from the same inputs the UI already has -- never "blocked": this policy
 * has no such outcome. */
export function progressionOutcome(state: AssistiveState | null, retriesUsed: number): ProgressionOutcome {
  if (state === "NEEDS_PRACTICE" && retriesUsed === 0) return "continued_immediately";
  if (state === "NEEDS_PRACTICE" && retriesUsed >= MAX_AUTOMATIC_RETRIES) return "continued_after_cap";
  if (retriesUsed > 0) return "continued_after_retry";
  return "continued_immediately";
}
