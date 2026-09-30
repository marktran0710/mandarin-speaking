import type { Topic } from "@entities/topic";
import type { CustomTeacherStory } from "./types";
import { storyToTopic } from "./model";

// This is a short-lived authoring cache only. The backend custom_stories table
// remains the only canonical content source for the student app.
export const CUSTOM_STORY_STORAGE_KEY = "teacherCustomStories";

export function loadCustomStories(): CustomTeacherStory[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const stored = window.localStorage.getItem(CUSTOM_STORY_STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
}

export function saveCustomStories(stories: CustomTeacherStory[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CUSTOM_STORY_STORAGE_KEY, JSON.stringify(stories));
  } catch {
    // Best-effort cache: a full localStorage quota (the story list is
    // megabytes) must never block the caller. Drop the stale copy rather
    // than leave outdated stories behind.
    try {
      window.localStorage.removeItem(CUSTOM_STORY_STORAGE_KEY);
    } catch {/* storage unavailable */}
  }
}

// Topic id -> title, kept by the student app. It replaces writing the student's
// (pitch-data-free) story list into the teacher authoring cache above: a teacher
// editor opened later in the same browser hydrates from that cache and must
// never see stories with their pitch data stripped.
const STORY_TITLE_INDEX_KEY = "studentStoryTitles";

export function saveStoryTitleIndex(stories: CustomTeacherStory[]) {
  if (typeof window === "undefined") return;
  try {
    const titles = Object.fromEntries(stories.map((story) => [`teacher-${story.id}`, story.title]));
    window.localStorage.setItem(STORY_TITLE_INDEX_KEY, JSON.stringify(titles));
  } catch {/* best-effort cache */}
}

export function loadStoryTitle(topicId: string | undefined): string | undefined {
  if (typeof window === "undefined" || !topicId) return undefined;
  try {
    const stored = window.localStorage.getItem(STORY_TITLE_INDEX_KEY);
    const title = stored ? (JSON.parse(stored) as Record<string, unknown>)[topicId] : undefined;
    return typeof title === "string" ? title : undefined;
  } catch {
    return undefined;
  }
}

export function loadPublishedTeacherTopics(): Topic[] {
  return publishedTopicsFromStories(loadCustomStories());
}

export function publishedTopicsFromStories(stories: CustomTeacherStory[]): Topic[] {
  return stories
    .filter((story) => story.published)
    .map((story) => storyToTopic(story, "easy"));
}

/** A story is authored once per scene, at a single text level, then mapped to
 * a Topic by storyToTopic. */

