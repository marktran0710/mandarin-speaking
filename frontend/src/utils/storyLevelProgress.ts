import type { StoryDifficultyLevel } from "./teacherStories";
import { getStudentScopeKey, isAdminSession } from "./studentSession";
import type { StorySubmission } from "../services/database";

// Mirrors the vocabQuizCompletedStoryIds pattern in StoryRecorder.tsx: a
// flat, per-browser/device localStorage map (not synced to the backend)
// rather than a new persistence layer for something this small — but keyed
// per student so a shared classroom device can't leak one student's
// unlocked tiers into the next student's session.
const STORY_LEVEL_PROGRESS_KEY = "storyLevelProgress";

type StoryLevelProgress = Record<string, Partial<Record<StoryDifficultyLevel, boolean>>>;

type StudentIdentity = Pick<StorySubmission, "studentId" | "studentName">;

const DIFFICULTY_LEVELS: readonly StoryDifficultyLevel[] = ["easy", "medium", "hard"];

function isDifficultyLevel(value: unknown): value is StoryDifficultyLevel {
  return typeof value === "string" && DIFFICULTY_LEVELS.includes(value as StoryDifficultyLevel);
}

/** Older submissions did not include scene learning_context. Use their topic
 * id only as a fallback; current submissions always prefer the recorded
 * baseStoryId/difficultyLevel from their scenes. */
function inferSubmittedTier(storyId: string): { storyId: string; level: StoryDifficultyLevel } | null {
  const topicId = storyId.startsWith("teacher-") ? storyId.slice("teacher-".length) : storyId;
  if (!topicId) return null;
  const suffix = topicId.match(/^(.*)-(medium|hard)$/);
  if (suffix?.[1]) return { storyId: suffix[1], level: suffix[2] as StoryDifficultyLevel };
  return { storyId: topicId, level: "easy" };
}

function submittedTier(submission: StorySubmission) {
  const taggedScene = submission.scenes.find(
    (scene) =>
      (typeof scene.baseStoryId === "string" && scene.baseStoryId.length > 0) ||
      isDifficultyLevel(scene.difficultyLevel),
  );
  const fallback = inferSubmittedTier(submission.storyId);
  const storyId = taggedScene?.baseStoryId || fallback?.storyId;
  const level = isDifficultyLevel(taggedScene?.difficultyLevel)
    ? taggedScene.difficultyLevel
    : fallback?.level;
  return storyId && level ? { storyId, level } : null;
}

/** The only completion signal that advances a story's difficulty track.
 * StoryRecorder writes this after the learner has finished every speaking
 * scene and explicitly submits the story. Quiz stars alone must never open
 * the next difficulty. */
export function hasStoryLevelBeenSubmitted(
  storyId: string,
  level: StoryDifficultyLevel,
): boolean {
  return loadStoryLevelProgress()[storyId]?.[level] === true;
}

function loadStoryLevelProgress(): StoryLevelProgress {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(`${STORY_LEVEL_PROGRESS_KEY}:${getStudentScopeKey()}`);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

/** Records that a student submitted `storyId` at `level` — the signal the
 * picker uses to unlock the next tier (easy -> medium -> hard). */
export function markStoryLevelSubmitted(storyId: string, level: StoryDifficultyLevel) {
  if (typeof window === "undefined") return;
  const progress = loadStoryLevelProgress();
  const next: StoryLevelProgress = {
    ...progress,
    [storyId]: { ...progress[storyId], [level]: true },
  };
  window.localStorage.setItem(`${STORY_LEVEL_PROGRESS_KEY}:${getStudentScopeKey()}`, JSON.stringify(next));
}

/** Every story id with at least one submitted difficulty level — the
 * "story completed" signal the lesson picker's sequential lock and
 * progress dots run on. */
export function loadSubmittedStoryIds(): Set<string> {
  const progress = loadStoryLevelProgress();
  return new Set(
    Object.keys(progress).filter((storyId) =>
      Object.values(progress[storyId] ?? {}).some(Boolean),
    ),
  );
}

/** The submitted-levels map for one story ({} when none) — drives the
 * per-story 🌱🌿🌳 tier track on the picker cards. */
export function loadSubmittedLevels(
  storyId: string,
): Partial<Record<StoryDifficultyLevel, boolean>> {
  return loadStoryLevelProgress()[storyId] ?? {};
}

/** Whether `level` is unlocked for `storyId` — Easy always is; Medium/Hard
 * require the previous tier to have been submitted at least once. */
export function isStoryLevelUnlocked(storyId: string, level: StoryDifficultyLevel): boolean {
  // The learner journey is deliberately linear for each story:
  // easy quiz (all three tiers) -> speaking practice -> submit -> medium,
  // then repeat medium -> hard. The quiz/speaking gates live in the recorder;
  // this helper only advances after its explicit submission signal.
  if (level === "easy" || isAdminSession()) return true;
  if (level === "medium") return hasStoryLevelBeenSubmitted(storyId, "easy");
  return hasStoryLevelBeenSubmitted(storyId, "medium");
}

/** Add submitted speaking stories returned by the backend to this student's
 * local mirror. This never removes local progress, is safe to run repeatedly,
 * and deliberately rejects another student's records even if a server filter
 * is unavailable or stale. */
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
  const progress = loadStoryLevelProgress();
  let changed = false;
  const next: StoryLevelProgress = { ...progress };

  for (const submission of mine) {
    const tier = submittedTier(submission);
    if (!tier || next[tier.storyId]?.[tier.level]) continue;
    next[tier.storyId] = { ...next[tier.storyId], [tier.level]: true };
    changed = true;
  }

  if (changed) {
    window.localStorage.setItem(
      `${STORY_LEVEL_PROGRESS_KEY}:${getStudentScopeKey()}`,
      JSON.stringify(next),
    );
  }
  return changed;
}
