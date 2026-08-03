import type { VoiceFeedbackReliability } from "../utils/voiceFeedbackReliability";
import "./VoiceFeedbackReliabilityNotice.css";

export default function VoiceFeedbackReliabilityNotice({
  assessment,
  attemptCount = 1,
  compact = false,
}: {
  assessment: VoiceFeedbackReliability;
  attemptCount?: number;
  compact?: boolean;
}) {
  const copy = {
    reliable: {
      icon: "✓",
      title: "Recording evidence looks usable",
      detail:
        "Pitch was measurable and the spoken content was checked. Use the feedback as a practice guide, not as a perfect judgment.",
    },
    estimate: {
      icon: "≈",
      title: "Feedback is an estimate",
      detail:
        "Pitch was measurable, but the words were not independently confirmed. Compare with the model recording before changing how you pronounce it.",
    },
    retry: {
      icon: "↻",
      title: "Retake before trusting this score",
      detail:
        assessment.reason === "content-mismatch"
          ? "The recording did not match the target closely enough. The score above may not be reliable and should not count."
          : "There was not enough clear pitch evidence to judge this recording safely.",
    },
  }[assessment.level];

  return (
    <aside
      className={`voice-reliability-notice is-${assessment.level}${compact ? " is-compact" : ""}`}
      role={assessment.level === "retry" ? "alert" : "status"}
      aria-live="polite"
      data-feedback-reliability={assessment.level}
    >
      <span className="voice-reliability-icon" aria-hidden="true">
        {copy.icon}
      </span>
      <div>
        <strong>{copy.title}</strong>
        {!compact && <p>{copy.detail}</p>}
        {assessment.level === "retry" && !compact && (
          <p className="voice-reliability-action">
            Move 10–20 cm from the microphone, find a quieter spot, and say the
            target once at a natural pace.
          </p>
        )}
        {assessment.level !== "reliable" && attemptCount >= 2 && !compact && (
          <p className="voice-reliability-teacher">
            Still getting conflicting feedback? Ask a teacher to review the
            recording before drilling this correction.
          </p>
        )}
      </div>
    </aside>
  );
}
