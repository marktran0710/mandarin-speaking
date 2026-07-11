import type { Topic } from "../components/TopicSelector";
import { numericToToneMarked } from "./pinyin";

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
  // Handy, easy-to-learn-and-reuse phrases for this scene (replaces the old
  // single whole-story "grammar pattern" note), comma-joined per scene —
  // same convention as vocabulary/vocabularyTranslation below.
  phrases?: string;
  phrasesTranslation?: string;
  vocabularyPinyin?: string;
  vocabularyPos?: string;
  vocabularyTranslation?: string;
  // JSON-encoded array of arrays (one entry per word, aligned with the
  // comma-split `vocabulary` above) — distractors are inherently multi-valued
  // per word, unlike the other comma-joined single-value fields.
  vocabularyDistractors?: string;
  suggestedAnswer?: string;
  listenAudioUrl?: string;
  listenScript?: string;
}

export type NarrativeMode = "story" | "describe" | "listen_retell";

export interface CustomTeacherStory {
  id: string;
  title: string;
  learningGoal: string;
  level: string;
  frames: CustomStoryFrame[];
  published?: boolean;
  linear?: boolean;
  lessonNumber?: number | null;
  narrativeMode?: NarrativeMode;
  firstFrameIsExample?: boolean;
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

  const vocabularyGroups: Record<number, import("../components/TopicSelector").VocabGroup[]> = {};
  const phrases: Record<number, string[]> = {};
  const phrasesTranslation: Record<number, string[]> = {};
  const vocabularyPinyin: Record<number, string[]> = {};
  const vocabularyPos: Record<number, string[]> = {};
  const vocabularyTranslation: Record<number, string[]> = {};
  const vocabularyDistractors: Record<number, string[][]> = {};
  const suggestedAnswers: Record<number, string> = {};
  const listenAudioUrls: Record<number, string> = {};
  const listenScripts: Record<number, string> = {};
  story.frames.forEach((frame, index) => {
    if (frame.vocabularyGroups && frame.vocabularyGroups.length > 0) {
      vocabularyGroups[index] = frame.vocabularyGroups;
    }
    if (frame.phrases && frame.phrases.trim()) {
      phrases[index] = frame.phrases
        .split(",")
        .map((p) => p.trim())
        .filter(Boolean);
    }
    if (frame.phrasesTranslation && frame.phrasesTranslation.trim()) {
      phrasesTranslation[index] = frame.phrasesTranslation
        .split(",")
        .map((t) => t.trim());
    }
    if (frame.vocabularyPinyin && frame.vocabularyPinyin.trim()) {
      vocabularyPinyin[index] = frame.vocabularyPinyin
        .split(",")
        .map((p) => numericToToneMarked(p.trim()));
    }
    if (frame.vocabularyPos && frame.vocabularyPos.trim()) {
      vocabularyPos[index] = frame.vocabularyPos
        .split(",")
        .map((p) => p.trim());
    }
    if (frame.vocabularyTranslation && frame.vocabularyTranslation.trim()) {
      vocabularyTranslation[index] = frame.vocabularyTranslation
        .split(",")
        .map((t) => t.trim());
    }
    if (frame.vocabularyDistractors && frame.vocabularyDistractors.trim()) {
      try {
        const parsed = JSON.parse(frame.vocabularyDistractors);
        if (Array.isArray(parsed)) {
          vocabularyDistractors[index] = parsed.map((row) =>
            Array.isArray(row) ? row.filter((d): d is string => typeof d === "string") : [],
          );
        }
      } catch {
        // Malformed/stale data — treat as absent rather than breaking the quiz.
      }
    }
    if (frame.suggestedAnswer && frame.suggestedAnswer.trim()) {
      suggestedAnswers[index] = frame.suggestedAnswer.trim();
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
    ...(Object.keys(phrases).length > 0 ? { phrases } : {}),
    ...(Object.keys(phrasesTranslation).length > 0 ? { phrasesTranslation } : {}),
    ...(Object.keys(vocabularyPinyin).length > 0 ? { vocabularyPinyin } : {}),
    ...(Object.keys(vocabularyPos).length > 0 ? { vocabularyPos } : {}),
    ...(Object.keys(vocabularyTranslation).length > 0 ? { vocabularyTranslation } : {}),
    ...(Object.keys(vocabularyDistractors).length > 0 ? { vocabularyDistractors } : {}),
    ...(Object.keys(suggestedAnswers).length > 0 ? { suggestedAnswers } : {}),
    ...(Object.keys(listenAudioUrls).length > 0 ? { listenAudioUrls } : {}),
    ...(Object.keys(listenScripts).length > 0 ? { listenScripts } : {}),
    ...(story.linear ? { linear: true } : {}),
    ...(story.lessonNumber != null ? { lessonNumber: story.lessonNumber } : {}),
    narrativeMode: story.narrativeMode ?? "story",
    ...(story.firstFrameIsExample ? { firstFrameIsExample: true } : {}),
  };
}
