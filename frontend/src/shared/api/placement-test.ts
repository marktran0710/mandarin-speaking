import { BACKEND_URL, fetchWithRetry } from "./client";

export type PlacementQuestionType =
  | "basic_meaning_mcq"
  | "character_to_pinyin_typing"
  | "context_cloze_mcq";

export interface PlacementQuestion {
  questionId: string;
  sourceStoryId: string;
  sourceStoryTitle: string;
  sourceWordId: string;
  sourceLevel: "easy" | "medium" | "hard";
  position: number;
  questionType: PlacementQuestionType;
  answerFormat: "single_choice" | "free_text";
  targetWord: string;
  prompt: string;
  options: string[];
  audioUrl?: string | null;
}

export interface PlacementBlueprint {
  configured: boolean;
  revision: number | null;
  questionCount: number;
  questions: PlacementQuestion[];
  updatedAt?: string | null;
}

export interface PlacementPreview extends PlacementBlueprint {
  valid: boolean;
  rowIssues: string[];
  currentRevision: number | null;
}

export interface PlacementAttempt {
  attemptId: string;
  revision: number;
  totalQuestions: number;
  questions: PlacementQuestion[];
}

export interface PlacementAnswer {
  questionId: string;
  selectedAnswer: string;
  timeMs: number;
  answeredAt: string;
}

export interface PlacementResult {
  attemptId: string;
  totalQuestions: number;
  correctCount: number;
  percentage: number;
  messageKey: "CONGRATULATIONS" | "KEEP_PRACTICING";
}

async function parseError(response: Response, fallback: string): Promise<Error> {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  return new Error(typeof body?.detail === "string" ? body.detail : `${fallback} (${response.status}).`);
}

export async function getPlacementBlueprint(): Promise<PlacementBlueprint> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/placement-test`);
  if (!response.ok) throw await parseError(response, "Could not load the placement test");
  return response.json() as Promise<PlacementBlueprint>;
}

export async function startPlacementAttempt(): Promise<PlacementAttempt> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/placement-test/attempts`, { method: "POST" }, 1);
  if (!response.ok) throw await parseError(response, "Could not start the placement test");
  return response.json() as Promise<PlacementAttempt>;
}

export async function completePlacementAttempt(attemptId: string, responses: PlacementAnswer[]): Promise<PlacementResult> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/placement-test/attempts/${encodeURIComponent(attemptId)}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ responses, completedAt: new Date().toISOString() }),
  }, 1);
  if (!response.ok) throw await parseError(response, "Could not submit the placement test");
  return response.json() as Promise<PlacementResult>;
}

export async function getAdminPlacementBlueprint(): Promise<PlacementBlueprint> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/placement-test`);
  if (!response.ok) throw await parseError(response, "Could not load the placement blueprint");
  return response.json() as Promise<PlacementBlueprint>;
}

async function uploadPlacementFile(path: string, file: File): Promise<PlacementPreview> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetchWithRetry(`${BACKEND_URL}${path}`, { method: "POST", body: form }, 1);
  if (!response.ok) throw await parseError(response, "Could not validate the placement file");
  return response.json() as Promise<PlacementPreview>;
}

export function previewPlacementImport(file: File): Promise<PlacementPreview> {
  return uploadPlacementFile("/api/admin/placement-test/import/preview", file);
}

export async function confirmPlacementImport(file: File): Promise<PlacementBlueprint> {
  const result = await uploadPlacementFile("/api/admin/placement-test/import/confirm", file);
  return result;
}
