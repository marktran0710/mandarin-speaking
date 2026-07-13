import type { ReactNode } from "react";
import "./ScoreCard.css";

/** Small labeled score tile shared by ImageNarrationPage and
 * ListenRetellPage's result grids — was defined twice, byte-identical
 * except for a page-specific class prefix. */
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
      <strong>{score}%</strong>
    </div>
  );
}
