import { getTopicVocabulary } from "../components/TopicSelector";
import type { VocabQuizAttempt } from "../services/database";
import { loadPublishedTeacherTopics, type NarrativeMode } from "./teacherStories";
import type { AudioRecord, CustomStoryValidationErrors } from "../pages/MyStoriesPage";

export function getStudentTopics() {
  return loadPublishedTeacherTopics();
}

export interface PromptImage {
  topicId: string;
  topicName: string;
  description: string;
  imageUrl: string;
  imageIndex: number;
  vocabulary: string[];
}

export function getPromptImages(topics = getStudentTopics()): PromptImage[] {
  return topics.flatMap((topic) =>
    topic.images.map((imageUrl, imageIndex) => ({
      topicId: topic.id,
      topicName: topic.name,
      description: topic.description,
      imageUrl,
      imageIndex,
      vocabulary: getTopicVocabulary(topic, imageIndex),
    })),
  );
}

/** Normal-mode stories are a 6-scene story; Describe/Listen & Retell are single-frame activities. */
export function frameCountForMode(mode: NarrativeMode): number {
  return mode === "story" ? 6 : 1;
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

export function getAverageMetric(records: AudioRecord[], metric: string): number | null {
  if (records.length === 0) {
    return null;
  }

  const total = records.reduce(
    (sum, record) => sum + (record.praatMetrics?.[metric] || 0),
    0,
  );
  return Math.round(total / records.length);
}

export interface StudentQuizStats {
  studentName: string;
  attempts: number;
  totalQuestions: number;
  accuracyPct: number;
  avgTimePerQuestionMs: number;
  topMissedWord: { word: string; missCount: number } | null;
}

export interface WordMissStats {
  word: string;
  timesAsked: number;
  timesMissed: number;
  missRatePct: number;
  avgTimeMs: number;
}

export function computeStudentQuizStats(attempts: VocabQuizAttempt[]): StudentQuizStats[] {
  const byStudent = new Map<string, VocabQuizAttempt[]>();
  for (const attempt of attempts) {
    const list = byStudent.get(attempt.studentName) ?? [];
    list.push(attempt);
    byStudent.set(attempt.studentName, list);
  }

  return Array.from(byStudent.entries())
    .map(([studentName, studentAttempts]) => {
      const totalQuestions = studentAttempts.reduce((sum, a) => sum + a.totalQuestions, 0);
      const correctCount = studentAttempts.reduce((sum, a) => sum + a.correctCount, 0);
      const totalTimeMs = studentAttempts.reduce((sum, a) => sum + a.totalTimeMs, 0);

      const missCounts = new Map<string, number>();
      for (const attempt of studentAttempts) {
        for (const result of attempt.questionResults) {
          if (!result.correct) {
            missCounts.set(result.word, (missCounts.get(result.word) ?? 0) + 1);
          }
        }
      }
      let topMissedWord: { word: string; missCount: number } | null = null;
      for (const [word, missCount] of missCounts.entries()) {
        if (!topMissedWord || missCount > topMissedWord.missCount) {
          topMissedWord = { word, missCount };
        }
      }

      return {
        studentName,
        attempts: studentAttempts.length,
        totalQuestions,
        accuracyPct: totalQuestions > 0 ? Math.round((correctCount / totalQuestions) * 100) : 0,
        avgTimePerQuestionMs:
          totalQuestions > 0 ? Math.round(totalTimeMs / totalQuestions) : 0,
        topMissedWord,
      };
    })
    .sort((a, b) => b.attempts - a.attempts);
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

export type WordMissSeverity = "critical" | "watch" | "ok";

/** Miss rate is the % of asks a word is gotten wrong — a small-sample word
 * missed once can swing to 100%, so this is a triage signal, not a verdict. */
export function wordMissSeverity(missRatePct: number): WordMissSeverity {
  if (missRatePct >= 60) return "critical";
  if (missRatePct >= 30) return "watch";
  return "ok";
}

/** Turns the ranked word-miss table into a one-paragraph reading for a
 * teacher: which word to act on first, and whether mistakes are concentrated
 * (a few words worth a class-wide review) or spread thin across many words. */
export function summarizeWordMissTrends(stats: WordMissStats[], shownCount: number): string {
  if (stats.length === 0) return "";

  const top = stats[0];
  const criticalCount = stats.filter((w) => wordMissSeverity(w.missRatePct) === "critical").length;
  const totalMisses = stats.reduce((sum, w) => sum + w.timesMissed, 0);

  const topSentence =
    `"${top.word}" is missed most often — ${top.timesMissed} of ${top.timesAsked} attempts` +
    ` (${top.missRatePct}%), averaging ${(top.avgTimeMs / 1000).toFixed(1)}s to answer.`;

  const spreadSentence =
    criticalCount === 0
      ? `No word has crossed a 60% miss rate — mistakes are spread across ${stats.length} words rather than concentrated, so a quick review of the list below should cover it.`
      : criticalCount === 1
        ? `1 word is at a critical (≥60%) miss rate and is responsible for outsized trouble — start there.`
        : `${criticalCount} words are at a critical (≥60%) miss rate out of ${stats.length} missed overall — worth a focused, class-wide review before moving on.`;

  const coverageNote =
    shownCount < stats.length
      ? ` Showing the top ${shownCount} of ${stats.length} missed words (${totalMisses} total misses) for this filter.`
      : "";

  return `${topSentence} ${spreadSentence}${coverageNote}`;
}

export function narrativeModeLabel(mode?: NarrativeMode): string {
  switch (mode) {
    case "describe":
      return "Descriptive";
    case "listen_retell":
      return "Listen & Retell";
    default:
      return "Normal mode";
  }
}

export function hasCustomStoryErrors(errors: CustomStoryValidationErrors): boolean {
  return Boolean(
    errors.title ||
      errors.learningGoal ||
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

export interface VocabWordSuggestion {
  word: string;
  pinyin: string;
  pos: string;
  translation: string;
}

/** Non-destructively folds AI-suggested word rows into what's already in the
 * table: a row the teacher already has keeps every cell they typed, only its
 * blank cells get filled; a suggested word with no matching row is appended
 * as a new row. Never removes or overwrites a cell the teacher already filled in. */
export function mergeVocabSuggestions(
  existingRows: VocabRow[],
  suggestions: VocabWordSuggestion[],
): VocabRow[] {
  const rows = existingRows.map((row) => ({ ...row }));
  for (const suggestion of suggestions) {
    const match = rows.find((row) => row.word === suggestion.word);
    if (match) {
      if (!match.pinyin.trim()) match.pinyin = suggestion.pinyin;
      if (!match.pos.trim()) match.pos = suggestion.pos;
      if (!match.translation.trim()) match.translation = suggestion.translation;
    } else {
      rows.push({ ...suggestion });
    }
  }
  return rows;
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

export interface PhraseSuggestion {
  phrase: string;
  translation: string;
}

/** Non-destructively folds AI-suggested phrases into what's already in the
 * table: a phrase the teacher already has keeps its typed translation (only
 * fills it in if blank), and a suggested phrase with no matching row is
 * appended as a new row — mirrors mergeVocabSuggestions. */
export function mergePhraseSuggestions(
  existingRows: PhraseRow[],
  suggestions: PhraseSuggestion[],
): PhraseRow[] {
  const rows = existingRows.map((row) => ({ ...row }));
  for (const suggestion of suggestions) {
    const match = rows.find((row) => row.phrase === suggestion.phrase);
    if (match) {
      if (!match.translation.trim()) match.translation = suggestion.translation;
    } else {
      rows.push({ ...suggestion });
    }
  }
  return rows;
}

export function getSessionName(storageKey: string, fallback: string) {
  try {
    const session = JSON.parse(localStorage.getItem(storageKey) || "{}");
    return typeof session.name === "string" && session.name.trim()
      ? session.name.trim()
      : fallback;
  } catch {
    return fallback;
  }
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

export function getAudioUploadError(file: File): string {
  if (!file.type.startsWith("audio/")) {
    return "Please upload an audio file.";
  }

  if (file.size > 5_000_000) {
    return "This audio file is too large. Use a clip under 5 MB.";
  }

  return "";
}

export function isPromptRecord(record: AudioRecord, prompt: PromptImage): boolean {
  return (
    record.imageUrl === prompt.imageUrl ||
    (record.topicId === prompt.topicId && record.imageIndex === prompt.imageIndex)
  );
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
  return topic?.name || "故事 Story";
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
