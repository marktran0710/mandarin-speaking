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
  round: 1 | 2 | 3;
  tier: "tier1" | "tier2" | "tier3";
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

export interface PlacementMetric {
  responseCount: number;
  correctCount: number;
  incorrectCount: number;
  accuracy: number;
}

export interface PlacementImportedResponse {
  order: number;
  itemId: string;
  wordId: string;
  word: string;
  lessonId: string;
  questionType: string;
  tier: string;
  selectedAnswer: string;
  correctAnswer: string;
  correct: boolean;
  responseTimeMs: number;
  pLearned: number | null;
  observationCount: number;
  status: string;
}

export interface PlacementImportedStudent {
  studentId: string;
  name: string;
  sessionId: string;
  attemptId: string;
  attemptStatus: string;
  blueprintRevision: number | null;
  completedAt: string | null;
  totalQuestions: number;
  correctCount: number;
  totalTimeMs: number;
  accuracy: number;
  tier1: PlacementMetric;
  tier3: PlacementMetric;
  mastery: {
    rowCount: number;
    statuses: Record<string, number>;
    minPLearned: number | null;
    maxPLearned: number | null;
  };
  responses: PlacementImportedResponse[];
}

export interface PlacementImportResults {
  available: boolean;
  evidenceOrigin: string;
  resolverVersion: string;
  importedAt: string | null;
  summary: PlacementMetric & {
    studentCount: number;
    attemptCount: number;
    masteryRowCount: number;
    masteryStatuses: Record<string, number>;
    tier1: PlacementMetric;
    tier3: PlacementMetric;
  };
  modelVersions: string[];
  parameterFingerprints: string[];
  students: PlacementImportedStudent[];
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

export async function getAdminPlacementImportResults(): Promise<PlacementImportResults> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/placement-test/results`);
  if (!response.ok) throw await parseError(response, "Could not load placement data");
  return response.json() as Promise<PlacementImportResults>;
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
