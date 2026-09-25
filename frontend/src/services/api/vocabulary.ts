import { BACKEND_URL, fetchWithRetry } from "./client";
import type { StoredCustomStory } from "./stories-submissions";

export type QuizVocabularyLevel = "Easy" | "Medium" | "Hard";
export interface QuizVocabularyQuestionDraft {
  level: QuizVocabularyLevel;
  prompt: string;
  options: string[];
  correctAnswer: string;
  acceptedAnswers: string[];
  explanation: string;
}
export interface QuizVocabularyWordDraft {
  wordId?: string;
  expectedRevision?: string;
  targetWord: string;
  pinyin: string;
  pos: string;
  simpleEnglishMeaning: string;
  questions: QuizVocabularyQuestionDraft[];
}

export interface VocabularyMetadataEdit {
  frameIndex: number;
  wordIndex: number;
  storyWide?: boolean;
  assessmentWordId?: string;
  tier: "easy" | "medium" | "hard";
  word: string;
  expected: { vocabulary: string; pinyin: string; translation: string; pos: string };
  pinyin: string;
  translation: string;
  pos: string;
}

export async function listVocabularyStories(): Promise<StoredCustomStory[]> {
  const stories: StoredCustomStory[] = [];
  for (let skip = 0; ; skip += 500) {
    const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/content-bank?limit=500&skip=${skip}`);
    if (!response.ok) {
      const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
      const detail = typeof payload?.detail === "string" ? ` ${payload.detail}` : "";
      throw new Error(`Could not load Speaking vocabulary (${response.status}).${detail}`);
    }
    const page: unknown = await response.json();
    if (!Array.isArray(page)) throw new Error("The server returned an invalid story list.");
    stories.push(...page as StoredCustomStory[]);
    if (page.length < 500) return stories;
  }
}

export async function updateVocabularyMetadata(storyId: string, edit: VocabularyMetadataEdit): Promise<StoredCustomStory> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/vocabulary-metadata`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(edit),
  }, 1);
  if (!response.ok) {
    if (response.status === 409) throw new Error("This vocabulary changed in another session. Close the editor and refresh before saving again.");
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : "Could not save vocabulary. Check your admin session and try again.");
  }
  return response.json() as Promise<StoredCustomStory>;
}

async function mutateQuizVocabulary(
  storyId: string,
  path: string,
  method: "POST" | "PUT" | "DELETE",
  body?: QuizVocabularyWordDraft,
): Promise<StoredCustomStory> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/quiz-vocabulary${path}`, {
    method,
    ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
  }, 1);
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = payload?.detail;
    const message = formatQuizVocabularyError(detail);
    if (response.status === 409) throw new Error(typeof detail === "string" ? detail : "Quiz vocabulary changed. Refresh before saving again.");
    throw new Error(message || "Could not update quiz vocabulary.");
  }
  return response.json() as Promise<StoredCustomStory>;
}

function formatQuizVocabularyError(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (!detail || typeof detail !== "object") return "";
  const value = detail as { message?: unknown; issues?: unknown };
  const message = typeof value.message === "string" ? value.message : "";
  const issues = Array.isArray(value.issues)
    ? value.issues.map((issue) => {
      if (!issue || typeof issue !== "object") return "";
      const item = issue as { code?: unknown; message?: unknown; question_id?: unknown };
      const prefix = typeof item.question_id === "string" && item.question_id ? `${item.question_id}: ` : "";
      const code = typeof item.code === "string" && item.code ? `[${item.code}] ` : "";
      return `${prefix}${code}${typeof item.message === "string" ? item.message : ""}`.trim();
    }).filter(Boolean)
    : [];
  return [message, ...issues].filter(Boolean).join(" ");
}

export function createQuizVocabularyWord(storyId: string, draft: QuizVocabularyWordDraft): Promise<StoredCustomStory> {
  return mutateQuizVocabulary(storyId, "", "POST", draft);
}

export function updateQuizVocabularyWord(storyId: string, wordId: string, draft: QuizVocabularyWordDraft): Promise<StoredCustomStory> {
  return mutateQuizVocabulary(storyId, `/${encodeURIComponent(wordId)}`, "PUT", draft);
}

export function deleteQuizVocabularyWord(storyId: string, wordId: string, expectedRevision?: string | null): Promise<StoredCustomStory> {
  const path = `/${encodeURIComponent(wordId)}${expectedRevision ? `?expectedRevision=${encodeURIComponent(expectedRevision)}` : ""}`;
  return mutateQuizVocabulary(storyId, path, "DELETE");
}

export interface VocabularyImportSection {
  section: string;
  storyId: string | null;
  storyTitle: string | null;
  found: boolean;
  error?: string;
  newWords: number;
  updatedWords: number;
  removedWords: number;
  preservedAudio: number;
  missingAudio: number;
  questionCount: number;
  issues: string[];
}
export interface VocabularyImportPreview {
  mode: "replace_lesson";
  rows: number;
  rowIssues: string[];
  sections: VocabularyImportSection[];
  newWords: number;
  updatedWords: number;
  removedWords: number;
  preservedAudio: number;
  missingAudio: number;
}
export interface VocabularyImportResult {
  mode: "replace_lesson";
  published: Array<{
    section: string;
    storyId: string;
    storyTitle: string;
    questionCount: number;
    newWords: number;
    updatedWords: number;
    removedWords: number;
    preservedAudio: number;
    missingAudio: number;
  }>;
  newWords: number;
  updatedWords: number;
  removedWords: number;
  preservedAudio: number;
  missingAudio: number;
}

async function postVocabularyImport<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  body.append("mode", "replace_lesson");
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/vocabulary-import/${path}`, { method: "POST", body }, 1);
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "Could not process the import file.");
  }
  return response.json() as Promise<T>;
}

/** Read-only: parse and validate, report what would change. Writes nothing. */
export function previewVocabularyImport(file: File): Promise<VocabularyImportPreview> {
  return postVocabularyImport<VocabularyImportPreview>("preview", file);
}

/** Re-validates the file from scratch server-side and replaces each matched
 * lesson's canonical quiz bank by Word Key. */
export function confirmVocabularyImport(file: File): Promise<VocabularyImportResult> {
  return postVocabularyImport<VocabularyImportResult>("confirm", file);
}

export async function downloadVocabularyImportTemplate(): Promise<Blob> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/vocabulary-import/template`);
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "Could not download the import template.");
  }
  return response.blob();
}

export async function downloadVocabularyAudioSample(): Promise<Blob> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/vocabulary-audio-import/template`);
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "Could not download the audio sample ZIP.");
  }
  return response.blob();
}

export interface VocabularyAudioMatch {
  filename: string;
  wordKey: string;
  storyId: string;
  storyTitle: string;
  bytes: number;
}

export interface VocabularyAudioImportPreview {
  files: number;
  matched: VocabularyAudioMatch[];
  unmatched: string[];
  issues: string[];
}

export interface VocabularyAudioImportResult {
  files: number;
  updated: number;
  unmatched: string[];
  unmatchedAudio: string[];
  stories: string[];
}

async function postVocabularyAudioImport<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/vocabulary-audio-import/${path}`, { method: "POST", body }, 1);
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "Could not process the audio import.");
  }
  return response.json() as Promise<T>;
}

/** Read-only: match ZIP filenames to canonical vocabulary Word Keys. */
export function previewVocabularyAudioImport(file: File): Promise<VocabularyAudioImportPreview> {
  return postVocabularyAudioImport<VocabularyAudioImportPreview>("preview", file);
}

/** Re-validates the ZIP and persists matched audio on the canonical word bank. */
export function confirmVocabularyAudioImport(file: File): Promise<VocabularyAudioImportResult> {
  return postVocabularyAudioImport<VocabularyAudioImportResult>("confirm", file);
}
