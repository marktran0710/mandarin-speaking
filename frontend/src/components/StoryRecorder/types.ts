import type { AssistiveFeedbackSyllable } from "../../utils/assistiveFeedback";
import type { AnalysisVersion } from "../../utils/analysisVersion";
import type { BackendFeedbackQuality } from "../../utils/voiceFeedbackReliability";
import { averageWordProsodyAccuracy } from "../../utils/storyRecorderFeedback";
import type { SceneSubmission, StoredAudioRecord } from "../../services/database";
import type { SpeechModel, Topic } from "./storyContent";

export interface PauseAnalysis {
  duration: number;
  utterance_count: number;
  pause_count: number;
  total_pause_duration: number;
  longest_pause: number;
  speech_ratio: number;
  // Judged pause placement + articulation rate — see backend
  // caf_metrics.classify_pauses and speech_rate_verdict.
  choppy_pause_count?: number;
  natural_pause_count?: number;
  articulation_rate?: number;
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
  /** Transcript from the independent ASR/content check, when requested. */
  recognized_text?: string | null;
  /** Whether the detected transcript matched the scene's target text. */
  content_match?: boolean | null;
  content_diff?: ContentDiffSegment[];
  /** Sentence roll-up of the four-state tone diagnosis. */
  tone_diagnostics?: {
    counts: { correct: number; uncertain: number; incorrect: number; invalid_audio: number };
    diagnostic_status: DiagnosticStatus;
    recommended_action: "record_again" | "targeted_practice" | "none";
    recording_reason_codes?: string[];
    controls_progression?: boolean;
  };
  pronunciation_mastery?: {
    passed?: boolean;
    status?: "passed" | "needs_practice" | "not_judged";
    passed_syllables?: number;
    total_syllables?: number;
    failed_words?: string[];
    missing_target_units?: string[];
    practice_parts?: string[];
    message?: string;
  };
  analysis_version?: AnalysisVersion;
  analysis_schema_version?: string;
  model_version?: string;
  comparison_group_id?: string;
  experimental?: boolean;
  progression_eligible?: boolean;
  neutral_tone_status?: string;
  character_prosody?: Array<{
    char_index: number;
    char: string;
    pinyin: string;
    expected_tone: number | null;
    detected_tone: number | null;
    tone_status: string;
    tone_probabilities: Record<string, number | null>;
    tone_confidence: number;
    start_time: number;
    end_time: number;
    alignment_confidence: number;
    phones: Array<{ phone: string; start_time: number; end_time: number }>;
  }>;
  /** Additive ACCEPT/UNCERTAIN/NEEDS_PRACTICE layer; absent/null unless the
   * backend has assistive feedback enabled for this request (globally off
   * by default, or pilot-scoped via `study_phase`). See
   * `src/utils/assistiveFeedback.ts`. */
  assistive_feedback?: AssistiveFeedbackSyllable[] | null;
  /** Additive join key for future quiz-item → speaking analysis links. */
  learning_context?: {
    baseStoryId: string;
    difficultyLevel: "easy" | "medium" | "hard";
    sceneIndex: number;
    promptId: string;
  };
}

export interface WordProsody {
  token: string;
  index: number;
  start_time: number;
  end_time: number;
  pitch_contour: Array<[number, number]>;
  reference_contour?: Array<[number, number]>;
  /** Whether this word was scored against a real teacher/model-voice curve. */
  reference_source?: "real_voice" | "synthetic";
  // The exact normalized [0,1] curves the backend's shape score compared
  // (user vs idealized target) — drawn by MiniContourChart so the chart
  // can never disagree with the score. Empty/absent when the segment was
  // too short to score (chart falls back to the raw-Hz pair above).
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
  // Pure shape-similarity score (the one the chart visualizes), as opposed
  // to tone_accuracy's direction-weighted blend used for aggregation.
  shape_accuracy?: number;
  /** Word-level pitch-shape similarity, separated from direction so
   * consumers can see disagreement. Present on any judged word after the
   * tone-verdict refactor. */
  shape_score?: number | null;
  /** Word-level directional-fit score (start/end regional means). */
  direction_score?: number | null;
  /** 70/30 shape-weighted composite. Kept only for progress-history
   * display; not a verdict input. */
  display_score?: number;
  /** Canonical word verdict; equal to `diagnostic_status`, mirrored under a
   * clearer name for the refactor's payload. */
  verdict?: DiagnosticStatus;
  /** Reason code for the verdict (strong_shape_supported,
   * strong_shape_direction_overridden, weak_shape, strong_negative_evidence,
   * insufficient_pitch_frames, invalid_audio, no_contour_measurement). */
  reason?: string;
  // Per-syllable directional scores + verdicts. `passed` at both syllable
  // and word level now follows the diagnostic verdict (verdict==CORRECT),
  // not a raw score threshold — placeholder syllables (short segments,
  // neutral tone) can no longer produce passed=True.
  syllables?: WordProsodySyllable[];
  passed?: boolean | null;
  /** Word roll-up of the diagnostic layer — same value as `verdict`. */
  diagnostic_status?: DiagnosticStatus;
  /** False when the analyzer could not extract enough pitch evidence. */
  judged?: boolean;
}

/** How the mouth was shaped, read relative to this same recording's own
 * average — never against a fixed table, so it means the same thing for an
 * adult and a child. */
export interface VowelZone {
  height: "high" | "mid" | "low";
  backness: "front" | "central" | "back";
}

export type VowelStatus =
  /** No audio reached the analyzer (word drills, the no-Praat fallback). */
  | "not_measured"
  /** Nothing to point at: the apical -i of 吃/知/是, or rhotic 兒. */
  | "not_applicable"
  /** Audio was there, but the nucleus was too short or unvoiced to measure. */
  | "no_formants"
  /** Measured — but the final glides (好, 在, 飯), so it is a nucleus reading. */
  | "nucleus_only"
  /** Measured on a steady single vowel. */
  | "measured";

/** Four-state tone diagnosis. Replaces ✓/✗ for *display and research*; it
 * does NOT drive lesson progression — that still runs on `passed` below. */
export type DiagnosticStatus =
  | "CORRECT"
  | "UNCERTAIN"
  | "INCORRECT"
  | "INVALID_AUDIO";

/** How the score attached to a syllable was produced. Two of these are
 * placeholder constants from the legacy scorer, not measurements. */
export type ScoreProvenance =
  | "measured"
  /** Legacy 65 placeholder: the segment held too few pitch frames to judge. */
  | "constant_short_segment"
  /** Legacy 75 placeholder: neutral tone has no contour target, so nothing
   * about the learner's production was measured at all. Distinct from an
   * uncertain measurement, and worded differently in the UI. */
  | "neutral_not_measured"
  /** Shape score compared against the teacher/model reference curve. */
  | "reference_shape"
  | "not_scored";

export interface WordProsodySyllable {
  char: string;
  /** Expected tone from the dictionary + legacy per-token sandhi. This is a
   * target, never a detected class — nothing in the pipeline predicts tones. */
  tone: number;
  /** Legacy heuristic contour-match score, 0-100. Not a probability. */
  score: number;
  /** Null when the analyzer did not have enough evidence to judge it. */
  passed: boolean | null;

  // ── Diagnostic layer (parallel to the legacy verdict above) ──────────
  diagnostic_status?: DiagnosticStatus;
  diagnostic_reason?: string;
  /** Contour match against the contextually accepted tone. Null when nothing
   * could be measured. Never a confidence or probability. */
  contour_match_score?: number | null;
  matched_surface_tone?: number | null;
  score_provenance?: ScoreProvenance;
  underlying_tone?: number;
  accepted_surface_tones?: number[];
  tone_realization?: string;
  context_rule?: string | null;
  /** The legacy verdict, kept explicitly labelled so the two never blur. */
  legacy?: { passed: boolean | null; score: number | null; threshold: number };
  /** The vowel this character should carry, from its pinyin final. */
  expected_vowel?: string | null;
  expected_zone?: VowelZone | null;
  final?: string | null;
  /** Measured formants for this syllable's own audio, in Hz. */
  f1?: number;
  f2?: number;
  measured_zone?: VowelZone | null;
  /** There is deliberately no vowel pass/fail here. A short utterance cannot
   * support one honestly — see backend/vowel_analysis.py. Tone is the only
   * thing scored, and the only thing that gates progression. */
  vowel_status?: VowelStatus;
}

interface LanguageFeedback {
  provider: string;
  vocabulary_coverage: {
    score: number;
    used: string[];
    missing: string[];
    feedback: string;
    // `false` when the backend could not verify sentence content and
    // therefore did NOT do a real word-presence check — used/missing in
    // that case are placeholders (all target words dumped into
    // `missing`). Consumers must fall back to their own transcript check.
    judged?: boolean;
  };
  coherence: {
    score: number;
    feedback: string;
    corrections: string[];
  };
  pronunciation_note: {
    score: number;
    feedback: string;
    // Same text as `feedback`, split into one entry per aspect (tone,
    // rhythm_pace, pausing, vowel_quality, word_stress) — see backend
    // ai_feedback.fallback_language_feedback for how these are built.
    details?: { key: string; text: string }[];
  };
  content_accuracy?: {
    score: number;
    feedback: string;
    matched_details: string[];
    missed_details: string[];
    accepted: boolean;
    judged: boolean;
  };
  corrective_feedback?: {
    errors: string[];
    hint: string;
    reveal_answer: boolean;
    correct_version: string;
  };
  improved_version: string;
  practice_prompt: string;
  // legacy fields kept for backward compat
  fluency?: { score: number; feedback: string };
  grammar?: { score: number; feedback: string; corrections: string[] };
  vocabulary?: { score: number; feedback: string; suggestions: string[] };
}
export interface TranscriptionItem {
  text: string;
  timestamp: string;
  model: SpeechModel;
}

/** Returns only the image frames a student is expected to record. A first
 * teacher-model frame is deliberately excluded from completion and submit
 * gates, while remaining available as a reference in the session sidebar. */
export function practiceSceneIndicesFor(
  topic: Pick<Topic, "images" | "firstFrameIsExample">,
): number[] {
  return topic.images
    .map((_, index) => index)
    .filter((index) => !(topic.firstFrameIsExample && index === 0));
}

/** Shape a freshly recorded scene attempt is handed up in via
 * `onAddRecord`, before it's persisted (see StoredAudioRecord in
 * services/database.ts for the shape after upload). Exported so callers
 * like CreateStoryPage can type their own onAddRecord prop instead of
 * widening it to `any`. */
export interface NewAudioRecord {
  id: string;
  audioBlob: Blob;
  timestamp: string;
  duration: number;
  transcription: string;
  model: SpeechModel;
  topicId: string;
  imageUrl: string;
  imageIndex: number;
  praatMetrics: PraatMetrics;
  analysisVersion?: AnalysisVersion;
  analysisSchemaVersion?: string;
  modelVersion?: string;
  comparisonGroupId?: string;
  sessionId?: string;
  attemptId?: string;
  attemptNumber?: number;
  attemptType?: "WHOLE_SENTENCE_INITIAL" | "FOCUSED_RETRY" | "WHOLE_SENTENCE_FINAL";
}

/** Builds the legacy restore fallback for progress rows written before
 * `latestResult` existed. */
export function sceneSubmissionFromAudioRecord(
  record: StoredAudioRecord,
): SceneSubmission | null {
  if (record.imageIndex === undefined) return null;
  const metrics = record.praatMetrics as PraatMetrics | undefined;
  const coverage = metrics?.ai_feedback?.vocabulary_coverage;
  return {
    sceneIndex: record.imageIndex,
    imageUrl: record.imageUrl ?? "",
    transcription: record.transcription ?? metrics?.transcription ?? "",
    vocabUsed: coverage?.used ?? [],
    vocabMissing: coverage?.missing ?? [],
    vocabScore: coverage?.score ?? 0,
    toneAccuracy: Math.round(metrics?.tone_accuracy ?? 0),
    pronScore: averageWordProsodyAccuracy(metrics?.word_prosody) ?? 0,
    fluencyScore: Math.round(metrics?.fluency_score ?? 0),
    audioUrl: record.audioUrl,
    pauseCount: metrics?.pause_analysis?.pause_count ?? 0,
    longestPause: metrics?.pause_analysis?.longest_pause ?? 0,
    utteranceCount: metrics?.pause_analysis?.utterance_count ?? 0,
    choppyPauseCount: metrics?.pause_analysis?.choppy_pause_count ?? 0,
    articulationRate: metrics?.pause_analysis?.articulation_rate ?? 0,
  };
}
export type ContentDiffSegment = {
  type: "match" | "replace" | "missing" | "extra";
  target: string;
  heard: string;
};
