import type { StoryDifficultyLevel } from "./teacherStories";

// Mirrors the vocabQuizCompletedStoryIds pattern in StoryRecorder.tsx: a
// flat, per-browser/device localStorage map (not per-student, not synced to
// the backend) rather than a new persistence layer for something this small.
const STORY_LEVEL_PROGRESS_KEY = "storyLevelProgress";

type StoryLevelProgress = Record<string, Partial<Record<StoryDifficultyLevel, boolean>>>;

function loadStoryLevelProgress(): StoryLevelProgress {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(STORY_LEVEL_PROGRESS_KEY);
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
  window.localStorage.setItem(STORY_LEVEL_PROGRESS_KEY, JSON.stringify(next));
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
  if (level === "easy") return true;
  const progress = loadStoryLevelProgress();
  const done = progress[storyId] || {};
  if (level === "medium") return done.easy === true;
  return done.medium === true;
}
