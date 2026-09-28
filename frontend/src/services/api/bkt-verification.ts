import { BACKEND_URL, fetchWithRetry } from "@shared/api/client";

export type VerificationResult = "PASS" | "FAIL" | "NOT TESTED" | "MODEL CONTRACT CHANGED";

export interface BktVerificationModel {
  version: string;
  parameterFingerprint: string;
  goldenFixtureVersion: string;
  contractStatus: "MATCH" | "MODEL CONTRACT CHANGED";
  parameters: {
    pL0: number;
    pT: number;
    mcqGuess: number;
    mcqSlip: number;
    typedGuess: number;
    typedSlip: number;
    masteryThreshold: number;
    minimumObservations: number;
  };
}

export interface BktTraceStep {
  step: number;
  prior: number;
  observation: "Correct" | "Incorrect";
  correct: boolean;
  questionType: string | null;
  guess: number;
  slip: number;
  posterior: number;
  learningTransition: number;
  resultingMastery: number;
}

export interface GoldenCheck {
  id: string;
  scenario: string;
  input: Array<{ correct: boolean; questionType: string }>;
  expected: {
    pLearned: number;
    observationCount: number;
    status: string;
    trace: BktTraceStep[];
  };
  actual: {
    pLearned: number;
    observationCount: number;
    status: string;
    trace: BktTraceStep[];
  };
  result: VerificationResult;
  tolerance: number;
}

export interface GoldenReport {
  contractStatus: "MATCH" | "MODEL CONTRACT CHANGED";
  fixtureVersion: string;
  targetParameterFingerprint: string;
  checks: GoldenCheck[];
  summary: { passed: number; total: number };
}

export interface VerificationStudent {
  studentId: string;
  name: string;
  status: string;
  isTestAccount: boolean;
}

export interface BktVerificationBootstrap {
  model: BktVerificationModel;
  golden: GoldenReport;
  students: VerificationStudent[];
}

export interface VerificationWord {
  wordId: string;
  word: string;
  meaning: string | null;
  lessonId: string | null;
  pLearned: number;
  observationCount: number;
  status: string;
  reviewStatus: string;
}

export interface EvidenceItem {
  order: number;
  timestamp: string | null;
  activityType: string;
  quizMode: string | null;
  questionType: string | null;
  correct: boolean;
  selectedAnswer: string | null;
  correctAnswer: string | null;
  word: string | null;
  evidenceOrigin: string;
  resolver: string | null;
  itemId: string | null;
  technical: Record<string, unknown>;
}

export interface PlacementPrior {
  source: "Global BKT prior" | "Placement Chapter Prior";
  pL0: number;
  chapter?: number;
  placementResult?: string;
  rawScore?: number | null;
  shrinkageWeight?: number | null;
  globalPrior?: number;
}

export interface LiveTrace {
  word: VerificationWord;
  evidence: EvidenceItem[];
  evidenceCount: number;
  provenance: string;
  syntheticTestData: boolean;
  coldStart: PlacementPrior;
  expectedTrace: BktTraceStep[];
  actualTrace: BktTraceStep[];
  comparison: {
    observationCount: { expected: number; actual: number };
    pLearned: { expected: number; actual: number };
    status: { expected: string; actual: string };
  };
  verification: VerificationResult;
  reviewStatus: string;
}

export interface BktVerificationTraceResponse {
  student: { studentId: string; name: string; isTestAccount: boolean };
  words: VerificationWord[];
  presets: Array<{ id: string; label: string; wordId: string }>;
  selectedWordId: string | null;
  model: BktVerificationModel;
  trace: LiveTrace | null;
}

async function parseError(response: Response, fallback: string): Promise<Error> {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  return new Error(typeof body?.detail === "string" ? body.detail : `${fallback} (${response.status}).`);
}

export async function getBktVerificationBootstrap(modelVersion?: string): Promise<BktVerificationBootstrap> {
  const query = modelVersion ? `?${new URLSearchParams({ model_version: modelVersion })}` : "";
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/bkt-verification${query}`);
  if (!response.ok) throw await parseError(response, "Could not load BKT verification metadata");
  return response.json() as Promise<BktVerificationBootstrap>;
}

export async function getBktVerificationTrace(studentId: string, wordId?: string, modelVersion?: string): Promise<BktVerificationTraceResponse> {
  const params = new URLSearchParams({ student_id: studentId });
  if (wordId) params.set("word_id", wordId);
  if (modelVersion) params.set("model_version", modelVersion);
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/bkt-verification/trace?${params.toString()}`);
  if (!response.ok) throw await parseError(response, "Could not load the BKT trace");
  return response.json() as Promise<BktVerificationTraceResponse>;
}
