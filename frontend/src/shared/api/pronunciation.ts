import { BACKEND_URL, fetchWithRetry } from "./client";

/** Mirrors backend services/pronunciation/presenter.py. The student response
 * has no `debug`; teachers and admins always get it. */
export type PronunciationBasis = "measured" | "inferred" | "unavailable";

export interface PronunciationDimension {
  key: "tone" | "segmental" | "fluency" | "intelligibility";
  basis: PronunciationBasis;
  points: number | null;
  out_of: number | null;
  note: string;
}

export interface PronunciationWord {
  word: string;
  pinyin: string;
  expected_tone: number;
  tone_similarity: number | null;
  reference_shape: string;
  student_shape: string;
  duration_ratio: number | null;
  evidence: "strong" | "moderate" | "weak";
  flags: string[];
}

export interface PronunciationFeedback {
  summary: string;
  focus_words: Array<{ word: string; feedback: string }>;
  practice_tip: string;
  source?: "llm" | "local";
  model?: string | null;
  fallback_reason?: string | null;
  adjustments?: string[];
  dimension_feedback?: Partial<Record<"pronunciation" | "fluency" | "prosody", string>>;
}

export interface PronunciationRubricDimension {
  key: "pronunciation" | "accuracy" | "fluency" | "prosody";
  score: number | null;
  out_of: 5;
  source: "praat" | "wav2vec2_plus_praat" | "unavailable" | "ai";
  rubric_level: number | null;
  rubric_description: string | null;
  reason: string;
  evidence_quality?: "full" | "degraded";
  evidence_reasons?: string[];
  feedback?: string;
  measurements: Record<string, unknown>;
  criteria: Array<{
    feature: string;
    value: number | null;
    level: number | null;
    thresholds_levels_5_to_2: number[];
    comparison: string;
    evidence?: "measured" | "degraded";
  }>;
  ai_result?: Record<string, unknown> | null;
  pronunciation_errors?: Array<Record<string, unknown>>;
  tone_errors?: Array<Record<string, unknown>>;
}

export interface PronunciationSyllableFeatures {
  expected: { hanzi: string; pinyin: string; expected_tone: number };
  start_ms: number;
  end_ms: number;
  direction: string;
  f0_points: Array<[number, number]>;
}

export interface PronunciationFeatureSet {
  duration_ms: number;
  syllables: PronunciationSyllableFeatures[];
}

export interface PronunciationDebug {
  provenance: Record<string, unknown>;
  policy: Record<string, unknown>;
  issues: Array<Record<string, unknown>>;
  comparison: Record<string, unknown> | null;
  reference_features: PronunciationFeatureSet;
  student_features: PronunciationFeatureSet | null;
  recording_quality: Record<string, unknown> | null;
  pronunciation_evidence?: Record<string, unknown>;
}

export interface PronunciationEvaluation {
  target_text?: string;
  status: "scored" | "unscorable";
  reason: string | null;
  pronunciation_score?: number | null;
  fluency_score?: number | null;
  prosody_score?: number | null;
  /** Legacy saved results only; new evaluations never calculate a total. */
  score?: {
    total: number | null;
    renormalized: boolean;
    dimensions: PronunciationDimension[];
  };
  dimensions?: Record<"pronunciation" | "fluency" | "prosody", PronunciationRubricDimension>;
  pronunciation_errors?: Array<Record<string, unknown>>;
  tone_errors?: Array<Record<string, unknown>>;
  scoring_policy?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  metrics: Partial<Record<"tone_similarity" | "rhythm_similarity" | "duration_similarity" | "pause_similarity", number | null>>;
  words: PronunciationWord[];
  feedback: PronunciationFeedback;
  model: {
    scoring_version: string;
    acoustic_pipeline_version: string;
    feedback_model: string | null;
    feedback_source: "llm" | "local";
  };
  reference: { key: string; cache_hit: boolean; audio_url?: string };
  debug?: PronunciationDebug;
}

export class PronunciationRequestError extends Error {
  constructor(readonly code: string, message: string, readonly status: number) {
    super(message);
    this.name = "PronunciationRequestError";
  }
}

// The backend analysis deadline is 120 seconds; leave enough time for its
// structured timeout response to reach the browser instead of aborting first.
const EVALUATION_TIMEOUT_MS = 125_000;

export interface PronunciationRequest {
  storyId: string;
  sceneIndex: number;
  conversationId?: string;
  turnId?: string;
  turnIndex?: number;
}

export async function evaluatePronunciation(
  audio: Blob,
  request: PronunciationRequest,
): Promise<PronunciationEvaluation> {
  const form = new FormData();
  form.append("file", audio, "recording.wav");
  form.append("story_id", request.storyId);
  form.append("scene_index", String(request.sceneIndex));
  if (request.conversationId) form.append("conversation_id", request.conversationId);
  if (request.turnId) form.append("turn_id", request.turnId);
  if (request.turnIndex !== undefined) form.append("turn_index", String(request.turnIndex));

  // One attempt only: a repeated upload would re-run Praat and the language model.
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/pronunciation/evaluate`,
    { method: "POST", body: form },
    1,
    EVALUATION_TIMEOUT_MS,
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail;
    const code = typeof detail === "object" && detail?.code ? String(detail.code) : "request_failed";
    const message = typeof detail === "string" ? detail : detail?.message ?? "Could not evaluate this recording.";
    throw new PronunciationRequestError(code, message, response.status);
  }
  return response.json() as Promise<PronunciationEvaluation>;
}
