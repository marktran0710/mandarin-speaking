import { BiLabel } from "./BiLabel";
import "./PitchOverlay.css";

const CHART_WIDTH = 560;
const CHART_HEIGHT = 200;
const CHART_PAD = 28;

/** Overlays a recorded pitch contour against a reference tone shape as a
 * small self-contained SVG line chart (no charting library needed). */
export default function PitchOverlay({
  userContour,
  referenceContour,
}: {
  userContour: Array<[number, number]>;
  referenceContour: Array<[number, number]>;
}) {
  if (userContour.length < 2) {
    return (
      <div className="tone-pitch-overlay tone-pitch-overlay-empty">
        <BiLabel zh="音檔太短，無法畫出音高曲線。" en="Recording too short to draw a pitch curve." />
      </div>
    );
  }

  const allPoints = [...userContour, ...referenceContour];
  const times = allPoints.map((p) => p[0]);
  const freqs = allPoints.map((p) => p[1]);
  const minTime = Math.min(...times);
  const maxTime = Math.max(...times, minTime + 0.01);
  const minFreq = Math.min(...freqs);
  const maxFreq = Math.max(...freqs, minFreq + 1);

  const toX = (t: number) =>
    CHART_PAD + ((t - minTime) / (maxTime - minTime)) * (CHART_WIDTH - CHART_PAD * 2);
  const toY = (f: number) =>
    CHART_HEIGHT - CHART_PAD - ((f - minFreq) / (maxFreq - minFreq)) * (CHART_HEIGHT - CHART_PAD * 2);

  const toPath = (points: Array<[number, number]>) =>
    points
      .map(([t, f], i) => `${i === 0 ? "M" : "L"} ${toX(t).toFixed(1)} ${toY(f).toFixed(1)}`)
      .join(" ");

  return (
    <div className="tone-pitch-overlay">
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        role="img"
        aria-label="Your pitch compared with the target tone shape"
      >
        <rect x="0" y="0" width={CHART_WIDTH} height={CHART_HEIGHT} rx="12" className="tone-pitch-bg" />
        <text x={CHART_PAD} y={CHART_PAD - 10} className="tone-pitch-axis-label">
          {Math.round(maxFreq)} Hz
        </text>
        <text x={CHART_PAD} y={CHART_HEIGHT - CHART_PAD + 18} className="tone-pitch-axis-label">
          {Math.round(minFreq)} Hz
        </text>
        {referenceContour.length > 1 && (
          <path d={toPath(referenceContour)} className="tone-pitch-reference" />
        )}
        <path d={toPath(userContour)} className="tone-pitch-user" />
        <g className="tone-pitch-legend">
          <line x1={CHART_WIDTH - 150} y1="16" x2={CHART_WIDTH - 132} y2="16" className="tone-pitch-user" />
          <text x={CHART_WIDTH - 126} y="20" className="tone-pitch-axis-label">
            your pitch
          </text>
          {referenceContour.length > 1 && (
            <>
              <line
                x1={CHART_WIDTH - 150}
                y1="34"
                x2={CHART_WIDTH - 132}
                y2="34"
                className="tone-pitch-reference"
              />
              <text x={CHART_WIDTH - 126} y="38" className="tone-pitch-axis-label">
                target shape
              </text>
            </>
          )}
        </g>
      </svg>
    </div>
  );
}
