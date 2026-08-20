import { persistMeasurementEvent } from "../services/database";

/** Versioned learning-measurement contract shared by student flows and the
 * teacher dashboard. Events are append-only facts; derived metrics belong in
 * dashboard selectors so the raw evidence remains auditable. */

export const MEASUREMENT_SCHEMA_VERSION = "learning-events.v1";
export const MEASUREMENT_STORAGE_KEY = "mandarin-speaking.measurement-events.v1";

export type MeasurementEventName =
  | "practice_started"
  | "reference_played"
  | "recording_submitted"
  | "analysis_completed"
  | "feedback_opened"
  | "practice_retry_submitted"
  | "practice_passed";

export type ExperimentCondition = "control" | "experimental" | "unassigned";

export interface MeasurementEvent {
  eventId: string;
  schemaVersion: typeof MEASUREMENT_SCHEMA_VERSION;
  name: MeasurementEventName;
  occurredAt: string;
  studentId?: string | null;
  classId?: string | null;
  sessionId?: string | null;
  attemptId?: string | null;
  topicId?: string | null;
  sceneIndex?: number | null;
  questionId?: string | null;
  condition?: ExperimentCondition;
  properties: Record<string, string | number | boolean | null>;
}

export interface MeasurementSummary {
  attempts: number;
  analyzed: number;
  passRate: number | null;
  averageTone: number | null;
  averageFluency: number | null;
  notEnoughEvidenceRate: number | null;
  averageRetries: number | null;
}

function mean(values: number[]): number | null {
  return values.length === 0
    ? null
    : Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 10) / 10;
}

export function createMeasurementEvent(
  name: MeasurementEventName,
  fields: Omit<MeasurementEvent, "eventId" | "schemaVersion" | "name" | "occurredAt" | "properties"> & {
    properties?: MeasurementEvent["properties"];
  } = {},
): MeasurementEvent {
  return {
    eventId: globalThis.crypto?.randomUUID?.() ?? `evt-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    schemaVersion: MEASUREMENT_SCHEMA_VERSION,
    name,
    occurredAt: new Date().toISOString(),
    ...fields,
    properties: fields.properties ?? {},
  };
}

export function recordMeasurementEvent(event: MeasurementEvent): void {
  if (typeof window === "undefined") return;
  try {
    const stored = JSON.parse(window.localStorage.getItem(MEASUREMENT_STORAGE_KEY) ?? "[]");
    const events = Array.isArray(stored) ? stored : [];
    events.push(event);
    window.localStorage.setItem(MEASUREMENT_STORAGE_KEY, JSON.stringify(events.slice(-2000)));
  } catch {
    // Measurement must never block a learner's recording flow.
  }
  // Server persistence is best-effort: learner feedback must remain usable
  // even when the API is temporarily offline. The local buffer remains a
  // short-lived recovery queue for the pilot.
  void persistMeasurementEvent(event).catch(() => {});
}

export function summarizeMeasurements(
  records: Array<{ praatMetrics?: { tone_accuracy?: number; fluency_score?: number; pronunciation_mastery?: { passed?: boolean; status?: string }; feedback_quality?: { status?: string } } }>,
): MeasurementSummary {
  const analyzed = records.filter((record) => record.praatMetrics);
  const tone = analyzed.flatMap((record) => typeof record.praatMetrics?.tone_accuracy === "number" ? [record.praatMetrics.tone_accuracy] : []);
  const fluency = analyzed.flatMap((record) => typeof record.praatMetrics?.fluency_score === "number" ? [record.praatMetrics.fluency_score] : []);
  const passed = analyzed.filter((record) => record.praatMetrics?.pronunciation_mastery?.passed === true).length;
  const notEnough = analyzed.filter((record) => record.praatMetrics?.feedback_quality?.status === "retry" || record.praatMetrics?.pronunciation_mastery?.status === "not_judged").length;
  return {
    attempts: records.length,
    analyzed: analyzed.length,
    passRate: analyzed.length ? Math.round((passed / analyzed.length) * 1000) / 10 : null,
    averageTone: mean(tone),
    averageFluency: mean(fluency),
    notEnoughEvidenceRate: analyzed.length ? Math.round((notEnough / analyzed.length) * 1000) / 10 : null,
    averageRetries: null,
  };
}
