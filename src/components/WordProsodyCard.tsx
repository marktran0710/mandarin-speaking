import {
  formatContourShape,
  prosodyImprovementTip,
} from "../utils/storyRecorderFeedback";
import { scoreTier } from "../utils/scoreLabels";
import type { WordProsody } from "./StoryRecorder";
import { BiLabel } from "./BiLabel";
import MiniContourChart from "./MiniContourChart";
import WordPracticeDrill from "./WordPracticeDrill";

export default function WordProsodyCard({ item }: { item: WordProsody }) {
  const improvementTip = prosodyImprovementTip(item);
  const hasReference =
    (item.target_curve?.length ?? 0) > 1 ||
    (item.reference_contour?.length ?? 0) > 1;
  // The number shown beside the shape chart is the shape score — the same
  // comparison the chart draws — not tone_accuracy's directional blend,
  // which can legitimately differ from what the overlay looks like.
  const shapeScore =
    typeof item.shape_accuracy === "number" ? item.shape_accuracy : null;
  return (
    <div className="word-prosody-card">
      <div className="word-prosody-topline">
        <strong>{item.token}</strong>
        <span>{formatContourShape(item.contour_shape)}</span>
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
      {hasReference && (
        <div className="mini-contour-legend">
          <span className="mini-contour-legend-actual">
            <BiLabel zh="你的音高" pinyin="Nǐ de yīngāo" en="Your pitch" />
          </span>
          <span className="mini-contour-legend-reference">
            <BiLabel zh="目標形狀" pinyin="Mùbiāo xíngzhuàng" en="Target shape" />
          </span>
          {shapeScore !== null && (
            <span
              className={`word-prosody-shape-score score-tier-text ${scoreTier(shapeScore)}`}
            >
              <BiLabel
                zh={`形狀相似 ${Math.round(shapeScore)}%`}
                pinyin={`Xíngzhuàng xiāngsì ${Math.round(shapeScore)}%`}
                en={`Shape match ${Math.round(shapeScore)}%`}
              />
            </span>
          )}
        </div>
      )}
      <div className="word-prosody-stats">
        <BiLabel
          zh={`平均 ${Math.round(item.mean_pitch)} Hz`}
          pinyin={`Píngjūn ${Math.round(item.mean_pitch)} Hz`}
          en={`${Math.round(item.mean_pitch)} Hz avg`}
        />
        <BiLabel
          zh={`範圍 ${Math.round(item.pitch_range)} Hz`}
          pinyin={`Fànwéi ${Math.round(item.pitch_range)} Hz`}
          en={`${Math.round(item.pitch_range)} Hz range`}
        />
      </div>
      <p>{item.feedback}</p>
      {improvementTip && (
        <p className="word-prosody-tip">💡 {improvementTip}</p>
      )}
      <WordPracticeDrill word={item} />
    </div>
  );
}
