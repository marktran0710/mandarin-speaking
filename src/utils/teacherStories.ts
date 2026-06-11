import type { Topic } from "../TopicSelector";

export interface CustomStoryFrame {
  imageUrl: string;
  prompt: string;
  vocabulary: string;
  conceptMap?: ConceptMapScaffold;
}

export interface ConceptMapScaffold {
  characters?: string;
  place?: string;
  actions?: string;
  vocabulary?: string;
  connectors?: string;
  fullStory?: string;
}

export interface CustomTeacherStory {
  id: string;
  title: string;
  learningGoal: string;
  level: string;
  frames: CustomStoryFrame[];
  published?: boolean;
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
  return publishedStoriesToTopics(loadCustomStories());
}

export function publishedStoriesToTopics(stories: CustomTeacherStory[]): Topic[] {
  return stories.filter((story) => story.published).map(storyToTopic);
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

  return {
    id: `teacher-${story.id}`,
    name: story.title,
    description: story.learningGoal,
    skillFocus: "Teacher published activity",
    level: story.level,
    images: story.frames.map((frame) => frame.imageUrl),
    vocabulary,
    conceptMaps: story.frames.reduce<Record<number, ConceptMapScaffold>>(
      (allScaffolds, frame, index) =>
        frame.conceptMap
          ? {
              ...allScaffolds,
              [index]: frame.conceptMap,
            }
          : allScaffolds,
      {},
    ),
  };
}
