export type SpeechModel = "webspeech" | "ctwhisper" | "groq" | "vibevoice" | "openai";

export type AssistiveFeedbackSyllable = {
  syllable_index: number;
  character: string;
  expected_underlying_tone: number;
  accepted_surface_tones: number[];
  context_rule: string | null;
  realization: string;
  assistive_state: "ACCEPT" | "UNCERTAIN" | "NEEDS_PRACTICE";
  assistive_state_label: "NO_ISSUE_DETECTED" | "NO_AUTOMATIC_JUDGMENT" | "CHECK_THIS_TONE";
  assistive_message: string;
  e2_diagnostic_category: string;
  explanation: { e2_provenance: string; e2_matched_tone: number; boundary_before: boolean; boundary_after: boolean };
};

export interface BackendFeedbackQuality {
  status?: string;
  confidence?: number;
  can_score_pronunciation?: boolean;
  can_score_content?: boolean;
  reason_codes?: string[];
  reasons?: string[];
  metrics?: Record<string, number | string | boolean | null>;
}

export interface PauseAnalysis {
  duration: number;
  utterance_count: number;
  pause_count: number;
  total_pause_duration: number;
  longest_pause: number;
  speech_ratio: number;
  choppy_pause_count?: number;
  natural_pause_count?: number;
  articulation_rate?: number;
}

export type VowelZone = { height: "high" | "mid" | "low"; backness: "front" | "central" | "back" };
export type VowelStatus = "not_measured" | "not_applicable" | "no_formants" | "nucleus_only" | "measured";
export type DiagnosticStatus = "CORRECT" | "UNCERTAIN" | "INCORRECT" | "INVALID_AUDIO";
export type ScoreProvenance = "measured" | "constant_short_segment" | "neutral_not_measured" | "reference_shape" | "not_scored";

export interface WordProsodySyllable {
  char: string;
  tone: number;
  score: number;
  passed: boolean | null;
  diagnostic_status?: DiagnosticStatus;
  diagnostic_reason?: string;
  contour_match_score?: number | null;
  matched_surface_tone?: number | null;
  score_provenance?: ScoreProvenance;
  underlying_tone?: number;
  accepted_surface_tones?: number[];
  tone_realization?: string;
  context_rule?: string | null;
  legacy?: { passed: boolean | null; score: number | null; threshold: number };
  expected_vowel?: string | null;
  expected_zone?: VowelZone | null;
  final?: string | null;
  f1?: number;
  f2?: number;
  measured_zone?: VowelZone | null;
  vowel_status?: VowelStatus;
}

export interface WordProsody {
  token: string;
  index: number;
  start_time: number;
  end_time: number;
  pitch_contour: Array<[number, number]>;
  reference_contour?: Array<[number, number]>;
  reference_source?: "real_voice" | "synthetic";
  user_curve?: number[];
  target_curve?: number[];
  mean_pitch: number;
  pitch_range: number;
  start_pitch: number;
  end_pitch: number;
  contour_shape: string;
  feedback: string;
  expected_tones?: number[];
  tone_accuracy?: number;
  shape_accuracy?: number;
  shape_score?: number | null;
  direction_score?: number | null;
  display_score?: number;
  verdict?: DiagnosticStatus;
  reason?: string;
  syllables?: WordProsodySyllable[];
  passed?: boolean | null;
  diagnostic_status?: DiagnosticStatus;
  judged?: boolean;
}

export interface ContentDiffSegment { type: "match" | "replace" | "missing" | "extra"; target: string; heard: string; }

interface LanguageFeedback {
  provider: string;
  vocabulary_coverage: { score: number; used: string[]; missing: string[]; feedback: string; judged?: boolean };
  coherence: { score: number; feedback: string; corrections: string[] };
  pronunciation_note: { score: number; feedback: string; details?: { key: string; text: string }[] };
  content_accuracy?: { score: number; feedback: string; matched_details: string[]; missed_details: string[]; accepted: boolean; judged: boolean };
  corrective_feedback?: { errors: string[]; hint: string; reveal_answer: boolean; correct_version: string };
  improved_version: string;
  practice_prompt: string;
  fluency?: { score: number; feedback: string };
  grammar?: { score: number; feedback: string; corrections: string[] };
  vocabulary?: { score: number; feedback: string; suggestions: string[] };
}

export interface PraatMetrics {
  transcription?: string;
  transcription_model?: string;
  pitch_contour: Array<[number, number]>;
  word_prosody?: WordProsody[];
  detected_tone: number;
  tone_accuracy: number;
  formants: Record<string, number>;
  vowel_quality?: string;
  speech_rate: number;
  fluency_score: number;
  pitch_statistics: Record<string, number>;
  tone_direction?: string;
  pause_analysis?: PauseAnalysis;
  feedback: string;
  ai_feedback?: LanguageFeedback;
  feedback_quality?: BackendFeedbackQuality;
  recognized_text?: string | null;
  content_match?: boolean | null;
  content_diff?: ContentDiffSegment[];
  tone_diagnostics?: { counts: { correct: number; uncertain: number; incorrect: number; invalid_audio: number }; diagnostic_status: DiagnosticStatus; recommended_action: "record_again" | "targeted_practice" | "none"; recording_reason_codes?: string[]; controls_progression?: boolean };
  pronunciation_mastery?: { passed?: boolean; status?: "passed" | "needs_practice" | "not_judged"; passed_syllables?: number; total_syllables?: number; failed_words?: string[]; missing_target_units?: string[]; practice_parts?: string[]; message?: string };
  analysis_schema_version?: string;
  model_version?: string;
  progression_eligible?: boolean;
  neutral_tone_status?: string;
  assistive_feedback?: AssistiveFeedbackSyllable[] | null;
  learning_context?: { baseStoryId: string; difficultyLevel: "easy" | "medium" | "hard"; sceneIndex: number; promptId: string };
}
