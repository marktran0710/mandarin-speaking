import {
  prosodyImprovementTip,
  shapeArrow,
  toneArrow,
} from "../utils/storyRecorderFeedback";
import { scoreTier } from "../utils/scoreLabels";
import type { WordProsody } from "./StoryRecorder";
import MiniContourChart from "./MiniContourChart";
import WordPracticeDrill from "./WordPracticeDrill";

export default function WordProsodyCard({
  item,
  onDrillPass,
}: {
  item: WordProsody;
  onDrillPass?: (token: string) => void;
}) {
  const improvementTip = prosodyImprovementTip(item);
  // The number shown in the topline is the shape score — the same
  // comparison the chart draws — not tone_accuracy's directional blend,
  // which can legitimately differ from what the overlay looks like.
  const shapeScore =
    typeof item.shape_accuracy === "number" ? item.shape_accuracy : null;
  const expectedTones = item.expected_tones ?? [];
  const syllables = item.syllables ?? [];
  const failed = item.passed === false;
  return (
    <div className={`word-prosody-card ${failed ? "word-prosody-failed" : ""}`}>
      <div className="word-prosody-topline">
        <strong>{item.token}</strong>
        <span className="word-prosody-topline-meta">
          {/* "You said X / target Y" — two labeled pills so the measured
              shape of the student's own pitch is never mistaken for a
              description of the target tones (the old single pill read as
              a verdict and contradicted the feedback text below). */}
          <span className="word-prosody-shape-pill">
            你說 {shapeArrow(item.contour_shape)}
          </span>
          {expectedTones.length > 0 && (
            <span className="word-prosody-shape-pill word-prosody-target-pill">
              要說 {expectedTones.map(toneArrow).join(" ")}
            </span>
          )}
          {shapeScore !== null && (
            <span
              className={`word-prosody-score score-tier-text ${scoreTier(shapeScore)}`}
            >
              {Math.round(shapeScore)}%
            </span>
          )}
        </span>
      </div>
      {syllables.length > 0 && (
        <div
          className="word-syllable-row"
          aria-label={`${item.token} per-syllable results`}
        >
          {syllables.map((syllable, index) => (
            <span
              key={`${syllable.char}-${index}`}
              className={`word-syllable-chip ${
                syllable.passed ? "syllable-pass" : "syllable-fail"
              }`}
            >
              {syllable.char} {toneArrow(syllable.tone)}{" "}
              {syllable.passed ? "✓" : "✗"}
            </span>
          ))}
        </div>
      )}
      <div
        className="mini-contour"
        aria-label={`${item.token} pitch contour vs target shape`}
      >
        <MiniContourChart
          actual={item.pitch_contour}
          reference={item.reference_contour}
          userCurve={item.user_curve}
          targetCurve={item.target_curve}
        />
      </div>
      <p className="word-prosody-feedback">{item.feedback}</p>
      {improvementTip && (
        <p className="word-prosody-tip">💡 {improvementTip}</p>
      )}
      <WordPracticeDrill word={item} onPass={onDrillPass} />
    </div>
  );
}
