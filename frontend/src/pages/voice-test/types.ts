import type { BackendFeedbackQuality } from "../../utils/voiceFeedbackReliability";

export interface WordProsody {
  token: string;
  index: number;
  start_time?: number;
  end_time?: number;
  pitch_contour?: Array<[number, number]>;
  reference_contour?: Array<[number, number]>;
  mean_pitch: number;
  pitch_range: number;
  start_pitch?: number;
  end_pitch?: number;
  contour_shape: string;
  feedback: string;
  tone_accuracy?: number;
  judged?: boolean;
}

export interface VoiceMetrics {
  description?: string;
  transcription?: string;
  transcription_model?: string;
  pitch_contour: Array<[number, number]>;
  word_prosody?: WordProsody[];
  detected_tone: number;
  tone_accuracy: number;
  speech_rate: number;
  fluency_score: number;
  feedback: string;
  feedback_quality?: BackendFeedbackQuality;
  ai_feedback?: {
    provider: string;
    fluency: { score: number; feedback: string };
    grammar: { score: number; feedback: string; corrections: string[] };
    vocabulary: { score: number; feedback: string; suggestions: string[] };
    improved_version: string;
    practice_prompt: string;
  };
}
