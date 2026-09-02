import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type WheelEvent,
} from "react";
import JourneyPath, { type JourneyStop } from "../journey/JourneyPath";
import StudentIcon from "../StudentIcon";
import { BiLabel } from "../BiLabel";
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
  const sceneScrollRef = useRef<HTMLElement>(null);
  const [sceneScrollState, setSceneScrollState] = useState({
    canScrollLeft: false,
    canScrollRight: false,
  });

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

  const sceneCount = orderedJourneyStops?.length ?? 0;

  useEffect(() => {
    const scrollNode = sceneScrollRef.current;
    if (!scrollNode) return;

    const updateScrollState = () => {
      const maxScrollLeft = Math.max(0, scrollNode.scrollWidth - scrollNode.clientWidth);
      const nextState = {
        canScrollLeft: scrollNode.scrollLeft > 1,
        canScrollRight: scrollNode.scrollLeft < maxScrollLeft - 1,
      };

      setSceneScrollState((currentState) =>
        currentState.canScrollLeft === nextState.canScrollLeft &&
        currentState.canScrollRight === nextState.canScrollRight
          ? currentState
          : nextState,
      );
    };

    scrollNode.addEventListener("scroll", updateScrollState, { passive: true });
    const resizeObserver =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateScrollState);
    resizeObserver?.observe(scrollNode);
    if (scrollNode.firstElementChild) resizeObserver?.observe(scrollNode.firstElementChild);
    updateScrollState();

    return () => {
      scrollNode.removeEventListener("scroll", updateScrollState);
      resizeObserver?.disconnect();
    };
  }, [sceneCount]);

  const handleSceneWheel = (event: WheelEvent<HTMLElement>) => {
    const scrollNode = sceneScrollRef.current;
    if (!scrollNode || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;

    const maxScrollLeft = Math.max(0, scrollNode.scrollWidth - scrollNode.clientWidth);
    if (maxScrollLeft <= 0) return;

    const nextScrollLeft = Math.min(
      maxScrollLeft,
      Math.max(0, scrollNode.scrollLeft + event.deltaY),
    );
    if (nextScrollLeft === scrollNode.scrollLeft) return;

    event.preventDefault();
    scrollNode.scrollLeft = nextScrollLeft;
  };

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
            aria-label="Back to previous page"
          >
            <StudentIcon name="arrow-left" size={17} />
          </button>
        )}
        <span className="ssb-topic-icon" aria-hidden="true">
          <StudentIcon name="book" size={22} />
        </span>
        <span className="ssb-topic-name">{topicName}</span>
      </div>

      {orderedJourneyStops && orderedJourneyStops.length > 0 && (
        <div
          className={`ssb-journey-viewport${
            sceneScrollState.canScrollLeft ? " has-scroll-left" : ""
          }${sceneScrollState.canScrollRight ? " has-scroll-right" : ""}`}
        >
          <nav
            ref={sceneScrollRef}
            className="ssb-journey"
            aria-label="Scenes"
            onWheel={handleSceneWheel}
          >
            <JourneyPath stops={orderedJourneyStops} orientation="vertical" />
          </nav>
        </div>
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
