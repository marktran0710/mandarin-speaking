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
  // JSON-encoded array of arrays (one entry per word, aligned with the
  // comma-split `vocabulary` above) — each word's entry is a list of
  // AI-generated {sentence, distractors} cloze candidates, grown the same
  // way vocabularyDistractors is.
  vocabularyCloze?: string;
  // JSON-encoded array of arrays (one entry per word) — each word's entry
  // is a list of AI-generated {synonym, distractors} candidates, grown the
  // same way vocabularyCloze is.
  vocabularySynonym?: string;
  // JSON-encoded array of arrays (one entry per word) — each word's entry
  // is a list of AI-generated visually-confusable words (喝/渴), grown the
  // same way vocabularyDistractors is.
  vocabularyLookalike?: string;
  suggestedAnswer?: string;
  listenAudioUrl?: string;
  listenScript?: string;
  // Medium/Hard tiers of the same scene — same imageUrl/plot, progressively
  // more complex text. Absent means that tier hasn't been authored yet.
  promptMedium?: string;
  promptHard?: string;
  vocabularyMedium?: string;
  vocabularyHard?: string;
  vocabularyPinyinMedium?: string;
  vocabularyPinyinHard?: string;
  vocabularyPosMedium?: string;
  vocabularyPosHard?: string;
  vocabularyTranslationMedium?: string;
  vocabularyTranslationHard?: string;
  phrasesMedium?: string;
  phrasesHard?: string;
  phrasesTranslationMedium?: string;
  phrasesTranslationHard?: string;
  suggestedAnswerMedium?: string;
  suggestedAnswerHard?: string;
  listenAudioUrlMedium?: string;
  listenAudioUrlHard?: string;
  listenScriptMedium?: string;
  listenScriptHard?: string;
}

export type NarrativeMode = "story" | "describe" | "listen_retell";

export interface CustomTeacherStory {
  id: string;
  title: string;
  learningGoal: string;
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
    .map((story) => storyToTopic(story));
}

/** A story is authored once per scene, at the Easy tier, then optionally
 * gains Medium/Hard variants of the same text fields (same imageUrl/plot).
 * Picking a level just changes which tier of text storyToTopic reads. */
export type StoryDifficultyLevel = "easy" | "medium" | "hard";

const TIER_SUFFIX: Record<StoryDifficultyLevel, ""  | "Medium" | "Hard"> = {
  easy: "",
  medium: "Medium",
  hard: "Hard",
};

type TieredField =
  | "prompt"
  | "vocabulary"
  | "vocabularyPinyin"
  | "vocabularyPos"
  | "vocabularyTranslation"
  | "phrases"
  | "phrasesTranslation"
  | "suggestedAnswer"
  | "listenAudioUrl"
  | "listenScript";

/** Read a frame's text for the given tier, falling back to the base (Easy)
 * field when that tier hasn't been authored yet — so a partially-filled-in
 * Medium/Hard story still shows workable content instead of blanks. */
function tierText(
  frame: CustomStoryFrame,
  base: TieredField,
  level: StoryDifficultyLevel,
): string | undefined {
  const baseValue = frame[base];
  if (level === "easy") return baseValue;
  const suffixed = frame[`${base}${TIER_SUFFIX[level]}` as keyof CustomStoryFrame] as
    | string
    | undefined;
  return suffixed && suffixed.trim() ? suffixed : baseValue;
}

/** Whether a story has any teacher-authored content for Medium/Hard beyond
 * the Easy fields — lets the student-facing level picker hide tiers that
 * would just silently fall back to Easy text. */
export function storyHasTierContent(
  story: CustomTeacherStory,
  level: "medium" | "hard",
): boolean {
  const suffix = TIER_SUFFIX[level];
  const fields: TieredField[] = [
    "prompt",
    "vocabulary",
    "vocabularyPinyin",
    "vocabularyPos",
    "vocabularyTranslation",
    "phrases",
    "phrasesTranslation",
    "suggestedAnswer",
    "listenAudioUrl",
    "listenScript",
  ];
  return story.frames.some((frame) =>
    fields.some((base) => {
      const value = frame[`${base}${suffix}` as keyof CustomStoryFrame] as string | undefined;
      return Boolean(value && value.trim());
    }),
  );
}

export function storyToTopic(
  story: CustomTeacherStory,
  difficultyLevel: StoryDifficultyLevel = "easy",
): Topic {
  const vocabulary = story.frames.reduce<Record<number, string[]>>(
    (allWords, frame, index) => ({
      ...allWords,
      [index]: (tierText(frame, "vocabulary", difficultyLevel) || "")
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
  const vocabularyLookalike: Record<number, string[][]> = {};
  const vocabularyCloze: Record<number, Array<{ sentence: string; distractors: string[] }[]>> = {};
  const vocabularySynonym: Record<number, Array<{ synonym: string; distractors: string[] }[]>> = {};
  const suggestedAnswers: Record<number, string> = {};
  const listenAudioUrls: Record<number, string> = {};
  const listenScripts: Record<number, string> = {};
  story.frames.forEach((frame, index) => {
    if (frame.vocabularyGroups && frame.vocabularyGroups.length > 0) {
      vocabularyGroups[index] = frame.vocabularyGroups;
    }
    const framePhrases = tierText(frame, "phrases", difficultyLevel);
    if (framePhrases && framePhrases.trim()) {
      phrases[index] = framePhrases
        .split(",")
        .map((p) => p.trim())
        .filter(Boolean);
    }
    const framePhrasesTranslation = tierText(frame, "phrasesTranslation", difficultyLevel);
    if (framePhrasesTranslation && framePhrasesTranslation.trim()) {
      phrasesTranslation[index] = framePhrasesTranslation
        .split(",")
        .map((t) => t.trim());
    }
    const frameVocabularyPinyin = tierText(frame, "vocabularyPinyin", difficultyLevel);
    if (frameVocabularyPinyin && frameVocabularyPinyin.trim()) {
      vocabularyPinyin[index] = frameVocabularyPinyin
        .split(",")
        .map((p) => numericToToneMarked(p.trim()));
    }
    const frameVocabularyPos = tierText(frame, "vocabularyPos", difficultyLevel);
    if (frameVocabularyPos && frameVocabularyPos.trim()) {
      vocabularyPos[index] = frameVocabularyPos
        .split(",")
        .map((p) => p.trim());
    }
    const frameVocabularyTranslation = tierText(frame, "vocabularyTranslation", difficultyLevel);
    if (frameVocabularyTranslation && frameVocabularyTranslation.trim()) {
      vocabularyTranslation[index] = frameVocabularyTranslation
        .split(",")
        .map((t) => t.trim());
    }
    // vocabularyDistractors isn't tiered — it's regenerated per word by a
    // dedicated AI endpoint rather than authored text, and isn't currently
    // persisted by the backend at all (a separate, pre-existing gap).
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
    // Same "not tiered, AI-grown rather than authored" story as
    // vocabularyDistractors above.
    if (frame.vocabularyLookalike && frame.vocabularyLookalike.trim()) {
      try {
        const parsed = JSON.parse(frame.vocabularyLookalike);
        if (Array.isArray(parsed)) {
          vocabularyLookalike[index] = parsed.map((row) =>
            Array.isArray(row) ? row.filter((d): d is string => typeof d === "string") : [],
          );
        }
      } catch {
        // Malformed/stale data — treat as absent rather than breaking the quiz.
      }
    }
    // Same "not tiered, AI-grown rather than authored" story as
    // vocabularyDistractors above.
    if (frame.vocabularyCloze && frame.vocabularyCloze.trim()) {
      try {
        const parsed = JSON.parse(frame.vocabularyCloze);
        if (Array.isArray(parsed)) {
          vocabularyCloze[index] = parsed.map((row) =>
            Array.isArray(row)
              ? row.filter(
                  (c): c is { sentence: string; distractors: string[] } =>
                    Boolean(c) && typeof c.sentence === "string" && Array.isArray(c.distractors),
                )
              : [],
          );
        }
      } catch {
        // Malformed/stale data — treat as absent rather than breaking the quiz.
      }
    }
    // Same "not tiered, AI-grown rather than authored" story as
    // vocabularyCloze above.
    if (frame.vocabularySynonym && frame.vocabularySynonym.trim()) {
      try {
        const parsed = JSON.parse(frame.vocabularySynonym);
        if (Array.isArray(parsed)) {
          vocabularySynonym[index] = parsed.map((row) =>
            Array.isArray(row)
              ? row.filter(
                  (c): c is { synonym: string; distractors: string[] } =>
                    Boolean(c) && typeof c.synonym === "string" && Array.isArray(c.distractors),
                )
              : [],
          );
        }
      } catch {
        // Malformed/stale data — treat as absent rather than breaking the quiz.
      }
    }
    const frameSuggestedAnswer = tierText(frame, "suggestedAnswer", difficultyLevel);
    if (frameSuggestedAnswer && frameSuggestedAnswer.trim()) {
      suggestedAnswers[index] = frameSuggestedAnswer.trim();
    }
    const frameListenAudioUrl = tierText(frame, "listenAudioUrl", difficultyLevel);
    if (frameListenAudioUrl && frameListenAudioUrl.trim()) {
      listenAudioUrls[index] = resolveImageUrl(frameListenAudioUrl.trim());
    }
    const frameListenScript = tierText(frame, "listenScript", difficultyLevel);
    if (frameListenScript && frameListenScript.trim()) {
      listenScripts[index] = frameListenScript.trim();
    }
  });

  // Easy keeps the story's original id (no behavior change for existing
  // single-tier stories); Medium/Hard get their own id so vocab-quiz
  // completion, scene recordings, and submissions track independently per
  // tier instead of colliding with Easy's.
  const topicId =
    difficultyLevel === "easy"
      ? `teacher-${story.id}`
      : `teacher-${story.id}-${difficultyLevel}`;

  return {
    id: topicId,
    name: story.title,
    description: story.learningGoal,
    skillFocus: "Teacher published activity",
    images: story.frames.map((frame) => resolveImageUrl(frame.imageUrl)),
    prompts: story.frames.map((frame) => tierText(frame, "prompt", difficultyLevel) || ""),
    vocabulary,
    ...(Object.keys(vocabularyGroups).length > 0 ? { vocabularyGroups } : {}),
    ...(Object.keys(phrases).length > 0 ? { phrases } : {}),
    ...(Object.keys(phrasesTranslation).length > 0 ? { phrasesTranslation } : {}),
    ...(Object.keys(vocabularyPinyin).length > 0 ? { vocabularyPinyin } : {}),
    ...(Object.keys(vocabularyPos).length > 0 ? { vocabularyPos } : {}),
    ...(Object.keys(vocabularyTranslation).length > 0 ? { vocabularyTranslation } : {}),
    ...(Object.keys(vocabularyDistractors).length > 0 ? { vocabularyDistractors } : {}),
    ...(Object.keys(vocabularyLookalike).length > 0 ? { vocabularyLookalike } : {}),
    ...(Object.keys(vocabularyCloze).length > 0 ? { vocabularyCloze } : {}),
    ...(Object.keys(vocabularySynonym).length > 0 ? { vocabularySynonym } : {}),
    ...(Object.keys(suggestedAnswers).length > 0 ? { suggestedAnswers } : {}),
    ...(Object.keys(listenAudioUrls).length > 0 ? { listenAudioUrls } : {}),
    ...(Object.keys(listenScripts).length > 0 ? { listenScripts } : {}),
    ...(story.linear ? { linear: true } : {}),
    ...(story.lessonNumber != null ? { lessonNumber: story.lessonNumber } : {}),
    narrativeMode: story.narrativeMode ?? "story",
    ...(story.firstFrameIsExample ? { firstFrameIsExample: true } : {}),
    difficultyLevel,
    sourceStory: story,
  };
}
