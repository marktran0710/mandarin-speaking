const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV && typeof window !== "undefined" ? window.location.origin : "");

export interface ContentAccuracy {
  score: number;
  feedback: string;
  matched_details: string[];
  missed_details: string[];
  judged?: boolean;
  accepted?: boolean;
}

export interface LanguageFeedback {
  provider: string;
  vocabulary_coverage?: {
    score: number;
    used: string[];
    missing: string[];
    feedback: string;
  };
  coherence?: {
    score: number;
    feedback: string;
    corrections: string[];
  };
  pronunciation_note?: {
    score: number;
    feedback: string;
  };
  content_accuracy?: ContentAccuracy;
  improved_version?: string;
  practice_prompt?: string;
}

export interface WordProsody {
  token: string;
  tone_accuracy?: number;
  feedback?: string;
  judged?: boolean;
  pitch_contour?: Array<[number, number]>;
}

export interface AnalysisResult {
  transcription?: string;
  transcription_model?: string;
  pitch_contour?: Array<[number, number]>;
  tone_accuracy: number;
  fluency_score: number;
  speech_rate?: number;
  word_prosody?: WordProsody[];
  ai_feedback?: LanguageFeedback;
  recognized_text?: string | null;
  content_match?: boolean | null;
  feedback_quality?: {
    status?: string;
    confidence?: number;
    can_score_pronunciation?: boolean;
    can_score_content?: boolean;
    reason_codes?: string[];
    reasons?: string[];
    student_message?: string;
  };
  pronunciation_mastery?: {
    passed?: boolean;
    status?: "passed" | "needs_practice" | "not_judged";
    passed_syllables?: number;
    total_syllables?: number;
    message?: string;
  };
}

export interface AnalysisVisibility {
  hasTranscript: boolean;
  canScorePronunciation: boolean;
  canScoreContent: boolean;
  contentIsVerified: boolean;
  showPronunciation: boolean;
  showContentScore: boolean;
  showContentDetails: boolean;
  showVocabulary: boolean;
  showCoherence: boolean;
  showPracticePrompt: boolean;
  needsRetry: boolean;
}

export function isUsableScore(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * Keep student-facing result visibility conservative. A numeric field can be
 * present in the API response even when the backend explicitly says that the
 * recording was not safe to score.
 */
export function getAnalysisVisibility(
  result: AnalysisResult | null,
): AnalysisVisibility {
  const hasTranscript = Boolean(result?.transcription?.trim());
  const quality = result?.feedback_quality;
  const canScorePronunciation =
    hasTranscript && quality?.can_score_pronunciation !== false;
  const canScoreContent = hasTranscript && quality?.can_score_content !== false;
  const contentAccuracy = result?.ai_feedback?.content_accuracy;
  const contentIsVerified =
    (result?.content_match !== null && result?.content_match !== undefined) ||
    contentAccuracy?.judged === true;
  const retryStatus = quality?.status === "retry";
  const needsRetry =
    retryStatus || !canScorePronunciation;

  return {
    hasTranscript,
    canScorePronunciation,
    canScoreContent,
    contentIsVerified,
    showPronunciation: canScorePronunciation && !retryStatus,
    showContentScore: Boolean(contentAccuracy) && contentIsVerified && canScoreContent,
    showContentDetails: Boolean(contentAccuracy) && contentIsVerified && canScoreContent,
    showVocabulary:
      Boolean(result?.ai_feedback?.vocabulary_coverage) &&
      canScoreContent &&
      contentAccuracy?.judged !== false,
    showCoherence: Boolean(result?.ai_feedback?.coherence) && canScoreContent,
    showPracticePrompt:
      Boolean(result?.ai_feedback?.practice_prompt) &&
      hasTranscript &&
      canScorePronunciation &&
      !retryStatus,
    needsRetry,
  };
}

/** Real, measured prosody score — averaged per-character tone_accuracy —
 * rather than the AI's generic pronunciation_note.score, which isn't
 * grounded in the actual measured pitch data for narrated-speaking feedback. */
export function averageWordProsodyAccuracy(wordProsody?: WordProsody[]): number | null {
  const accuracies = (wordProsody ?? [])
    .map((item) => item.tone_accuracy)
    .filter((value): value is number => typeof value === "number");
  if (accuracies.length === 0) return null;
  return Math.round(
    accuracies.reduce((sum, value) => sum + value, 0) / accuracies.length,
  );
}

/** Per-character feedback for the characters that most need work, grounded in
 * the actual measured pitch data (word_prosody), instead of the AI's generic
 * pronunciation_note text. */
export function prosodyFeedbackLines(wordProsody?: WordProsody[]): Array<{ token: string; feedback: string }> {
  return (wordProsody ?? [])
    .filter((item) => item.feedback)
    .sort((a, b) => (a.tone_accuracy ?? 100) - (b.tone_accuracy ?? 100))
    .slice(0, 3)
    .map((item) => ({ token: item.token, feedback: item.feedback! }));
}

export async function readErrorResponse(response: Response): Promise<{ detail?: string }> {
  try {
    return await response.json();
  } catch {
    return { detail: `${response.status} ${response.statusText}` };
  }
}

export function getBackendUrl(): string {
  if (BACKEND_URL) return BACKEND_URL;
  throw new Error("Set VITE_BACKEND_URL to reach the FastAPI backend.");
}
