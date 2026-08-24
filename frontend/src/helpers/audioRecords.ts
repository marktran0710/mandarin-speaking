import { getStudentId } from "../utils/studentSession";
import type { StoredAudioRecord } from "../shared/api/learningApi";
import type { AudioRecord } from "../app/appTypes";

export function serializeAudioRecord(record: AudioRecord): StoredAudioRecord {
  return {
    id: record.id,
    timestamp: record.timestamp,
    duration: record.duration,
    transcription: record.transcription,
    model: record.model,
    topicId: record.topicId,
    studentId: getStudentId(),
    imageUrl: record.imageUrl,
    imageIndex: record.imageIndex,
    audioUrl: record.audioUrl,
    audioName: record.audioName,
    analysisVersion: record.analysisVersion ?? record.praatMetrics?.analysis_version ?? "stable_v1",
    analysisSchemaVersion: record.analysisSchemaVersion ?? record.praatMetrics?.analysis_schema_version,
    modelVersion: record.modelVersion ?? record.praatMetrics?.model_version,
    comparisonGroupId: record.comparisonGroupId,
    sessionId: record.sessionId,
    attemptId: record.attemptId,
    attemptNumber: record.attemptNumber,
    attemptType: record.attemptType,
    praatMetrics: record.praatMetrics,
  };
}

export function writeAudioRecordsCache(records: StoredAudioRecord[]): void {
  const candidates: StoredAudioRecord[][] = [
    records,
    records.slice(0, 100),
    records.slice(0, 30),
    records.slice(0, 10).map(({ praatMetrics: _praatMetrics, ...record }) => record),
  ];
  for (const candidate of candidates) {
    try {
      localStorage.setItem("audioRecords", JSON.stringify(candidate));
      return;
    } catch {
      // Try a smaller cache below. Never let a quota error break the app.
    }
  }
  try {
    localStorage.removeItem("audioRecords");
  } catch {
    // Storage-disabled/private browsing environments can reject this too.
  }
}

export function recordsFromStored(recordsData: StoredAudioRecord[]): AudioRecord[] {
  return recordsData.map((data) => ({
    ...data,
    audioBlob: new Blob([], { type: "audio/webm" }),
    model: data.model as AudioRecord["model"],
  }));
}

export function updateStoredAudioRecord(
  id: string,
  media: Pick<StoredAudioRecord, "audioUrl" | "audioName">,
): void {
  const stored = JSON.parse(localStorage.getItem("audioRecords") || "[]");
  const updated = stored.map((record: StoredAudioRecord) =>
    record.id === id ? { ...record, ...media } : record,
  );
  writeAudioRecordsCache(updated);
}
