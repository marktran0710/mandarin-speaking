import type { ReactNode } from "react";
import StudentIcon from "../StudentIcon";
import "./JourneyPath.css";

export type JourneyStopStatus = "done" | "current" | "upcoming";

export interface JourneyStop {
  key: string | number;
  status: JourneyStopStatus;
  label: ReactNode;
  thumbnail?: string;
  /** Small overlay in the corner of the stop — e.g. an attempt count. */
  badge?: ReactNode;
  /** Ring content shown when there's no thumbnail — defaults to the stop's
   * 1-based position, which only reads correctly when stops are numbered
   * contiguously from 1 (e.g. scenes). Callers whose numbering doesn't
   * start at 1 (e.g. lessons 5, 6, 7…) must pass the real number here. */
  fallbackLabel?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  /** Optional panel rendered below this stop, inside its path segment (e.g.
   * an accordion body toggled by the stop's own onClick). Absent/undefined
   * renders nothing — most consumers never set this. */
  expanded?: ReactNode;
  /** Set when the stop's onClick toggles `expanded` — exposes the
   * open/closed state to assistive tech. Omit for stops that aren't
   * accordion triggers. */
  ariaExpanded?: boolean;
}

function JourneyConnector() {
  return <span className="journey-connector" aria-hidden="true" />;
}

/**
 * A connected row of scene stops with compact thumbnails and a plain visual
 * thread between each step. The vertical orientation reflows the same stops
 * into thumbnail-and-label rows for the session sidebar.
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
            <JourneyConnector />
          )}
          <button
            type="button"
            className={`journey-stop journey-stop-${stop.status}`}
            onClick={stop.onClick}
            disabled={stop.disabled}
            aria-expanded={stop.ariaExpanded}
          >
            <span className="journey-stop-ring">
              {stop.thumbnail ? (
                <img src={stop.thumbnail} alt="" />
              ) : (
                <span className="journey-stop-fallback">{stop.fallbackLabel ?? i + 1}</span>
              )}
              {stop.status === "done" && (
                <span className="journey-stop-star" aria-hidden="true"><StudentIcon name="star" size={14} fill="currentColor" /></span>
              )}
            </span>
            <span className="journey-stop-label">{stop.label}</span>
            {stop.badge && <span className="journey-stop-badge">{stop.badge}</span>}
          </button>
          {stop.expanded && (
            <div className="journey-stop-expanded">{stop.expanded}</div>
          )}
        </div>
      ))}
    </div>
  );
}
