import { useState, type ReactNode } from "react";
import JourneyPath, { type JourneyStop } from "./JourneyPath";
import StudentIcon from "./StudentIcon";
import { BiLabel } from "./BiLabel";
import "./StorySessionSidebar.css";

export type SidebarSummaryStatus = "locked" | "available" | "active" | "done";

interface StorySessionSidebarProps {
  topicName: string;
  onExit?: () => void;
  /** Scene stops for the current story, shown as a horizontal strip once
   * practice has started. Empty/omitted hides it (e.g. on the Prepare
   * screen, before there is anything to navigate between). */
  journeyStops?: JourneyStop[];
  summaryStatus: SidebarSummaryStatus;
  onOpenSummary?: () => void;
  /** Dropped into a popover behind the raise-hand toggle at the strip's
   * end. */
  helpPanel?: ReactNode;
}

/** Header strip above a story practice session's content: exit + story name,
 * the scene list (once practice has started) as a horizontal strip, and the
 * raise-hand panel behind a toggle at the end.
 *
 * This used to be a left rail — first its own, then (once student mode
 * settled on a single global rail) portaled into that rail's middle. Moved
 * out of the rail entirely at the user's request: the global rail
 * (StudentSidebar — brand, 課程/我的學習, the star card, account block) now
 * stays exactly as-is on every student screen, session included, rather
 * than lending its middle to whatever story is running. This strip is
 * where the session-specific navigation that used to live there now goes
 * instead.
 *
 * Before that it briefly showed a Prepare/Speak/Feedback stepper above the
 * scene list — three large rings on a curved connector, the same
 * decorative-journey treatment the lesson list (目錄) dropped for image rows
 * the same day, for the same reason: it read as decoration carrying little
 * information. Removed at the user's request rather than simplified. */
export default function StorySessionSidebar({
  topicName,
  onExit,
  journeyStops,
  helpPanel,
}: StorySessionSidebarProps) {
  const [helpOpen, setHelpOpen] = useState(false);

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

  return (
    <div className="story-session-topbar">
      <div className="ssb-topline">
        {onExit && (
          <button
            type="button"
            className="btn-story-exit"
            onClick={onExit}
            aria-label="Back to topics"
          >
            <StudentIcon name="arrow-left" size={17} />
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
        <div className="ssb-help-anchor">
          <button
            type="button"
            className="ssb-help-toggle"
            aria-expanded={helpOpen}
            onClick={() => setHelpOpen((open) => !open)}
          >
            <StudentIcon name={helpOpen ? "close" : "user"} size={18} />
            <BiLabel zh="舉手" pinyin="Jǔshǒu" en="Raise hand" />
          </button>
          {helpOpen && <div className="ssb-help">{helpPanel}</div>}
        </div>
      )}
    </div>
  );
}
