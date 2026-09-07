import { getStudentScopeKey } from "./studentSession";
import type { StorySubmission } from "../services/database";

// A flat, per-browser/device localStorage set of the stories this student has
// submitted (not synced to the backend) — the "story completed" signal the
// lesson picker's sequential lock and progress dots run on. Keyed per student
// so a shared classroom device can't leak one student's progress into the
// next student's session.
//
// Difficulty tiers were removed: a story now has a single version, so progress
// is tracked per story id rather than per (story, easy/medium/hard) level. The
// storage still reads the old nested `{storyId: {easy: true}}` shape so a
// returning device does not lose progress after this change.
const STORY_LEVEL_PROGRESS_KEY = "storyLevelProgress";

type SubmittedProgress = Record<string, boolean>;

type StudentIdentity = Pick<StorySubmission, "studentId" | "studentName">;

/** The source story id behind a submission's scene metadata. Current
 * submissions persist a canonical baseStoryId on every scene; a legacy
 * submission without it falls back to its (non-tier-suffixed) topic id. A
 * `-medium`/`-hard` suffix is intentionally treated as ambiguous — a valid
 * source story may itself end with that word — so such legacy ids are
 * skipped rather than guessed. */
function submittedStoryId(submission: StorySubmission): string | null {
  const taggedScene = submission.scenes.find(
    (scene) => typeof scene.baseStoryId === "string" && scene.baseStoryId.length > 0,
  );
  if (taggedScene?.baseStoryId) return taggedScene.baseStoryId;
  const storyId = submission.storyId;
  if (!storyId) return null;
  const topicId = storyId.startsWith("teacher-") ? storyId.slice("teacher-".length) : storyId;
  if (!topicId || /-(medium|hard)$/.test(topicId)) return null;
  return topicId;
}

function loadSubmittedProgress(): SubmittedProgress {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(`${STORY_LEVEL_PROGRESS_KEY}:${getStudentScopeKey()}`);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const flat: SubmittedProgress = {};
    for (const [storyId, value] of Object.entries(parsed)) {
      // New shape: boolean. Legacy shape: { easy?: bool, medium?: bool, ... }.
      const submitted =
        value === true ||
        (value !== null && typeof value === "object" && Object.values(value as object).some(Boolean));
      if (submitted) flat[storyId] = true;
    }
    return flat;
  } catch {
    return {};
  }
}

function persist(progress: SubmittedProgress) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      `${STORY_LEVEL_PROGRESS_KEY}:${getStudentScopeKey()}`,
      JSON.stringify(progress),
    );
  } catch {
    /* storage unavailable — progress just won't persist on this device */
  }
}

/** Records that a student submitted `storyId`. The second argument is retained
 * only for call-site compatibility (the StoryRecorder runtime still passes the
 * scene's difficulty level); it is ignored now that stories are single-tier. */
export function markStoryLevelSubmitted(storyId: string, _level?: unknown) {
  if (!storyId) return;
  const progress = loadSubmittedProgress();
  if (progress[storyId]) return;
  persist({ ...progress, [storyId]: true });
}

/** Every story id this student has submitted — the completion signal the
 * lesson picker's sequential lock and progress dots run on. */
export function loadSubmittedStoryIds(): Set<string> {
  return new Set(Object.keys(loadSubmittedProgress()));
}

/** Add submitted stories returned by the backend to this student's local
 * mirror. Never removes local progress, is safe to run repeatedly, and
 * rejects another student's records even if a server filter is stale. */
export function mergeSubmittedStoryLevels(
  submissions: readonly StorySubmission[],
  student: StudentIdentity,
): boolean {
  if (typeof window === "undefined") return false;
  const mine = submissions.filter((submission) =>
    student.studentId
      ? submission.studentId === student.studentId
      : submission.studentName === student.studentName,
  );
  const progress = loadSubmittedProgress();
  let changed = false;
  const next: SubmittedProgress = { ...progress };

  for (const submission of mine) {
    const storyId = submittedStoryId(submission);
    if (!storyId || next[storyId]) continue;
    next[storyId] = true;
    changed = true;
  }

  if (changed) persist(next);
  return changed;
}
