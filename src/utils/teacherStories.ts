import type { Topic } from "../TopicSelector";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

/** Resolve a relative /uploads/... URL to an absolute backend URL. */
export function resolveImageUrl(url: string): string {
  if (!url) return url;
  if (url.startsWith("/uploads/")) return `${BACKEND_URL}${url}`;
  return url;
}

export interface VocabGroup {
  name: string;
  words: string[];
}

export interface CustomStoryFrame {
  imageUrl: string;
  prompt: string;
  vocabulary: string;
  vocabularyGroups?: VocabGroup[];
  grammarPattern?: string;
  listenAudioUrl?: string;
  listenScript?: string;
}

export interface CustomTeacherStory {
  id: string;
  title: string;
  learningGoal: string;
  level: string;
  frames: CustomStoryFrame[];
  published?: boolean;
  linear?: boolean;
}

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
    .map(storyToTopic);
}

export function storyToTopic(story: CustomTeacherStory): Topic {
  const vocabulary = story.frames.reduce<Record<number, string[]>>(
    (allWords, frame, index) => ({
      ...allWords,
      [index]: frame.vocabulary
        .split(",")
        .map((word) => word.trim())
        .filter(Boolean),
    }),
    {},
  );

  const vocabularyGroups: Record<number, import("../TopicSelector").VocabGroup[]> = {};
  const grammarPatterns: Record<number, string> = {};
  const listenAudioUrls: Record<number, string> = {};
  const listenScripts: Record<number, string> = {};
  story.frames.forEach((frame, index) => {
    if (frame.vocabularyGroups && frame.vocabularyGroups.length > 0) {
      vocabularyGroups[index] = frame.vocabularyGroups;
    }
    if (frame.grammarPattern && frame.grammarPattern.trim()) {
      grammarPatterns[index] = frame.grammarPattern.trim();
    }
    if (frame.listenAudioUrl && frame.listenAudioUrl.trim()) {
      listenAudioUrls[index] = resolveImageUrl(frame.listenAudioUrl.trim());
    }
    if (frame.listenScript && frame.listenScript.trim()) {
      listenScripts[index] = frame.listenScript.trim();
    }
  });

  return {
    id: `teacher-${story.id}`,
    name: story.title,
    description: story.learningGoal,
    skillFocus: "Teacher published activity",
    level: story.level,
    images: story.frames.map((frame) => resolveImageUrl(frame.imageUrl)),
    prompts: story.frames.map((frame) => frame.prompt),
    vocabulary,
    ...(Object.keys(vocabularyGroups).length > 0 ? { vocabularyGroups } : {}),
    ...(Object.keys(grammarPatterns).length > 0 ? { grammarPatterns } : {}),
    ...(Object.keys(listenAudioUrls).length > 0 ? { listenAudioUrls } : {}),
    ...(Object.keys(listenScripts).length > 0 ? { listenScripts } : {}),
    ...(story.linear ? { linear: true } : {}),
  };
}
