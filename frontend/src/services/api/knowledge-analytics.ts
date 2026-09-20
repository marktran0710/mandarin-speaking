import { BACKEND_URL, fetchWithRetry, REQUEST_TIMEOUT_MS } from "./client";

export type KnowledgeModelName = "pfa" | "bkt" | "compare";

export interface KnowledgeSkillState {
  conceptId: string;
  mastery: number;
  predictedCorrect: number;
  exposures: number;
  successes: number;
  failures: number;
  lastSeenAt: string | null;
  evidenceDepth: "low" | "medium" | "high";
}

export interface KnowledgeStudentState {
  studentId: string;
  studentName?: string;
  skills: KnowledgeSkillState[];
}

export interface KnowledgeEvidenceCheck {
  name: "training_records" | "evaluation_predictions" | "evaluation_positives" | "evaluation_negatives" | "students" | "concepts";
  actual: number;
  minimum: number;
  passed: boolean;
}

export interface KnowledgeFitDiagnostics {
  status: "success" | "failed" | "not_run";
  optimizer: string;
  message: string;
  iterations: number;
  objective: number | null;
  finite: boolean;
}

export interface KnowledgeEvaluation {
  status: "evidence_ready" | "insufficient_evidence" | "fit_failed";
  responseCount: number;
  predictionCount: number;
  positiveCount: number;
  negativeCount: number;
  logLoss: number | null;
  brierScore: number | null;
  calibrationError: number | null;
  auc: number | null;
  evidenceChecks: KnowledgeEvidenceCheck[];
  fitDiagnostics: KnowledgeFitDiagnostics;
}

export interface KnowledgeDataQuality {
  totalAttempts: number;
  totalResponses: number;
  eligibleResponses: number;
  legacyConceptResponses: number;
  skippedResponses: number;
  duplicateResponses: number;
  attemptsWithoutId: number;
  invalidTimestampAttempts: number;
  skillCount: number;
  studentCount: number;
  conceptCount: number;
}

export interface KnowledgeModelResult {
  model: "pfa" | "bkt";
  modelVersion: string;
  implementation: "restricted_pooled_baseline" | "pooled_bkt_pilot";
  parameters?: Record<string, number>;
  masteryInterpretation: "predicted_correct_probability" | "latent_mastery_probability";
  scope: { studentId: string | null; storyId: string | null; level: string | null };
  dataQuality: KnowledgeDataQuality;
  students: KnowledgeStudentState[];
  evaluation: KnowledgeEvaluation;
}

export interface KnowledgeModelComparison {
  model: "compare";
  modelVersion: string;
  scope: { studentId: string | null; storyId: string | null; level: string | null };
  dataQuality: KnowledgeDataQuality;
  models: {
    pfa: KnowledgeModelResult;
    bkt: KnowledgeModelResult;
  };
  lowerLossSignal: "pfa" | "bkt" | "no_material_difference" | null;
}

export type KnowledgeAnalyticsResponse = KnowledgeModelResult | KnowledgeModelComparison;

export async function getKnowledgeModelAnalytics(
  model: KnowledgeModelName = "compare",
  filters: { studentId?: string; storyId?: string; level?: string } = {},
): Promise<KnowledgeAnalyticsResponse> {
  const params = new URLSearchParams({ model });
  if (filters.studentId) params.set("student_id", filters.studentId);
  if (filters.storyId) params.set("story_id", filters.storyId);
  if (filters.level) params.set("level", filters.level);
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/admin/analytics/knowledge-state?${params.toString()}`,
    undefined,
    2,
    REQUEST_TIMEOUT_MS,
  );
  if (!response.ok) throw new Error("Could not load learning model analytics.");
  return response.json() as Promise<KnowledgeAnalyticsResponse>;
}
