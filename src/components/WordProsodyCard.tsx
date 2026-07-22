import {
  formatContourShape,
  prosodyImprovementTip,
} from "../utils/storyRecorderFeedback";
import { scoreTier } from "../utils/scoreLabels";
import type { WordProsody } from "./StoryRecorder";
import MiniContourChart from "./MiniContourChart";
import WordPracticeDrill from "./WordPracticeDrill";

export default function WordProsodyCard({ item }: { item: WordProsody }) {
  const improvementTip = prosodyImprovementTip(item);
  // The number shown beside the shape name is the shape score — the same
  // comparison the chart draws — not tone_accuracy's directional blend,
  // which can legitimately differ from what the overlay looks like.
  const shapeScore =
    typeof item.shape_accuracy === "number" ? item.shape_accuracy : null;
  return (
    <div className="word-prosody-card">
      <div className="word-prosody-topline">
        <strong>{item.token}</strong>
        <span className="word-prosody-topline-meta">
          <span className="word-prosody-shape-pill">
            {formatContourShape(item.contour_shape)}
          </span>
          {shapeScore !== null && (
            <span
              className={`word-prosody-score score-tier-text ${scoreTier(shapeScore)}`}
            >
              {Math.round(shapeScore)}%
            </span>
          )}
        </span>
      </div>
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
      <WordPracticeDrill word={item} />
    </div>
  );
}
