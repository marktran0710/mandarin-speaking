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

/** Whether `level` is unlocked for `storyId` — Easy always is; Medium/Hard
 * require the previous tier to have been submitted at least once. */
export function isStoryLevelUnlocked(storyId: string, level: StoryDifficultyLevel): boolean {
  if (level === "easy") return true;
  const progress = loadStoryLevelProgress();
  const done = progress[storyId] || {};
  if (level === "medium") return done.easy === true;
  return done.medium === true;
}
