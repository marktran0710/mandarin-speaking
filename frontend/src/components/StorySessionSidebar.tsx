import { useState, type ReactNode } from "react";
import JourneyPath, { type JourneyStop } from "./JourneyPath";
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
  /** Scene stops rendered as a vertical journey nested under the Speak
   * phase node. Empty/omitted hides the journey (e.g. before practice). */
  journeyStops?: JourneyStop[];
  summaryStatus: SidebarSummaryStatus;
  onOpenSummary?: () => void;
  /** Rendered pinned to the sidebar's bottom (the raise-hand panel). On
   * narrow screens it collapses behind a floating help button. */
  helpPanel?: ReactNode;
}

/** Left rail for a story practice session: exit + story name up top, the
 * phase progression threaded on the same tone-contour journey path used for
 * lessons (目錄) and for scenes — one visual language for "progress along a
 * sequence" at every level of the app, rather than a plain numbered list.
 * The scene journey nests under the Speak stop via JourneyPath's `expanded`
 * slot; the raise-hand panel docks at the bottom. */
export default function StorySessionSidebar({
  topicName,
  onExit,
  phases,
  journeyStops,
  helpPanel,
}: StorySessionSidebarProps) {
  // Mobile-only: the help panel folds behind a floating button. Desktop CSS
  // ignores this flag and always shows the panel.
  const [helpOpen, setHelpOpen] = useState(false);

  const phaseStops: JourneyStop[] = phases.map((p) => ({
    key: p.key,
    status: p.status === "active" ? "current" : p.status,
    label: p.label,
    fallbackLabel: p.icon,
    onClick: p.onClick,
    disabled: !p.onClick,
    expanded:
      p.key === "speak" && journeyStops && journeyStops.length > 0 ? (
        <div className="ssb-journey">
          <JourneyPath stops={journeyStops} orientation="vertical" />
        </div>
      ) : undefined,
  }));

  // summaryStatus/onOpenSummary stay in the props contract (StoryRecorder
  // still computes and passes them) but aren't rendered here — the Summary
  // node was force-hidden site-wide (see the .ssb-summary rule this replaced,
  // commit eb6e88f, an undocumented same-day "fix" not a deliberate design
  // call) and this redesign preserves that shipped behavior rather than
  // guess at re-enabling something that may have been hiding a real bug.

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
        <JourneyPath stops={phaseStops} orientation="vertical" />
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
