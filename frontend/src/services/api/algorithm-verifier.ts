import { BACKEND_URL, fetchWithRetry } from "@shared/api/client";

export type AlgorithmResult = "PASS" | "FAIL" | "NOT RUN" | "BLOCKED" | "MODEL CONTRACT CHANGED";

export interface AlgorithmVerifierBootstrap {
  model: Record<string, unknown>;
  golden: { summary: { passed: number; total: number } };
  contractStatus: string;
  sm2: Record<string, unknown>;
  baselineSuites: { bkt: AlgorithmResult; sm2: AlgorithmResult };
  integration: {
    enabled: boolean;
    studentId: string;
    runId: string;
    fixture: IntegrationFixture | null;
    fixtureError: string | null;
  };
}

export interface IntegrationFixtureWord {
  wordId: string;
  word: string;
  focus: boolean;
  items: Array<{ questionId: string; questionType: string; round: number; targetWord: string; answerFormat: string }>;
}

export interface IntegrationFixture {
  storyId: string;
  title: string | null;
  lesson: number;
  section: number;
  revision: string;
  words: IntegrationFixtureWord[];
}

export interface IntegrationState {
  enabled: boolean;
  studentId: string;
  runId: string;
  fixture: IntegrationFixture;
  status: string;
  report: IntegrationReport | null;
  simulatedNow: string | null;
  stepPosition: number;
}

export interface IntegrationReport {
  runId: string;
  studentId: string;
  fixture: IntegrationFixture;
  baseTime: string;
  daySeconds: number;
  before: IntegrationSnapshot;
  afterDiagnostic: IntegrationSnapshot;
  steps: Array<{ id: string; label: string; state: IntegrationSnapshot }>;
  completed: boolean;
  traceability: Record<string, unknown>;
}

export interface IntegrationSnapshot {
  timestamp: string;
  diagnostic?: Record<string, unknown>;
  words: Array<{
    wordId: string;
    word: string;
    focus: boolean;
    pLearned: number;
    observationCount: number;
    bktStatus: string | null;
    masteryStatus: string | null;
    practice: Record<string, unknown> | null;
    schedule: { reps: number; intervalDays: number; ease: number; dueOn: string | null; lastReviewedOn: string | null } | null;
    queueReason: string | null;
  }>;
  queue: Array<{ wordId: string; word: string; reviewReason: string }>;
}

async function parseError(response: Response, fallback: string): Promise<Error> {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  return new Error(typeof body?.detail === "string" ? body.detail : `${fallback} (${response.status}).`);
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetchWithRetry(`${BACKEND_URL}${path}`, init);
  if (!response.ok) throw await parseError(response, "Algorithm verifier request failed");
  return response.json() as Promise<T>;
}

export function getAlgorithmVerifierBootstrap(): Promise<AlgorithmVerifierBootstrap> {
  return json<AlgorithmVerifierBootstrap>("/api/admin/algorithm-verifier");
}

export function runBktVerification(input: Record<string, unknown>): Promise<Record<string, unknown>> {
  return json<Record<string, unknown>>("/api/admin/algorithm-verifier/bkt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
}

export function runSm2Verification(input: Record<string, unknown>): Promise<Record<string, unknown>> {
  return json<Record<string, unknown>>("/api/admin/algorithm-verifier/sm2", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
}

export function getIntegrationState(): Promise<IntegrationState> {
  return json<IntegrationState>("/api/admin/algorithm-verifier/integration");
}

export function getIntegrationRequests(): Promise<Record<string, unknown>> {
  return json<Record<string, unknown>>("/api/admin/algorithm-verifier/integration/requests");
}

export function resetIntegration(): Promise<{ status: string; studentId: string; fixture: IntegrationFixture }> {
  return json("/api/admin/algorithm-verifier/integration/reset", { method: "POST" });
}

export function runIntegration(): Promise<IntegrationReport> {
  return json<IntegrationReport>("/api/admin/algorithm-verifier/integration/run", { method: "POST" });
}
