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
  targetIds,
  refreshToken,
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
  /** Ordered ids the needs-stars target may come from — the newest
   * unlocked lesson's stories (the TOC's "you are here" row), so the
   * nudge always points at the lesson the student is actually on.
   * Omitted: every story in storyTitles is a candidate. */
  targetIds?: string[];
  /** Any value that changes when fresh backend stars might exist (page
   * switches, a practice session ending) — the bubble mounts once at App
   * level, so without this its attempts snapshot would go stale the
   * moment a quiz earns a star. */
  refreshToken?: unknown;
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
  }, [studentId, studentName, refreshToken]);

  // Per-story stars. Two folds happen here:
  // - local mirror vs backend history: whichever is higher (they drift
  //   across devices);
  // - text tiers: Medium/Hard sessions run the same 3-star quiz ladder
  //   under tier-suffixed quiz ids (`{id}-medium`, `{id}-hard`), so a
  //   story's stars are the BEST earned across its tiers — never the sum,
  //   which would triple-count the same ladder.
  const TIER_SUFFIXES = ["", "-medium", "-hard"];
  const starsFor = (id: string) =>
    Math.max(
      ...TIER_SUFFIXES.map((suffix) =>
        Math.max(
          loadLocalStars(`${id}${suffix}`),
          dbStars[`${id}${suffix}`] ?? 0,
        ),
      ),
    );

  // Pages without a story list can't enumerate ids — fold the backend map
  // onto base ids (best per story) and total that instead.
  const foldedDb: Record<string, number> = {};
  for (const [id, stars] of Object.entries(dbStars)) {
    const base = id.replace(/-(medium|hard)$/, "");
    foldedDb[base] = Math.max(foldedDb[base] ?? 0, stars);
  }
  // Sum each story's best tier once. This deliberately merges local and
  // backend values per story instead of taking the maximum of two totals,
  // which could discard stars earned on different stories.
  const earnedStoryIds = storyIds.length > 0 ? storyIds : Object.keys(foldedDb);
  const totalStars = earnedStoryIds.reduce((sum, id) => sum + starsFor(id), 0);
  const maxStars = storyCount ? storyCount * 3 : undefined;

  // Quiz ids for Medium/Hard tiers suffix the base topic id — map a
  // near-miss id back onto the base story so stars/titles resolve.
  const baseId = (id: string) =>
    storyIds.find((known) => known === id || id.startsWith(`${known}-`)) ?? id;

  // Target scope: the caller-provided candidate list (current lesson)
  // when given, else every known story. The near-miss story still wins
  // the slot, but only when it belongs to the scope — a near-miss in a
  // later lesson must not pull the student off their current one.
  const candidateIds = targetIds ?? storyIds;
  const firstBelowGate = candidateIds.find(
    (id) => starsFor(id) < PRACTICE_UNLOCK_STARS,
  );
  const nearMissBase =
    message.kind === "near_miss" ? baseId(message.storyId) : undefined;
  const targetId =
    nearMissBase !== undefined &&
    candidateIds.includes(nearMissBase) &&
    starsFor(nearMissBase) < PRACTICE_UNLOCK_STARS
      ? nearMissBase
      : firstBelowGate;
  const needsStars = firstBelowGate !== undefined;

  // ── Needs-stars state: pulsing quiz call-to-action ──────────────────────
  if (needsStars && targetId && onJumpToStory) {
    const targetTitle = titles[targetId] ?? targetId;
    return (
      <button
        type="button"
        className="journey-bubble journey-bubble-locked"
        onClick={() => onJumpToStory(targetId)}
        aria-label={`Take the quiz for ${targetTitle}. ${totalStars} of ${maxStars ?? "available"} stars earned overall.`}
        title={targetTitle}
      >
        <span className="journey-bubble-big">
          ⭐ {totalStars}{maxStars ? `/${maxStars}` : ""}
        </span>
        <span className="journey-bubble-caption">
          <BiLabel zh="做測驗" pinyin="Zuò cèyàn" en="Do the quiz" />
        </span>
      </button>
    );
  }

  // ── Caught-up / display-only state: progress dial ───────────────────────
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
