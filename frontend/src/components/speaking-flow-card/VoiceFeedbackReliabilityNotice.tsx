import type { VoiceFeedbackReliability } from "@entities/speech";
import Icon from "@shared/ui/Icon";
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
 * recording itself didn't come through well enough to give feedback on. The
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
      : "We couldn't hear enough to compare pitch.";

  return (
    <aside
      className={`voice-reliability-notice is-retry${isCompact ? " is-compact" : ""}`}
      role="alert"
      aria-live="polite"
      data-feedback-reliability={assessment.level}
    >
      <span className="voice-reliability-icon" aria-hidden="true">
        <Icon name="retry" size={18} aria-hidden="true" />
      </span>
      <div>
        <strong>We couldn't measure this recording</strong>
        {!isCompact && <p>{detail}</p>}
      </div>
    </aside>
  );
}
