import { useEffect, useState, type CSSProperties } from "react";
import { BiLabel } from "./BiLabel";
import { canUseDatabase, listVocabQuizAttempts } from "../services/database";
import {
  loadLocalStars,
  starsByStory,
  PRACTICE_UNLOCK_STARS,
} from "../utils/quizTiers";
import { pickStripMessage, type StripMessage } from "../utils/journeyStrip";
import "./JourneyBubble.css";

/** The floating star bubble of every non-practice student page — the
 * JourneyStrip band reshaped into one fixed round badge (bottom-right).
 *
 * Two states:
 * - Needs stars (some story below PRACTICE_UNLOCK_STARS): gold, pulsing,
 *   showing that story's ⭐ x/2 — a real button that jumps straight into
 *   the story so the student can take its quiz. The near-miss story from
 *   pickStripMessage wins the target slot; otherwise the first story (in
 *   lesson order) still short of the gate.
 * - All caught up (or the page doesn't know the story list): a quiet
 *   progress dial — conic ring for totalStars / (storyCount × 3) with the
 *   tally in the middle. Display only, not interactive.
 *
 * Data flow is unchanged from the strip: device-local stars paint
 * instantly, the attempts fetch raises them (and picks the near-miss)
 * once the backend answers. */
export default function JourneyBubble({
  studentName,
  studentId,
  storyCount,
  storyTitles,
  onJumpToStory,
}: {
  studentName?: string;
  studentId?: string;
  // How many stories exist (denominator: 3 stars each) — omit on pages that
  // don't know the story list; the dial then shows just the earned total.
  storyCount?: number;
  // Display titles by quiz storyId, in lesson order — also the candidate
  // list for the "first story still below the gate" target.
  storyTitles?: Record<string, string>;
  onJumpToStory?: (storyId: string) => void;
}) {
  const titles = storyTitles ?? {};
  const storyIds = Object.keys(titles);
  const [dbStars, setDbStars] = useState<Record<string, number>>({});
  const [message, setMessage] = useState<StripMessage>({ kind: "welcome" });

  useEffect(() => {
    if (!canUseDatabase() || (!studentId && !studentName)) return;
    let cancelled = false;
    listVocabQuizAttempts(undefined, { studentId, studentName })
      .then((attempts) => {
        if (cancelled) return;
        setDbStars(starsByStory(attempts));
        setMessage(pickStripMessage(attempts));
      })
      .catch(() => {
        /* best-effort — the bubble just keeps its local numbers */
      });
    return () => {
      cancelled = true;
    };
  }, [studentId, studentName]);

  // Per-story stars: whichever of the device-local mirror and the backend
  // history is higher (they can drift across devices).
  const starsFor = (id: string) =>
    Math.max(loadLocalStars(id), dbStars[id] ?? 0);

  const totalFromTitles = storyIds.reduce((sum, id) => sum + starsFor(id), 0);
  const totalFromDb = Object.values(dbStars).reduce((sum, s) => sum + s, 0);
  const totalStars = Math.max(totalFromTitles, totalFromDb);

  // Quiz ids for Medium/Hard tiers suffix the base topic id — map a
  // near-miss id back onto the base story so stars/titles resolve.
  const baseId = (id: string) =>
    storyIds.find((known) => known === id || id.startsWith(`${known}-`)) ?? id;

  const firstBelowGate = storyIds.find(
    (id) => starsFor(id) < PRACTICE_UNLOCK_STARS,
  );
  const targetId =
    message.kind === "near_miss" ? baseId(message.storyId) : firstBelowGate;
  const needsStars = firstBelowGate !== undefined;

  // ── Needs-stars state: pulsing quiz call-to-action ──────────────────────
  if (needsStars && targetId && onJumpToStory) {
    const targetStars = Math.min(starsFor(targetId), PRACTICE_UNLOCK_STARS);
    const targetTitle = titles[targetId] ?? targetId;
    return (
      <button
        type="button"
        className="journey-bubble journey-bubble-locked"
        onClick={() =>
          onJumpToStory(
            message.kind === "near_miss" ? message.storyId : targetId,
          )
        }
        aria-label={`做測驗拿星星 — ${targetTitle} (${targetStars}/${PRACTICE_UNLOCK_STARS} stars). Take the quiz to earn stars.`}
        title={targetTitle}
      >
        <span className="journey-bubble-big">
          ⭐ {targetStars}/{PRACTICE_UNLOCK_STARS}
        </span>
        <span className="journey-bubble-caption">
          <BiLabel zh="做測驗" pinyin="Zuò cèyàn" en="Do the quiz" />
        </span>
      </button>
    );
  }

  // ── Caught-up / display-only state: progress dial ───────────────────────
  const maxStars = storyCount ? storyCount * 3 : undefined;
  const progressDeg = maxStars
    ? Math.min(360, Math.round((totalStars / maxStars) * 360))
    : 0;
  return (
    <div
      className={`journey-bubble journey-bubble-dial${maxStars ? " has-ring" : ""}`}
      role="status"
      aria-label={
        maxStars
          ? `${totalStars} of ${maxStars} stars earned`
          : `${totalStars} stars earned`
      }
      style={{ "--jb-progress": `${progressDeg}deg` } as CSSProperties}
    >
      <span className="journey-bubble-big">
        ⭐ {totalStars}
        {maxStars ? `/${maxStars}` : ""}
      </span>
      <span className="journey-bubble-caption">
        <BiLabel zh="星星" pinyin="Xīngxing" en="Stars" />
      </span>
    </div>
  );
}
