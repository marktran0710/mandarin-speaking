import type { VocabQuizAttempt } from "../services/database";
import { loadPublishedTeacherTopics, loadStoryTitle } from "@entities/story";
import type { CustomStoryValidationErrors } from "@features/teacher/components/story-builder/StoryBuilderSection";

export function getStudentTopics() {
  return loadPublishedTeacherTopics();
}

export function resizeToCount<T>(items: T[], count: number, fill: T): T[] {
  if (items.length === count) return items;
  if (items.length > count) return items.slice(0, count);
  return [...items, ...Array.from({ length: count - items.length }, () => fill)];
}

export function quizAttemptAccuracy(attempt: VocabQuizAttempt): number {
  return attempt.totalQuestions > 0
    ? Math.round((attempt.correctCount / attempt.totalQuestions) * 100)
    : 0;
}

export interface WordMissStats {
  word: string;
  timesAsked: number;
  timesMissed: number;
  missRatePct: number;
  avgTimeMs: number;
}

export function computeWordMissStats(attempts: VocabQuizAttempt[]): WordMissStats[] {
  const stats = new Map<string, { asked: number; missed: number; timeMs: number }>();
  for (const attempt of attempts) {
    for (const result of attempt.questionResults) {
      const entry = stats.get(result.word) ?? { asked: 0, missed: 0, timeMs: 0 };
      entry.asked += 1;
      if (!result.correct) entry.missed += 1;
      entry.timeMs += result.timeMs;
      stats.set(result.word, entry);
    }
  }

  return Array.from(stats.entries())
    .map(([word, { asked, missed, timeMs }]) => ({
      word,
      timesAsked: asked,
      timesMissed: missed,
      missRatePct: asked > 0 ? Math.round((missed / asked) * 100) : 0,
      avgTimeMs: asked > 0 ? Math.round(timeMs / asked) : 0,
    }))
    .filter((w) => w.timesMissed > 0)
    .sort((a, b) => b.timesMissed - a.timesMissed || b.missRatePct - a.missRatePct);
}

export function hasCustomStoryErrors(errors: CustomStoryValidationErrors): boolean {
  return Boolean(
    errors.title ||
      errors.form ||
      Object.keys(errors.frames ?? {}).length > 0,
  );
}

export function clearFrameError(
  errors: CustomStoryValidationErrors,
  index: number,
  field:
    | "imageUrls"
    | "prompts"
    | "vocabulary"
    | "vocabularyPinyin"
    | "vocabularyPos"
    | "vocabularyTranslation"
    | "phrases"
    | "phrasesTranslation"
    | "suggestedAnswers"
    | "listenAudioUrls"
    | "listenScripts",
): CustomStoryValidationErrors {
  const frameError = errors.frames?.[index];

  if (!frameError) {
    return { ...errors, form: undefined };
  }

  const nextFrames = { ...errors.frames };
  nextFrames[index] = {
    ...frameError,
    imageUrl: field === "imageUrls" ? undefined : frameError.imageUrl,
    prompt: field === "prompts" ? undefined : frameError.prompt,
  };

  if (!nextFrames[index].imageUrl && !nextFrames[index].prompt) {
    delete nextFrames[index];
  }

  return {
    ...errors,
    form: undefined,
    frames: Object.keys(nextFrames).length > 0 ? nextFrames : undefined,
  };
}

export interface VocabRow {
  word: string;
  pinyin: string;
  pos: string;
  translation: string;
}

export function splitVocabColumn(value: string): string[] {
  if (!value.trim()) return [];
  return value.split(",").map((v) => v.trim());
}

export function buildVocabRows(
  vocabulary: string,
  vocabularyPinyin: string,
  vocabularyPos: string,
  vocabularyTranslation: string,
): VocabRow[] {
  const words = splitVocabColumn(vocabulary);
  const pinyins = splitVocabColumn(vocabularyPinyin);
  const pos = splitVocabColumn(vocabularyPos);
  const translations = splitVocabColumn(vocabularyTranslation);
  return words.map((word, i) => ({
    word,
    pinyin: pinyins[i] || "",
    pos: pos[i] || "",
    translation: translations[i] || "",
  }));
}

export interface PhraseRow {
  phrase: string;
  translation: string;
}

export function splitPhraseColumn(value: string): string[] {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

export function buildPhraseRows(phrases: string, phrasesTranslation: string): PhraseRow[] {
  const rawPhrases = splitPhraseColumn(phrases);
  const translations = splitPhraseColumn(phrasesTranslation);
  return rawPhrases.map((phrase, i) => ({ phrase, translation: translations[i] || "" }));
}

export function formatRequestTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Just now";
  }

  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function getImageUploadError(file: File): string {
  if (!file.type.startsWith("image/")) {
    return "Please upload an image file.";
  }

  if (file.size > 1_500_000) {
    return "This image is too large for browser storage. Use an image under 1.5 MB or paste an image URL.";
  }

  return "";
}

export interface LessonAudioFilenameMatch {
  lessonNumber: number;
  lessonSubOrder: number;
  sceneIndex: number;
}

/** Parses a filename like "5-1-01.mp3" (or "L5_1_s01.m4a") into the lesson
 * number, the story's lessonSubOrder, and a 1-based scene index, by reading
 * the first three integers found. Used by the multi-story bulk audio upload
 * so a teacher can name files instead of opening each story one at a time. */
export function parseLessonAudioFilename(filename: string): LessonAudioFilenameMatch | null {
  // Strip the extension first -- "mp3"/"m4a" etc. contain digits that would
  // otherwise be misread as the scene number (e.g. "5-01.mp3" has only two
  // real numbers, not three).
  const withoutExtension = filename.replace(/\.[^./\\]+$/, "");
  const numbers = (withoutExtension.match(/\d+/g) || []).map(Number);
  if (numbers.length < 3) return null;
  const [lessonNumber, lessonSubOrder, sceneIndex] = numbers;
  if (!lessonNumber || !lessonSubOrder || !sceneIndex) return null;
  return { lessonNumber, lessonSubOrder, sceneIndex };
}

export function getAudioUploadError(file: File): string {
  if (!file.type.startsWith("audio/")) {
    return "Please upload an audio file.";
  }

  if (file.size > 5_000_000) {
    return "This audio file is too large. Use a clip under 5 MB.";
  }

  return "";
}

export function getToneName(tone: number): string {
  const toneNames: Record<number, string> = {
    1: "一聲 High Level (ma1)",
    2: "二聲 Rising (ma2)",
    3: "三聲 Falling-Rising (ma3)",
    4: "四聲 Falling (ma4)",
  };
  return toneNames[tone] || "未知 Unknown";
}

export function getTopicLabel(topicId?: string): string {
  const topic = getStudentTopics().find((item) => item.id === topicId);
  return loadStoryTitle(topicId) || topic?.name || "故事 Story";
}

export function formatContourShape(shape: string): string {
  const labels: Record<string, string> = {
    dip: "低降 Dipping",
    falling: "下降 Falling",
    level: "平直 Level",
    rising: "上升 Rising",
    variable: "不規則 Variable",
  };
  return labels[shape] || "不規則 Variable";
}
