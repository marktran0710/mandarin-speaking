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
    const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories?limit=500&skip=${skip}`);
    if (!response.ok) throw new Error("Could not load Speaking vocabulary. Check your admin session and try again.");
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
    if (response.status === 409) throw new Error(typeof detail === "string" ? detail : "Quiz vocabulary changed. Refresh before saving again.");
    throw new Error(typeof detail === "string" ? detail : "Could not update quiz vocabulary.");
  }
  return response.json() as Promise<StoredCustomStory>;
}

export function createQuizVocabularyWord(storyId: string, draft: QuizVocabularyWordDraft): Promise<StoredCustomStory> {
  return mutateQuizVocabulary(storyId, "", "POST", draft);
}

export function updateQuizVocabularyWord(storyId: string, wordId: string, draft: QuizVocabularyWordDraft): Promise<StoredCustomStory> {
  return mutateQuizVocabulary(storyId, `/${encodeURIComponent(wordId)}`, "PUT", draft);
}

export function deleteQuizVocabularyWord(storyId: string, wordId: string): Promise<StoredCustomStory> {
  return mutateQuizVocabulary(storyId, `/${encodeURIComponent(wordId)}`, "DELETE");
}
