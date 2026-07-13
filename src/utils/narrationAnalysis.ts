const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

export interface ContentAccuracy {
  score: number;
  feedback: string;
  matched_details: string[];
  missed_details: string[];
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
}

export interface AnalysisResult {
  transcription?: string;
  tone_accuracy: number;
  fluency_score: number;
  word_prosody?: WordProsody[];
  ai_feedback?: LanguageFeedback;
}

/** Real, measured prosody score — averaged per-character tone_accuracy —
 * rather than the AI's generic pronunciation_note.score, which isn't
 * grounded in the actual measured pitch data. Shared by ImageNarrationPage
 * and ListenRetellPage, which both submit to the same /api/analyze shape. */
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
