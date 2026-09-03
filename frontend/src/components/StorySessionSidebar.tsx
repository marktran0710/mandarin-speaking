import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import JourneyPath, { type JourneyStop } from "./JourneyPath";
import StudentIcon from "./StudentIcon";
import { SESSION_RAIL_SLOT_ID } from "./student-workspace/StudentSidebar";
import "./StorySessionSidebar.css";

export type SidebarSummaryStatus = "locked" | "available" | "active" | "done";

interface StorySessionSidebarProps {
  topicName: string;
  onExit?: () => void;
  /** Scene stops for the current story, shown as a vertical journey once
   * practice has started. Empty/omitted hides it (e.g. on the Prepare
   * screen, before there is anything to navigate between). */
  journeyStops?: JourneyStop[];
  summaryStatus: SidebarSummaryStatus;
  onOpenSummary?: () => void;
  /** Rendered pinned to the sidebar's bottom (the raise-hand panel). On
   * narrow screens it collapses behind a floating help button. */
  helpPanel?: ReactNode;
}

/** Left rail for a story practice session: exit + story name up top, the
 * scene list (once practice has started) on the same tone-contour journey
 * path used for lessons (目錄), and the raise-hand panel docked at the
 * bottom.
 *
 * Used to also show a Prepare/Speak/Feedback stepper above the scene list —
 * three large rings on a curved connector, the same decorative-journey
 * treatment the lesson list (目錄) dropped for image rows the same day, for
 * the same reason: it read as decoration carrying little information.
 * Removed at the user's request rather than simplified, since unlike the
 * lesson list there was no simpler stand-in judged worth building for it. */
export default function StorySessionSidebar({
  topicName,
  onExit,
  journeyStops,
  helpPanel,
}: StorySessionSidebarProps) {
  // Mobile-only: the help panel folds behind a floating button. Desktop CSS
  // ignores this flag and always shows the panel.
  const [helpOpen, setHelpOpen] = useState(false);

  // Student mode keeps ONE left rail. When the workspace shell is on screen
  // it offers a slot inside that rail, and this content moves into it, so a
  // practice session never opens a second rail beside the first. Outside the
  // shell (a route that renders StoryRecorder on its own) the slot is absent
  // and this still renders as its own <aside>, unchanged.
  // The shell renders the slot unconditionally and before this component
  // mounts, so a single mount lookup is enough — no re-checking, and no
  // dependence on a later render happening to land.
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  useEffect(() => {
    setSlot(document.getElementById(SESSION_RAIL_SLOT_ID));
  }, []);

  // Scene practice is sequential: a student may revisit completed scenes, but
  // the next scene stays locked until the previous one has a result. This is
  // intentionally independent of the pronunciation pass/fail verdict.
  const orderedJourneyStops = journeyStops?.map((stop, index, stops) => {
    const previousStop = index > 0 ? stops[index - 1] : undefined;
    const waitingForPrevious =
      stop.status === "upcoming" && previousStop?.status !== "done";
    return {
      ...stop,
      disabled: Boolean(stop.disabled || waitingForPrevious),
    };
  });

  // summaryStatus/onOpenSummary stay in the props contract (StoryRecorder
  // still computes and passes them) but aren't rendered here — the Summary
  // node was force-hidden site-wide (see the .ssb-summary rule this replaced,
  // commit eb6e88f, an undocumented same-day "fix" not a deliberate design
  // call) and this redesign preserves that shipped behavior rather than
  // guess at re-enabling something that may have been hiding a real bug.

  const body = (
    <>
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

      {orderedJourneyStops && orderedJourneyStops.length > 0 && (
        <nav className="ssb-journey" aria-label="Scenes">
          <JourneyPath stops={orderedJourneyStops} orientation="vertical" />
        </nav>
      )}

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
            <StudentIcon name={helpOpen ? "close" : "user"} size={18} />
          </button>
        </>
      )}
    </>
  );

  if (slot) return createPortal(body, slot);

  return (
    <aside className="story-session-sidebar" aria-label="Story progress">
      {body}
    </aside>
  );
}
