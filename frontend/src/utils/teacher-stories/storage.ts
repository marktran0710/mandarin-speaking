import type { Topic } from "../../components/TopicSelector";
import type { CustomTeacherStory } from "./types";
import { storyToTopic } from "./mappers";

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
  if (typeof window !== "undefined") {
    window.localStorage.setItem(CUSTOM_STORY_STORAGE_KEY, JSON.stringify(stories));
  }
}

export function loadPublishedTeacherTopics(): Topic[] {
  return loadCustomStories()
    .filter((story) => story.published)
    .map((story) => storyToTopic(story, "easy", "approved"));
}

/** A story is authored once per scene, at the Easy tier, then optionally
 * gains Medium/Hard variants of the same plot — its own text and, if the
 * teacher uploads one, its own image; a tier left blank falls back to Easy's.
 * Picking a level just changes which tier storyToTopic reads. */

