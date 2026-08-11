/**
 * Shared types + copy for the additive ACCEPT/UNCERTAIN/NEEDS_PRACTICE
 * assistive-feedback layer (Candidate F1 risk signal + Candidate E2
 * diagnostic, combined per the frozen `feedback_policy_protocol.json`
 * rule). Mirrors `assistive_feedback/policy.py`'s constants exactly so the
 * frontend never invents its own wording.
 *
 * `assistive_feedback` on the `/api/analyze` response is `null`/absent
 * unless the backend has `ENABLE_ASSISTIVE_FEEDBACK=1` set — every
 * consumer of this module must treat a missing array as "nothing to show",
 * never as an error.
 */

export type AssistiveState = "ACCEPT" | "UNCERTAIN" | "NEEDS_PRACTICE";

export interface AssistiveFeedbackSyllable {
  syllable_index: number;
  character: string;
  expected_underlying_tone: number;
  accepted_surface_tones: number[];
  context_rule: string | null;
  realization: string;
  assistive_state: AssistiveState;
  assistive_state_label: "NO_ISSUE_DETECTED" | "NO_AUTOMATIC_JUDGMENT" | "CHECK_THIS_TONE";
  assistive_message: string;
  e2_diagnostic_category: string;
  explanation: {
    e2_provenance: string;
    e2_matched_tone: number;
    boundary_before: boolean;
    boundary_after: boolean;
  };
}

/** STEP 1 of `assistive_feedback_design.md` -- verbatim, never re-worded per row. */
export const ASSISTIVE_STATE_LABEL: Record<AssistiveState, AssistiveFeedbackSyllable["assistive_state_label"]> = {
  ACCEPT: "NO_ISSUE_DETECTED",
  UNCERTAIN: "NO_AUTOMATIC_JUDGMENT",
  NEEDS_PRACTICE: "CHECK_THIS_TONE",
};

/** This task's STEP 4 wording, verbatim. Never "wrong"/"failed"/"incorrect". */
export const ASSISTIVE_MESSAGE: Record<AssistiveState, string> = {
  ACCEPT: "No pronunciation issue was detected.",
  UNCERTAIN: "The system is not confident enough to judge this tone automatically.",
  NEEDS_PRACTICE: "This tone may be worth checking.",
};

/**
 * Matches one flattened breakdown-row position to its assistive record.
 * Position-based (the backend emits one record per Han character in
 * utterance order, the same order `PronunciationBreakdown` flattens
 * `word_prosody` into), with a character sanity check -- returns `null`
 * rather than a possibly-wrong match if the two sequences have drifted
 * apart (e.g. a partial/failed assistive-feedback computation for this
 * utterance), so a mismatch degrades to "nothing shown", never a
 * misattributed syllable.
 */
export function matchAssistiveRecord(
  records: AssistiveFeedbackSyllable[] | null | undefined,
  flatIndex: number,
  character: string,
): AssistiveFeedbackSyllable | null {
  if (!records) return null;
  const record = records[flatIndex];
  if (!record || record.character !== character) return null;
  return record;
}

/** Rolls a set of records up to the single most attention-worthy state --
 * NEEDS_PRACTICE beats UNCERTAIN beats ACCEPT -- for a sentence-level
 * summary (e.g. deciding whether a targeted retry should be offered). */
export function worstState(records: AssistiveFeedbackSyllable[]): AssistiveState | null {
  if (records.some((r) => r.assistive_state === "NEEDS_PRACTICE")) return "NEEDS_PRACTICE";
  if (records.some((r) => r.assistive_state === "UNCERTAIN")) return "UNCERTAIN";
  if (records.length > 0) return "ACCEPT";
  return null;
}
