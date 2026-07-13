import type { ReactNode } from "react";
import { scoreTier } from "../utils/scoreLabels";
import "./ScoreCard.css";

/** Small labeled score tile shared by ImageNarrationPage and
 * ListenRetellPage's result grids — was defined twice, byte-identical
 * except for a page-specific class prefix. The score number is tinted by
 * the same excellent/good/ok/low tier scale TonePracticePage uses, so a
 * raw percentage doesn't read as flat, uncolored text here while every
 * other score display in the app tells you at a glance how you did. */
export default function ScoreCard({
  label,
  score,
  highlight,
}: {
  label: ReactNode;
  score: number;
  highlight?: boolean;
}) {
  return (
    <div className={`mini-score-card ${highlight ? "highlight" : ""}`}>
      <span>{label}</span>
      <strong className={`score-tier-text ${scoreTier(score)}`}>{score}%</strong>
    </div>
  );
}
