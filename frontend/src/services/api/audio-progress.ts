import { BACKEND_URL, fetchWithRetry } from "./client";
import type { SceneSubmission } from "./stories-submissions";
import { buildPracticeAnalysisFormData, type PracticeAnalysisRequestContext } from "../../utils/practiceAnalysis";

function snapshotIdFor(result: SceneSubmission): string {
  if (result.snapshotId) return result.snapshotId;
  const generated = typeof globalThis.crypto?.randomUUID === "function"
    ? globalThis.crypto.randomUUID()
    : `snapshot-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  // StoryRecorder spreads this object for same-recording enrichment (audio
  // URL/self-evaluation), so attaching the ID here carries identity through
  // those updates without guessing it from scored content.
  result.snapshotId = generated;
  return generated;
}

export interface StoredAudioRecord { id: string; timestamp: string; duration: number; transcription: string; model: string; topicId?: string; studentId?: string | null; imageUrl?: string; imageIndex?: number; audioUrl?: string; audioName?: string; praatMetrics?: any; analysisVersion?: "stable_v1"; analysisSchemaVersion?: string; modelVersion?: string; comparisonGroupId?: string; sessionId?: string; attemptId?: string; attemptNumber?: number; attemptType?: "WHOLE_SENTENCE_INITIAL" | "FOCUSED_RETRY" | "WHOLE_SENTENCE_FINAL"; serverVerifiedAt?: string | null; audioSha256?: string | null; serverVerificationVersion?: string | null; }
export interface StoredSpeakingProgress { studentId: string; topicId: string; sceneIndex: number; attempts: number; bestTone: number; bestFluency: number; masteryPassed: boolean; contentPassed: boolean; clearedWords: string[]; latestResult?: SceneSubmission | null; baseStoryId?: string; difficultyLevel?: "easy" | "medium" | "hard"; promptId?: string; verifiedAudioRecordId?: string | null; progressionEligible?: boolean; }

export interface VerifiedSpeakingAnalysisResponse {
  serverVerified: true;
  audioRecordId: string;
  audioUrl?: string | null;
  attemptId: string;
  storyId: string;
  baseStoryId: string;
  sceneIndex: number;
  difficultyLevel: "easy" | "medium" | "hard";
  progressionEligible: boolean;
  analysis: any;
  verdicts: {
    pronunciationPassed: boolean;
    contentPassed: boolean;
    masteryPassed: boolean;
  };
}

export async function analyzeVerifiedSpeech(
  audio: Blob,
  context: PracticeAnalysisRequestContext & {
    storyId: string;
    baseStoryId?: string;
    sceneIndex: number;
    difficultyLevel?: "easy" | "medium" | "hard";
  },
): Promise<VerifiedSpeakingAnalysisResponse> {
  if (!context.attemptId?.trim()) throw new Error("A stable speaking attempt ID is required.");
  const formData = buildPracticeAnalysisFormData(audio, context);
  formData.append("story_id", context.storyId);
  formData.append("base_story_id", context.baseStoryId ?? context.storyId);
  formData.append("scene_index", String(context.sceneIndex));
  formData.append("difficulty_level", context.difficultyLevel ?? "easy");
  const response = await fetchWithRetry(`${BACKEND_URL}/api/analyze/verified`, {
    method: "POST",
    body: formData,
    signal: AbortSignal.timeout(120_000),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof detail?.detail === "string" ? detail.detail : "Verified speaking analysis failed.");
  }
  return response.json() as Promise<VerifiedSpeakingAnalysisResponse>;
}

export async function listAudioRecords(params?: { limit?: number; skip?: number; studentId?: string; topicId?: string }): Promise<StoredAudioRecord[]> {
  const queryParams = new URLSearchParams(); if (params?.limit !== undefined) queryParams.set("limit", String(params.limit)); if (params?.skip !== undefined) queryParams.set("skip", String(params.skip)); if (params?.studentId) queryParams.set("student_id", params.studentId); if (params?.topicId) queryParams.set("topic_id", params.topicId);
  const response = await fetchWithRetry(`${BACKEND_URL}/api/audio-records${queryParams.size ? `?${queryParams}` : ""}`); if (!response.ok) throw new Error("Could not load audio records from the database."); const records = await response.json(); return Array.isArray(records) ? records : [];
}
export async function listLatestAudioRecordsByScene(studentId: string, topicId: string): Promise<StoredAudioRecord[]> { const query = new URLSearchParams({ student_id: studentId, topic_id: topicId }); const response = await fetchWithRetry(`${BACKEND_URL}/api/audio-records/latest-by-scene?${query}`); if (!response.ok) throw new Error("Could not load the latest practice results from the database."); const records = await response.json(); return Array.isArray(records) ? records : []; }
export async function getAudioRecordCount(): Promise<number> { const response = await fetchWithRetry(`${BACKEND_URL}/api/audio-records/count`); if (!response.ok) throw new Error("Could not load audio record count from the database."); const data = await response.json() as { total?: unknown }; return typeof data.total === "number" ? data.total : 0; }
export async function createAudioRecord(record: StoredAudioRecord, audioBlob?: Blob): Promise<StoredAudioRecord> { const response = audioBlob ? await uploadAudioRecord(record, audioBlob) : await fetchWithRetry(`${BACKEND_URL}/api/audio-records`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(record) }); if (!response.ok) throw new Error("Could not save audio record to the database."); return response.json() as Promise<StoredAudioRecord>; }
async function uploadAudioRecord(record: StoredAudioRecord, audioBlob: Blob): Promise<Response> { const formData = new FormData(); formData.append("record", JSON.stringify(record)); formData.append("file", audioBlob, `${record.id}.wav`); return fetchWithRetry(`${BACKEND_URL}/api/audio-records/upload`, { method: "POST", body: formData }); }
export async function listSpeakingProgress(studentId: string, topicId: string): Promise<StoredSpeakingProgress[]> { const response = await fetchWithRetry(`${BACKEND_URL}/api/speaking-progress?student_id=${encodeURIComponent(studentId)}&topic_id=${encodeURIComponent(topicId)}`); if (!response.ok) throw new Error("Could not load speaking progress from the database."); const records = await response.json(); return Array.isArray(records) ? records : []; }
export async function saveSpeakingProgress(progress: StoredSpeakingProgress): Promise<StoredSpeakingProgress> { const payload = progress.latestResult ? { ...progress, latestResult: { ...progress.latestResult, snapshotId: snapshotIdFor(progress.latestResult) } } : progress; const response = await fetchWithRetry(`${BACKEND_URL}/api/speaking-progress`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); if (!response.ok) throw new Error("Could not save speaking progress to the database."); return response.json() as Promise<StoredSpeakingProgress>; }
export async function deleteAudioRecordFromDatabase(id: string): Promise<void> { const response = await fetchWithRetry(`${BACKEND_URL}/api/audio-records/${encodeURIComponent(id)}`, { method: "DELETE" }); if (!response.ok) throw new Error("Could not delete audio record from the database."); }
