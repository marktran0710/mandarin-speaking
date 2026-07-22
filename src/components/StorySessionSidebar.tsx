import { useState, type ReactNode } from "react";
import JourneyPath, { type JourneyStop } from "./JourneyPath";
import { BiLabel } from "./BiLabel";
import "./StorySessionSidebar.css";

export type SidebarPhaseStatus = "done" | "active" | "upcoming";

export interface SidebarPhase {
  key: string;
  label: ReactNode;
  icon: string;
  status: SidebarPhaseStatus;
  /** Set only for phases the student may jump back to (done ones). */
  onClick?: () => void;
}

export type SidebarSummaryStatus = "locked" | "available" | "active" | "done";

interface StorySessionSidebarProps {
  topicName: string;
  onExit?: () => void;
  phases: SidebarPhase[];
  /** Scene stops rendered as a vertical journey nested under the Practice
   * phase node. Empty/omitted hides the journey (e.g. before practice). */
  journeyStops?: JourneyStop[];
  summaryStatus: SidebarSummaryStatus;
  onOpenSummary?: () => void;
  /** Rendered pinned to the sidebar's bottom (the raise-hand panel). On
   * narrow screens it collapses behind a floating help button. */
  helpPanel?: ReactNode;
}

function PhaseMarker({ status }: { status: SidebarPhaseStatus }) {
  return (
    <span className={`ssb-phase-marker ssb-phase-marker-${status}`}>
      {status === "done" && "✓"}
      {status === "active" && <span className="ssb-phase-marker-dot" />}
    </span>
  );
}

/** Left rail for a story practice session: exit + story name up top, the
 * phase list running vertically (done phases clickable, same jump-back rule
 * as the old horizontal stepper), the scene journey threaded under the
 * Practice node, and the raise-hand panel docked at the bottom. Replaces
 * the stacked story-nav-panel + horizontal JourneyPath + help strip. */
export default function StorySessionSidebar({
  topicName,
  onExit,
  phases,
  journeyStops,
  summaryStatus,
  onOpenSummary,
  helpPanel,
}: StorySessionSidebarProps) {
  // Mobile-only: the help panel folds behind a floating button. Desktop CSS
  // ignores this flag and always shows the panel.
  const [helpOpen, setHelpOpen] = useState(false);

  const summaryLabel = (
    <BiLabel zh="總結" pinyin="Zǒngjié" en="Summary" />
  );

  return (
    <aside className="story-session-sidebar" aria-label="Story progress">
      <div className="ssb-topline">
        {onExit && (
          <button
            type="button"
            className="btn-story-exit"
            onClick={onExit}
            aria-label="Back to topics"
          >
            ←
          </button>
        )}
        <span className="ssb-topic-name">{topicName}</span>
      </div>

      <nav className="ssb-phases" aria-label="Progress">
        {phases.map((p) => {
          const inner = (
            <>
              <PhaseMarker status={p.status} />
              <span className="ssb-phase-caption">
                <span className="ssb-phase-icon" aria-hidden="true">
                  {p.icon}
                </span>
                {p.label}
              </span>
            </>
          );
          const isPractice = p.key === "practice";
          const node =
            p.status === "done" && p.onClick ? (
              <button
                key={p.key}
                type="button"
                className={`ssb-phase ssb-phase-${p.status}`}
                onClick={p.onClick}
              >
                {inner}
              </button>
            ) : (
              <div key={p.key} className={`ssb-phase ssb-phase-${p.status}`}>
                {inner}
              </div>
            );
          if (!isPractice || !journeyStops || journeyStops.length === 0) {
            return node;
          }
          // The scene journey belongs to the Practice phase — nest it right
          // under that node so the hierarchy reads phase → scenes.
          return (
            <div className="ssb-practice-group" key={p.key}>
              {node}
              <div className="ssb-journey">
                <JourneyPath stops={journeyStops} orientation="vertical" />
              </div>
            </div>
          );
        })}

        {summaryStatus === "available" && onOpenSummary ? (
          <button
            type="button"
            className="ssb-phase ssb-phase-done ssb-summary"
            onClick={onOpenSummary}
          >
            <PhaseMarker status="done" />
            <span className="ssb-phase-caption">
              <span className="ssb-phase-icon" aria-hidden="true">🏁</span>
              {summaryLabel}
            </span>
          </button>
        ) : (
          <div
            className={`ssb-phase ssb-summary ${
              summaryStatus === "active"
                ? "ssb-phase-active"
                : summaryStatus === "done"
                  ? "ssb-phase-done"
                  : "ssb-phase-upcoming"
            }`}
          >
            <PhaseMarker
              status={
                summaryStatus === "active"
                  ? "active"
                  : summaryStatus === "done"
                    ? "done"
                    : "upcoming"
              }
            />
            <span className="ssb-phase-caption">
              <span className="ssb-phase-icon" aria-hidden="true">
                {summaryStatus === "locked" ? "🔒" : "🏁"}
              </span>
              {summaryLabel}
            </span>
          </div>
        )}
      </nav>

      {helpPanel && (
        <>
          <div className={`ssb-help${helpOpen ? " ssb-help-open" : ""}`}>
            {helpPanel}
          </div>
          <button
            type="button"
            className="ssb-help-toggle"
            aria-expanded={helpOpen}
            onClick={() => setHelpOpen((open) => !open)}
          >
            {helpOpen ? "✕" : "🖐"}
          </button>
        </>
      )}
    </aside>
  );
}
