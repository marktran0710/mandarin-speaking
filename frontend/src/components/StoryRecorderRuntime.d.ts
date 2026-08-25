import type { StoredAudioRecord } from "../services/database";

declare const StoryRecorderRuntime: unknown;
export default StoryRecorderRuntime;

export function practiceSceneIndicesFor(
  topic: { images: unknown[] },
): number[];
export function sceneSubmissionFromAudioRecord(record: StoredAudioRecord): unknown;
export function attemptHistoryFromAudioRecords(records: StoredAudioRecord[]): Record<number, unknown[]>;
