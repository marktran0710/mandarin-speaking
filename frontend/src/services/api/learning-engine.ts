import { BACKEND_URL, fetchWithRetry } from "@shared/api/client";

export interface LearningEngineParameter {
  value: number | string;
  provenance: string;
}

export interface LearningEngineThreshold {
  value: number;
  purpose: string;
  controlsProgression: boolean;
  provenance: string;
}

export interface LearningEngineReference {
  citation: string;
  doi?: string;
  note?: string;
}

export interface LearningEngineBkt {
  name: string;
  version: string;
  provenance: string;
  purpose: string;
  parameters: Record<string, LearningEngineParameter>;
  parameterStatus: string;
  calibrationStatus: string;
  pipeline: string[];
  reference: LearningEngineReference;
}

export interface LearningEngineRetention {
  name: string;
  version: string;
  provenance: string;
  purpose: string;
  parameters: Record<string, LearningEngineParameter>;
  parameterStatus: string;
  calibrationStatus: string;
  easeFormula: string;
  intervalSequence: string;
  conceptualSeparation: string;
  reference: LearningEngineReference;
}

export interface LearningEngineProvider {
  provider: string;
  role: string;
  configured: boolean;
}

export interface LearningEngineVoice {
  pipeline: string[];
  acousticEngine: { technology: string; purpose: string; provenance: string; reference: LearningEngineReference };
  toneScoring: { provenance: string; note: string };
  qualityGate: { reasons: string[]; principle: string };
  thresholds: Record<string, LearningEngineThreshold>;
  asrProviders: LearningEngineProvider[];
  feedbackProviders: { defaultProvider: string; providers: LearningEngineProvider[]; fallbackBehavior: string };
  calibrationStatus: string;
}

export interface LearningEngineMetadata {
  bkt: LearningEngineBkt;
  retention: LearningEngineRetention;
  voice: LearningEngineVoice;
}

export async function getLearningEngineMetadata(): Promise<LearningEngineMetadata> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/learning-engine`, {
    method: "GET",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Could not load Learning Engine metadata.");
  }
  return response.json() as Promise<LearningEngineMetadata>;
}
