import { attemptEarnsStar, nextStarGap, type QuizTier } from "./quizTiers";

// The journey strip's one motivational slot (see the student-shell design
// in memory): near-miss first — a story the student almost earned a star on
// is the strongest "try again" pull — then the freshest star milestone,
// then a plain welcome for students with nothing to point at yet.

export interface StripAttempt {
  storyId: string;
  mode?: string | null;
  correctCount: number;
  completedAt: string;
}

export type StripMessage =
  | { kind: "welcome" }
  | { kind: "near_miss"; storyId: string; gap: number }
  | { kind: "milestone"; storyId: string; stars: QuizTier };

// A miss only counts as "near" when one or two more right answers would
// have passed — close enough that "try again right now" feels winnable.
const NEAR_MISS_MAX_GAP = 2;

export function pickStripMessage(attempts: StripAttempt[]): StripMessage {
  const sorted = [...attempts].sort((a, b) =>
    b.completedAt.localeCompare(a.completedAt),
  );

  // Latest tier attempt per story decides that story's status — an early
  // near-miss that a later run already passed is old news, not a nudge.
  const seen = new Set<string>();
  let nearMiss: { storyId: string; gap: number } | null = null;
  let milestone: { storyId: string; stars: QuizTier } | null = null;

  for (const attempt of sorted) {
    const gap = nextStarGap(attempt.mode, attempt.correctCount);
    if (gap === null) continue; // not a tier run
    const isLatestForStory = !seen.has(attempt.storyId);
    seen.add(attempt.storyId);

    if (
      isLatestForStory &&
      nearMiss === null &&
      gap >= 1 &&
      gap <= NEAR_MISS_MAX_GAP
    ) {
      nearMiss = { storyId: attempt.storyId, gap };
    }
    const earned = attemptEarnsStar(attempt.mode, attempt.correctCount);
    if (milestone === null && earned !== null) {
      milestone = { storyId: attempt.storyId, stars: earned };
    }
  }

  if (nearMiss) return { kind: "near_miss", ...nearMiss };
  if (milestone) return { kind: "milestone", ...milestone };
  return { kind: "welcome" };
}
