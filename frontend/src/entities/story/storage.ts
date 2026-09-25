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
  if (typeof window !== "undefined") {
    window.localStorage.setItem(CUSTOM_STORY_STORAGE_KEY, JSON.stringify(stories));
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

