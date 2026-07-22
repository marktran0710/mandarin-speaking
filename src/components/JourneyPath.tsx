import type { ReactNode } from "react";
import "./JourneyPath.css";

export type JourneyStopStatus = "done" | "current" | "upcoming";

export interface JourneyStop {
  key: string | number;
  status: JourneyStopStatus;
  label: ReactNode;
  thumbnail?: string;
  /** Small overlay in the corner of the stop — e.g. an attempt count. */
  badge?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}

// The four tone-contour strokes (flat / rising / dip / falling), the same
// path data as ToneShapeIcon/ToneMark — cycled in order between stops so the
// connecting thread reads as a real pitch contour, not a straight progress
// bar, while staying literally grounded in what the app teaches.
const CONNECTOR_SHAPES = [
  "M2 14 H38", // flat
  "M2 22 L38 6", // rising
  "M2 10 C10 26 30 26 38 6", // dip
  "M2 6 L38 22", // falling
];

function JourneyConnector({ index, reached }: { index: number; reached: boolean }) {
  return (
    <svg
      className={`journey-connector${reached ? " reached" : ""}`}
      viewBox="0 0 40 28"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path
        d={CONNECTOR_SHAPES[index % CONNECTOR_SHAPES.length]}
        strokeWidth="3"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

/**
 * A connected row of stops (e.g. story scenes) threaded together by a
 * pitch-contour-shaped path instead of a plain strip or progress bar — the
 * app's own subject (tone contours are wavy pitch lines) doubles as the
 * "journey" visual, so scene N feels like the next stop on a path rather
 * than an unrelated thumbnail sitting next to the others.
 *
 * `orientation="vertical"` renders the same stops as a top-to-bottom column
 * (thumbnail ring left, label right) for the session sidebar — the contour
 * connectors rotate a quarter turn so the thread still reads as a pitch
 * line running down the path.
 */
export default function JourneyPath({
  stops,
  orientation = "horizontal",
}: {
  stops: JourneyStop[];
  orientation?: "horizontal" | "vertical";
}) {
  return (
    <div
      className={`journey-path${orientation === "vertical" ? " journey-path-vertical" : ""}`}
      role="list"
      aria-label="Practice journey"
    >
      {stops.map((stop, i) => (
        <div className="journey-item" key={stop.key} role="listitem">
          {i > 0 && (
            <JourneyConnector index={i - 1} reached={stop.status !== "upcoming"} />
          )}
          <button
            type="button"
            className={`journey-stop journey-stop-${stop.status}`}
            onClick={stop.onClick}
            disabled={stop.disabled}
          >
            <span className="journey-stop-ring">
              {stop.thumbnail ? (
                <img src={stop.thumbnail} alt="" />
              ) : (
                <span className="journey-stop-fallback">{i + 1}</span>
              )}
              {stop.status === "done" && (
                <span className="journey-stop-star" aria-hidden="true">★</span>
              )}
            </span>
            <span className="journey-stop-label">{stop.label}</span>
            {stop.badge && <span className="journey-stop-badge">{stop.badge}</span>}
          </button>
        </div>
      ))}
    </div>
  );
}
