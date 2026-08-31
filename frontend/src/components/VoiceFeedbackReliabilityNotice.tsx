import type { VoiceFeedbackReliability } from "../utils/voiceFeedbackReliability";
import {
  ASSISTIVE_MESSAGE,
  type AssistiveState,
} from "../utils/assistiveFeedback";
import StudentIcon from "./StudentIcon";
import "./VoiceFeedbackReliabilityNotice.css";

/**
 * Shown only when the recording itself is unusable.
 *
 * This used to announce all three reliability levels, including "Recording
 * evidence looks usable" and "Feedback is an estimate". Both described how
 * much the *measurement* could be trusted — interesting to us, useless to a
 * student, who cannot act on either one. They were two paragraphs of English
 * sitting above the actual results on every single attempt.
 *
 * What survives is the one level a learner needs to understand: the
 * recording failed and the score is unavailable. The
 * assessment itself is untouched — `assessVoiceFeedbackReliability` still
 * feeds `canCountForProgress` in the practice drills, and several screens
 * still hide their scores on `level === "retry"`. This is display only.
 */
export default function VoiceFeedbackReliabilityNotice({
  assessment,
  variant = "default",
}: {
  assessment: VoiceFeedbackReliability;
  /** Kept for call-site compatibility; no longer read. */
  attemptCount?: number;
  variant?: "default" | "compact";
}) {
  if (assessment.level !== "retry") return null;

  const isCompact = variant === "compact";

  const detail =
    assessment.reason === "content-mismatch"
      ? "The words did not match the target closely enough."
      : "We couldn't hear enough pitch to score this recording.";

  return (
    <aside
      className={`voice-reliability-notice is-retry${isCompact ? " is-compact" : ""}`}
      role="alert"
      aria-live="polite"
      data-feedback-reliability={assessment.level}
    >
      <span className="voice-reliability-icon" aria-hidden="true">
        <StudentIcon name="retry" size={18} />
      </span>
      <div>
        <strong>Score unavailable</strong>
        {!isCompact && <p>{detail}</p>}
      </div>
    </aside>
  );
}

/**
 * The three-state ACCEPT/UNCERTAIN/NEEDS_PRACTICE assistive-feedback notice
 * -- a DIFFERENT concept from the reliability notice above (this component
 * is about recording-quality QC; this one is about a per-syllable tone
 * judgment). Additive: only rendered when the caller has an
 * `assistive_feedback` record to show, which only exists when the backend's
 * `ENABLE_ASSISTIVE_FEEDBACK` flag is on. `NO_ISSUE_DETECTED` renders
 * nothing by default (no notice needed for "carry on") unless the caller
 * explicitly opts into showing brief positive acknowledgement.
 *
 * Never claims "wrong"/"failed"/"incorrect" -- see
 * `benchmarking/results/assistive_feedback_design.md` STEP 5.
 */
export function AssistiveFeedbackNotice({
  state,
  showOnAccept = false,
  variant = "default",
}: {
  state: AssistiveState;
  /** Show a low-key acknowledgement for NO_ISSUE_DETECTED too; off by
   * default since STEP 4 only asks for this optionally. */
  showOnAccept?: boolean;
  variant?: "default" | "compact";
}) {
  if (state === "ACCEPT" && !showOnAccept) return null;

  const isCompact = variant === "compact";

  const tone = state === "NEEDS_PRACTICE" ? "check" : state === "UNCERTAIN" ? "uncertain" : "accept";
  const icon = state === "NEEDS_PRACTICE" ? "warning" : state === "UNCERTAIN" ? "help" : "check-circle";

  return (
    <aside
      className={`voice-reliability-notice is-assistive is-${tone}${isCompact ? " is-compact" : ""}`}
      role="status"
      aria-live="polite"
      data-assistive-state={state}
    >
      <span className="voice-reliability-icon" aria-hidden="true">
        <StudentIcon name={icon} size={17} />
      </span>
      <div>
        <p>{ASSISTIVE_MESSAGE[state]}</p>
      </div>
    </aside>
  );
}
