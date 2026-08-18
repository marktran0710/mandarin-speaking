import {
  type ChangeEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
  useCallback,
} from "react";
import {
  canUseDatabase,
  createStorySubmission,
  createVocabQuizAttempt,
  listAudioRecords,
  listSpeakingProgress,
  listVocabQuizAttempts,
  saveSpeakingProgress,
  updateVocabularyCloze,
  updateVocabularyDistractors,
  updateVocabularySynonym,
  type HelpRequest,
  type SceneSubmission,
  type StoredAudioRecord,
  type StoredSpeakingProgress,
  type StoryFeedback,
  type VocabularyClozeUpdate,
  type VocabularyDistractorUpdate,
  type VocabularySynonymUpdate,
} from "../services/database";
import ScenePracticeWord from "./ScenePracticeWord";
import StoryVocabQuiz, { type VocabQuizSummary } from "./StoryVocabQuiz";
import { topicQuizEntries } from "../utils/topicQuiz";
import { type JourneyStop, type JourneyStopStatus } from "./JourneyPath";
import { toPinyin } from "../utils/pinyin";
import {
  getLastScenePhase,
  getStudentId,
  isAdminSession,
  saveLastScenePhase,
} from "../utils/studentSession";
import type { AssistiveFeedbackSyllable } from "../utils/assistiveFeedback";
import { resolvePilotContext } from "../utils/pilotSession";
import type { AnalysisVersion } from "../utils/analysisVersion";
import { markStoryLevelSubmitted } from "../utils/storyLevelProgress";
import type { CustomTeacherStory, StoryDifficultyLevel } from "../utils/teacherStories";
import { convertBlobToWav } from "../utils/audio";
import { createMeasurementEvent, recordMeasurementEvent } from "../utils/measurement";
import { buildPracticeAnalysisFormData } from "../utils/practiceAnalysis";
import {
  sceneReady,
  sceneContentGatePassed,
  averageWordProsodyAccuracy,
  hasAudioFileExtension,
  getBackendUrl,
  prosodyGatePassed,
  readErrorResponse,
  formatBackendError,
} from "../utils/storyRecorderFeedback";
import {
  loadCompletedVocabQuizzes,
  markVocabQuizCompleted,
} from "../utils/vocabQuizStorage";
import "./StoryRecorder.css";
import { BiLabel, BiText } from "./BiLabel";
import AppButton from "./AppButton";
import "./BiLabel.css";
import StoryOverviewSection from "./StoryOverviewSection";
import SortingChallenge from "./SortingChallenge";
import StorySummarySection, {
  type JourneyStopBase,
} from "./StorySummarySection";
import SpeakingFlowCard from "./SpeakingFlowCard";
import StorySessionSidebar, {
  type SidebarPhase,
  type SidebarSummaryStatus,
} from "./StorySessionSidebar";
import StudentHelpPanel from "./StudentHelpPanel";
import type { BackendFeedbackQuality } from "../utils/voiceFeedbackReliability";
import type { SelfEvalLevel } from "../utils/selfEvalComparison";

const MAX_RECORDING_SECONDS = 30;

// Mirrors the backend's MAX_VOCAB_DISTRACTORS_PER_WORD cap — checked
// client-side so a story where every word already has a full pool skips the
// AI call entirely instead of generating distractors the backend would just
// discard.
const MAX_VOCAB_DISTRACTORS_PER_WORD = 8;

/** Combines cached sentence-token and vocabulary pitch-shape curves into the
 * {word: curve} map /api/analyze expects as scene_reference_curves. Tokens
 * without a usable teacher/TTS curve are omitted, so the backend can keep its
 * synthetic idealized tone-shape fallback only where real evidence is absent.
 * Returns null when there's nothing to send (no reference curves cached at
 * all for this scene), so callers can skip the form field entirely. */
export function buildSceneReferenceCurves(
  topic: Pick<Topic, "vocabulary" | "vocabularyReferenceCurves" | "sentenceReferenceCurves">,
  sceneIndex: number,
): Record<string, number[]> | null {
  const byWord: Record<string, number[]> = {
    ...(topic.sentenceReferenceCurves?.[sceneIndex] || {}),
  };
  const words = topic.vocabulary[sceneIndex] || [];
  const curves = topic.vocabularyReferenceCurves?.[sceneIndex];
  if (curves && curves.length > 0) {
    words.forEach((word, index) => {
      const curve = curves[index];
      if (curve && curve.length > 0 && !byWord[word]) {
        byWord[word] = curve;
      }
    });
  }
  return Object.keys(byWord).length > 0 ? byWord : null;
}

export function vocabTooltip(
  pos?: string,
  translation?: string,
): string | undefined {
  if (pos && translation) return `(${pos}) ${translation}`;
  if (pos) return `(${pos})`;
  if (translation) return translation;
  return undefined;
}

export type SpeechModel = "webspeech" | "ctwhisper" | "groq" | "vibevoice" | "openai";

export interface AiProviderOption {
  id: string;
  label: string;
  available: boolean;
}

interface VocabGroup {
  name: string;
  words: string[];
}

export interface Topic {
  id: string;
  name: string;
  description?: string;
  skillFocus?: string;
  level?: string;
  images: string[];
  prompts?: string[];
  vocabulary: Record<number, string[]>;
  vocabularyGroups?: Record<number, VocabGroup[]>;
  // Handy, easy-to-learn-and-reuse phrases for this scene (replaces the old
  // single whole-story "grammar pattern" note) — same word/translation shape
  // as vocabulary, aligned by index.
  phrases?: Record<number, string[]>;
  phrasesTranslation?: Record<number, string[]>;
  vocabularyPinyin?: Record<number, string[]>;
  vocabularyPos?: Record<number, string[]>;
  vocabularyTranslation?: Record<number, string[]>;
  vocabularyDistractors?: Record<number, string[][]>;
  vocabularyCloze?: Record<number, Array<{ sentence: string; distractors: string[] }[]>>;
  vocabularySynonym?: Record<number, Array<{ synonym: string; distractors: string[] }[]>>;
  suggestedAnswers?: Record<number, string>;
  listenAudioUrls?: Record<number, string>;
  listenAudioSources?: Record<number, "teacher" | "tts">;
  listenScripts?: Record<number, string>;
  // Model-voice reference audio for individual vocabulary words (aligned by
  // index with vocabulary[scene]) — a null entry means that word's clip
  // couldn't be sliced. vocabularyReferenceCurves is the matching cached
  // pitch-shape curve sent to /api/analyze as a real-voice scoring target
  // instead of the synthetic idealized tone-shape pattern.
  vocabularyAudioUrls?: Record<number, (string | null)[]>;
  vocabularyReferenceCurves?: Record<number, number[][]>;
  sentenceReferenceCurves?: Record<number, Record<string, number[]>>;
  linear?: boolean;
  lessonNumber?: number | null;
  lessonSubOrder?: number | null;
  narrativeMode?: "story" | "describe" | "listen_retell";
  firstFrameIsExample?: boolean;
  difficultyLevel?: StoryDifficultyLevel;
  sourceStory?: CustomTeacherStory;
}

export interface DistractorGrowthCandidate {
  frameIndex: number;
  wordIndex: number;
  word: string;
  translation: string;
  context?: string;
  existing: string[];
}

/** Pure planning step for growVocabularyDistractorPool: picks the words in a
 * story whose persisted distractor pool hasn't reached the cap yet, pairing
 * each with its existing pool (sent as the AI's "avoid" list). Returns an
 * empty array once every word is already at cap, the caller's signal to
 * skip the AI call entirely. */
export function planDistractorGrowth(
  topic: Pick<
    Topic,
    "images" | "vocabulary" | "vocabularyTranslation" | "vocabularyDistractors" | "suggestedAnswers"
  >,
): DistractorGrowthCandidate[] {
  const candidates: DistractorGrowthCandidate[] = [];
  topic.images.forEach((_, si) => {
    const sceneSuggestedAnswer = topic.suggestedAnswers?.[si];
    (topic.vocabulary[si] || []).forEach((word, i) => {
      const translation = topic.vocabularyTranslation?.[si]?.[i];
      if (!translation) return;
      const existing = topic.vocabularyDistractors?.[si]?.[i] ?? [];
      if (existing.length >= MAX_VOCAB_DISTRACTORS_PER_WORD) return;
      candidates.push({
        frameIndex: si,
        wordIndex: i,
        word,
        translation,
        context: sceneSuggestedAnswer,
        existing,
      });
    });
  });
  return candidates;
}

/** Pairs each growth candidate with the AI-generated distractors for its
 * word (matched by word text), dropping any candidate the AI returned
 * nothing for. */
export function buildDistractorPatchUpdates(
  candidates: DistractorGrowthCandidate[],
  results: Array<{ word: string; distractors: string[] }>,
): VocabularyDistractorUpdate[] {
  const byWord = new Map(results.map((r) => [r.word, r.distractors]));
  return candidates
    .map((candidate) => ({
      frameIndex: candidate.frameIndex,
      wordIndex: candidate.wordIndex,
      distractors: byWord.get(candidate.word) ?? [],
    }))
    .filter((update) => update.distractors.length > 0);
}

// Mirrors the backend's MAX_VOCAB_CLOZE_PER_WORD cap.
const MAX_VOCAB_CLOZE_PER_WORD = 4;

export interface ClozeGrowthCandidate {
  frameIndex: number;
  wordIndex: number;
  word: string;
  translation: string;
  context?: string;
  existing: string[];
}

/** Pure planning step for growVocabularyClozePool: picks the words in a
 * story whose persisted cloze-candidate pool hasn't reached the cap yet,
 * pairing each with its existing sentences (sent as the AI's "avoid" list).
 * Mirrors planDistractorGrowth above. */
export function planClozeGrowth(
  topic: Pick<
    Topic,
    "images" | "vocabulary" | "vocabularyTranslation" | "vocabularyCloze" | "suggestedAnswers"
  >,
): ClozeGrowthCandidate[] {
  const candidates: ClozeGrowthCandidate[] = [];
  topic.images.forEach((_, si) => {
    const sceneSuggestedAnswer = topic.suggestedAnswers?.[si];
    (topic.vocabulary[si] || []).forEach((word, i) => {
      const translation = topic.vocabularyTranslation?.[si]?.[i];
      if (!translation) return;
      const existing = topic.vocabularyCloze?.[si]?.[i] ?? [];
      if (existing.length >= MAX_VOCAB_CLOZE_PER_WORD) return;
      candidates.push({
        frameIndex: si,
        wordIndex: i,
        word,
        translation,
        context: sceneSuggestedAnswer,
        existing: existing.map((c) => c.sentence),
      });
    });
  });
  return candidates;
}

/** Pairs each growth candidate with the AI-generated cloze result for its
 * word (matched by word text), dropping any candidate the AI returned
 * nothing for. Mirrors buildDistractorPatchUpdates above. */
export function buildClozePatchUpdates(
  candidates: ClozeGrowthCandidate[],
  results: Array<{ word: string; sentence: string; distractors: string[] }>,
): VocabularyClozeUpdate[] {
  const byWord = new Map(results.map((r) => [r.word, r]));
  return candidates
    .map((candidate) => {
      const result = byWord.get(candidate.word);
      return {
        frameIndex: candidate.frameIndex,
        wordIndex: candidate.wordIndex,
        candidates: result ? [{ sentence: result.sentence, distractors: result.distractors }] : [],
      };
    })
    .filter((update) => update.candidates.length > 0);
}

// Mirrors the backend's MAX_VOCAB_SYNONYM_PER_WORD cap.
const MAX_VOCAB_SYNONYM_PER_WORD = 4;

export interface SynonymGrowthCandidate {
  frameIndex: number;
  wordIndex: number;
  word: string;
  translation: string;
  context?: string;
  existing: string[];
}

/** Pure planning step for growVocabularySynonymPool — mirrors
 * planClozeGrowth above, for the synonym-candidate pool instead. */
export function planSynonymGrowth(
  topic: Pick<
    Topic,
    "images" | "vocabulary" | "vocabularyTranslation" | "vocabularySynonym" | "suggestedAnswers"
  >,
): SynonymGrowthCandidate[] {
  const candidates: SynonymGrowthCandidate[] = [];
  topic.images.forEach((_, si) => {
    const sceneSuggestedAnswer = topic.suggestedAnswers?.[si];
    (topic.vocabulary[si] || []).forEach((word, i) => {
      const translation = topic.vocabularyTranslation?.[si]?.[i];
      if (!translation) return;
      const existing = topic.vocabularySynonym?.[si]?.[i] ?? [];
      if (existing.length >= MAX_VOCAB_SYNONYM_PER_WORD) return;
      candidates.push({
        frameIndex: si,
        wordIndex: i,
        word,
        translation,
        context: sceneSuggestedAnswer,
        existing: existing.map((c) => c.synonym),
      });
    });
  });
  return candidates;
}

/** Pairs each growth candidate with the AI-generated synonym result for its
 * word (matched by word text), dropping any candidate the AI returned
 * nothing for. Mirrors buildClozePatchUpdates above. */
export function buildSynonymPatchUpdates(
  candidates: SynonymGrowthCandidate[],
  results: Array<{ word: string; synonym: string; distractors: string[] }>,
): VocabularySynonymUpdate[] {
  const byWord = new Map(results.map((r) => [r.word, r]));
  return candidates
    .map((candidate) => {
      const result = byWord.get(candidate.word);
      return {
        frameIndex: candidate.frameIndex,
        wordIndex: candidate.wordIndex,
        candidates: result ? [{ synonym: result.synonym, distractors: result.distractors }] : [],
      };
    })
    .filter((update) => update.candidates.length > 0);
}

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
   * shape_direction_disagreement, weak_shape, strong_negative_evidence,
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

type ScenePracticeStep = "study" | "speaking";

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

export function attemptHistoryFromAudioRecords(
  records: StoredAudioRecord[],
): Record<number, Array<{ tone: number; fluency: number; attempt: number }>> {
  const grouped = new Map<number, StoredAudioRecord[]>();
  // The list endpoint is newest-first. Present history in recording order.
  [...records].reverse().forEach((record) => {
    if (record.imageIndex === undefined || !record.praatMetrics) return;
    const history = grouped.get(record.imageIndex) ?? [];
    history.push(record);
    grouped.set(record.imageIndex, history);
  });
  return Object.fromEntries(
    [...grouped.entries()].map(([sceneIndex, history]) => [
      sceneIndex,
      history.map((record, index) => {
        const metrics = record.praatMetrics as PraatMetrics;
        return {
          tone: Math.round(metrics.tone_accuracy ?? 0),
          fluency: Math.round(metrics.fluency_score ?? 0),
          attempt: record.attemptNumber ?? index + 1,
        };
      }),
    ]),
  );
}

const AUDIO_RECORDS_CACHE_KEY = "audioRecords";
const SPEAKING_PROGRESS_CACHE_PREFIX = "speakingProgress:";

function speakingProgressCacheKey(studentId: string, topicId: string): string {
  return `${SPEAKING_PROGRESS_CACHE_PREFIX}${studentId}:${topicId}`;
}

function readLocalSpeakingProgress(
  studentId: string,
  topicId: string,
): StoredSpeakingProgress[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(speakingProgressCacheKey(studentId, topicId));
    const rows = raw ? JSON.parse(raw) : [];
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

function writeLocalSpeakingProgress(progress: StoredSpeakingProgress): void {
  if (typeof window === "undefined") return;
  try {
    const rows = readLocalSpeakingProgress(progress.studentId, progress.topicId);
    const next = rows.filter((row) => row.sceneIndex !== progress.sceneIndex);
    window.localStorage.setItem(
      speakingProgressCacheKey(progress.studentId, progress.topicId),
      JSON.stringify([...next, progress]),
    );
  } catch {
    // localStorage can be unavailable or full; the server remains the source
    // of truth whenever it is reachable.
  }
}

function readLocalAudioRecords(
  studentId: string,
  topicId: string,
): StoredAudioRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const rows = JSON.parse(window.localStorage.getItem(AUDIO_RECORDS_CACHE_KEY) || "[]");
    if (!Array.isArray(rows)) return [];
    return rows.filter(
      (row: StoredAudioRecord) =>
        row.studentId === studentId && row.topicId === topicId,
    );
  } catch {
    return [];
  }
}

function mergeAudioRecords(
  localRows: StoredAudioRecord[],
  serverRows: StoredAudioRecord[],
): StoredAudioRecord[] {
  const byId = new Map<string, StoredAudioRecord>();
  [...localRows, ...serverRows].forEach((row) => byId.set(row.id, row));
  return [...byId.values()].sort(
    (left, right) =>
      new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime(),
  );
}

function mergeSpeakingProgress(
  localRows: StoredSpeakingProgress[],
  serverRows: StoredSpeakingProgress[],
): StoredSpeakingProgress[] {
  const byScene = new Map<number, StoredSpeakingProgress>();
  localRows.forEach((row) => byScene.set(row.sceneIndex, row));
  serverRows.forEach((row) => {
    const local = byScene.get(row.sceneIndex);
    byScene.set(row.sceneIndex, {
      ...(local || {}),
      ...row,
      // A server row written before migration 0016 has no snapshot. Keep the
      // locally persisted snapshot until the next successful server save.
      latestResult: row.latestResult ?? local?.latestResult ?? null,
    });
  });
  return [...byScene.values()];
}

interface StoryRecorderProps {
  topic: Topic;
  selectedImage: string;
  selectedImageIndex: number;
  onImageSelect: (index: number) => void;
  onImageChange: (image: string) => void;
  onAddRecord: (record: NewAudioRecord) => Promise<string | undefined> | void;
  enableSorting?: boolean;
  /** Show the orientation screen (challenge summary + "here's what you'll do"
   * modal) before the student reaches the recording workspace. Independent of
   * `enableSorting` so production can restore student-facing orientation
   * without reintroducing the picture-ordering minigame. */
  enableOverview?: boolean;
  studentName?: string;
  /** Roster-assigned id (see LoginPage), when the student signed in via the
   * roster picker rather than a name typed before the roster existed —
   * lets attempt records join on a stable id instead of a free-typed
   * name. */
  studentId?: string;
  /** Leaves this topic entirely, back to the topic list — rendered as the
   * single exit action in the nav panel above the phase steps. Omitted
   * (no button shown) when there's nowhere to exit to. */
  onExit?: () => void;
  /** Open help requests for the raise-hand panel docked at the bottom of
   * the session sidebar. Omitted (no panel) outside the student app. */
  helpRequests?: HelpRequest[];
  onRaiseHand?: (message: string) => void;
}

export default function StoryRecorder({
  topic,
  selectedImage,
  selectedImageIndex,
  onImageSelect,
  onImageChange,
  onAddRecord,
  enableSorting = false,
  enableOverview = false,
  studentName = "Student",
  studentId,
  onExit,
  helpRequests,
  onRaiseHand,
}: StoryRecorderProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [pendingVoiceFile, setPendingVoiceFile] = useState<File | null>(null);
  const [pendingVoiceFileUrl, setPendingVoiceFileUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<SpeechModel>("webspeech");
  const [groqAsrAvailable, setGroqAsrAvailable] = useState(false);
  const [openaiAsrAvailable, setOpenaiAsrAvailable] = useState(false);
  const speechModelChosenByStudentRef = useRef(false);
  const [aiProvider, setAiProvider] = useState<string>("");
  // Admin backdoor (name "admin" at login): every gate in the session reads
  // as passed. Computed here so all progression gates share the same policy.
  const isAdmin = isAdminSession();
  // Pilot context remains available for the study-specific progression rules.
  const isPilotSession = resolvePilotContext().studyPhase === "pilot";
  // Stable V1 is the only student-facing analysis path. It is the
  // teacher-validated implementation and remains explicit in request metadata.
  const analysisVersion: AnalysisVersion = "stable_v1";
  const [silenceDuration, setSilenceDuration] = useState(0);
  const [recordingDuration, setRecordingDuration] = useState(0);

  useEffect(() => {
    return () => {
      if (pendingVoiceFileUrl) URL.revokeObjectURL(pendingVoiceFileUrl);
    };
  }, [pendingVoiceFileUrl]);

  // Per-scene result maps — keyed by image index so switching scenes restores
  // the last analysis result for that scene instead of showing a blank state.
  const [praatMetricsMap, setPraatMetricsMap] = useState<
    Record<number, PraatMetrics | null>
  >({});
  const [analysisAudioBlobMap, setAnalysisAudioBlobMap] = useState<
    Record<number, Blob | null>
  >({});
  const [attemptHistoryMap, setAttemptHistoryMap] = useState<
    Record<number, Array<{ tone: number; fluency: number; attempt: number }>>
  >({});
  // Transcript history is still collected per scene (submission/summary
  // consumers read the latest via currentTranscriptRef) even though the
  // Speaking flow now shows only the newest transcript inline.
  const [, setTranscriptionsMap] = useState<
    Record<number, TranscriptionItem[]>
  >({});

  // Derived values for the currently-selected scene — same names as before so
  // all downstream reads require no changes.
  const praatMetrics = praatMetricsMap[selectedImageIndex] ?? null;
  const analysisAudioBlob = analysisAudioBlobMap[selectedImageIndex] ?? null;
  const attemptHistory = attemptHistoryMap[selectedImageIndex] ?? [];

  // Setters scoped to the current scene index.
  const setPraatMetrics = (v: PraatMetrics | null) =>
    setPraatMetricsMap((prev) => ({ ...prev, [selectedImageIndex]: v }));
  const setAnalysisAudioBlob = (v: Blob | null) =>
    setAnalysisAudioBlobMap((prev) => ({ ...prev, [selectedImageIndex]: v }));
  const setAttemptHistory = (
    updater:
      | Array<{ tone: number; fluency: number; attempt: number }>
      | ((
          prev: Array<{ tone: number; fluency: number; attempt: number }>,
        ) => Array<{ tone: number; fluency: number; attempt: number }>),
  ) =>
    setAttemptHistoryMap((prev) => ({
      ...prev,
      [selectedImageIndex]:
        typeof updater === "function"
          ? updater(prev[selectedImageIndex] ?? [])
          : updater,
    }));
  const setTranscriptions = (
    updater:
      | TranscriptionItem[]
      | ((prev: TranscriptionItem[]) => TranscriptionItem[]),
  ) =>
    setTranscriptionsMap((prev) => ({
      ...prev,
      [selectedImageIndex]:
        typeof updater === "function"
          ? updater(prev[selectedImageIndex] ?? [])
          : updater,
    }));
  // Per-scene progress: keyed by imageIndex
  const [sceneProgress, setSceneProgress] = useState<
    Record<number, { attempts: number; bestTone: number; bestFluency: number }>
  >({});
  // Pronunciation mastery gate, keyed by imageIndex. A scene is "mastered"
  // only when a full-sentence recording had every word clear the backend's
  // per-syllable pass verdict. When it didn't, the student first drills each
  // failed word to a pass (clearedWordsMap tracks those), then must re-record
  // the whole sentence — every fresh analysis resets the cleared list because
  // the new recording re-judges everything.
  const [masteryPassedMap, setMasteryPassedMap] = useState<
    Record<number, boolean>
  >({});
  // PART 3: mirrors masteryPassedMap's pilot override, but for `sceneReady`'s
  // separate bestTone/bestFluency/attempts>=4 gate -- forcing masteryPassed
  // alone would still leave a pilot student stuck behind that legacy score
  // threshold. Stays false (no behavior change) until an operator turns on
  // the pilot assistive-feedback flag server-side.
  const [pilotSceneReadyOverrideMap, setPilotSceneReadyOverrideMap] = useState<
    Record<number, boolean>
  >({});
  // A high tone/fluency score alone must not unlock a scene when the learner
  // said a different sentence or skipped required words.
  const [contentPassedMap, setContentPassedMap] = useState<
    Record<number, boolean>
  >({});
  const [clearedWordsMap, setClearedWordsMap] = useState<
    Record<number, string[]>
  >({});
  // Fire-and-forget: a save failure must never block the practice flow the
  // student is already mid-way through. Skipped without a logged-in student
  // (admin/guest) since there's no id to key the row on.
  const persistSpeakingProgress = useCallback(
    (sceneIndex: number, fields: Partial<StoredSpeakingProgress>) => {
      if (!studentId) return;
      const prog = sceneProgress[sceneIndex] ?? {
        attempts: 0,
        bestTone: 0,
        bestFluency: 0,
      };
      const progress: StoredSpeakingProgress = {
        studentId,
        topicId: topic.id,
        sceneIndex,
        attempts: prog.attempts,
        bestTone: prog.bestTone,
        bestFluency: prog.bestFluency,
        masteryPassed: masteryPassedMap[sceneIndex] ?? false,
        contentPassed: contentPassedMap[sceneIndex] ?? false,
        clearedWords: clearedWordsMap[sceneIndex] ?? [],
        ...fields,
      };
      writeLocalSpeakingProgress(progress);
      if (!canUseDatabase()) return;
      saveSpeakingProgress(progress).catch((err) => {
        console.error("Failed to save speaking progress:", err);
      });
    },
    [
      studentId,
      topic.id,
      sceneProgress,
      masteryPassedMap,
      contentPassedMap,
      clearedWordsMap,
    ],
  );
  const handleWordDrillPass = useCallback(
    (token: string) => {
      const current = clearedWordsMap[selectedImageIndex] ?? [];
      if (current.includes(token)) return;
      const next = [...current, token];
      setClearedWordsMap((prev) => ({ ...prev, [selectedImageIndex]: next }));
      persistSpeakingProgress(selectedImageIndex, { clearedWords: next });
    },
    [selectedImageIndex, clearedWordsMap, persistSpeakingProgress],
  );
  // Completed scene snapshots for story submission
  const [sceneRecordings, setSceneRecordings] = useState<
    Record<number, SceneSubmission>
  >({});
  // Self-eval only ever fires on the attempt that just became this scene's
  // saved snapshot (see SpeakingResultsFlow's showSelfEval), so the merge
  // target always exists by the time the student answers.
  const handleSelfEvalSubmit = useCallback(
    (levels: { content: SelfEvalLevel; pronunciation: SelfEvalLevel }) => {
      const existing = sceneRecordings[selectedImageIndex];
      if (!existing) return;
      const latestResult: SceneSubmission = {
        ...existing,
        selfEvalContent: levels.content,
        selfEvalPronunciation: levels.pronunciation,
      };
      setSceneRecordings((prev) => ({ ...prev, [selectedImageIndex]: latestResult }));
      // Best-effort, just like aggregate progress: the learner can continue
      // offline and the self-check is retained when persistence is available.
      persistSpeakingProgress(selectedImageIndex, { latestResult });
    },
    [selectedImageIndex, sceneRecordings, persistSpeakingProgress],
  );
  const [storySubmitted, setStorySubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [storyFeedbackResult, setStoryFeedbackResult] = useState<{
    concatenatedAudioUrl?: string | null;
    storyFeedback?: StoryFeedback | null;
  } | null>(null);

  // Shared with the lesson gate (see utils/topicQuiz) so "this story has a
  // quiz" means exactly one thing app-wide.
  const quizEntries = useMemo(() => topicQuizEntries(topic), [topic]);
  const hasVocabQuiz = quizEntries.length >= 1;

  // Whether this student has already finished the vocabulary quiz for this
  // specific story (persisted across visits) — a story with no quiz content
  // at all counts as "nothing to gate on", not "not yet done". Re-read
  // directly in the topic-change effect below (not derived reactively from
  // this state) so the very first phase decision after switching stories
  // already reflects the new topic's completion status, not a stale one.
  const [vocabQuizCompleted, setVocabQuizCompleted] = useState(
    () => loadCompletedVocabQuizzes()[topic.id] === true,
  );
  // isAdmin is computed earlier (near studentScope) — the pilot
  // Stable/Experimental hiding needs it before this point too. Same
  // backdoor gates quiz-before-speaking here and per-scene mastery below
  // (sceneReady's own bypass lives in storyRecorderFeedback).
  const speakingLocked = hasVocabQuiz && !vocabQuizCompleted && !isAdmin;

  const handleVocabQuizDone = () => {
    markVocabQuizCompleted(topic.id);
    setVocabQuizCompleted(true);
    setPhase("practice");
  };

  // Records a finished quiz attempt for tracking (question-by-question
  // correctness/timing, total score, total time). Best-effort: a save
  // failure shouldn't block the student from moving on to practice, so it's
  // fire-and-forget with just a console warning on failure.
  const handleVocabQuizComplete = (summary: VocabQuizSummary) => {
    if (!canUseDatabase()) return;
    createVocabQuizAttempt({
      id: `vocab-quiz-${topic.id}-${Date.now()}`,
      storyId: topic.id,
      studentName,
      studentId,
      mode: summary.mode,
      completedAt: new Date().toISOString(),
      totalQuestions: summary.totalQuestions,
      correctCount: summary.correctCount,
      totalTimeMs: summary.totalTimeMs,
      questionResults: summary.questionResults,
    }).catch((error) => {
      console.warn("Failed to save vocabulary quiz attempt:", error);
    });
    growVocabularyDistractorPool().catch((error) => {
      console.warn("Failed to grow vocabulary distractor pool:", error);
    });
    growVocabularyClozePool().catch((error) => {
      console.warn("Failed to grow vocabulary cloze pool:", error);
    });
    growVocabularySynonymPool().catch((error) => {
      console.warn("Failed to grow vocabulary synonym pool:", error);
    });
  };

  // topic.id is a quiz-tracking id, prefixed/suffixed for teacher-authored
  // stories (`teacher-{realId}` or `teacher-{realId}-{tier}` — see
  // storyToTopic) so Easy/Medium/Hard track vocab-quiz completion and
  // attempts independently. The custom-stories PATCH endpoints below key on
  // the *real* story id instead (topic.sourceStory.id) — using topic.id
  // there 404s silently (caught by the .catch below) and the AI pool never
  // actually persists. Falls back to topic.id for non-teacher-authored
  // topics, which have no sourceStory and use their id as-is.
  const persistedStoryId = topic.sourceStory?.id ?? topic.id;

  // Each genuine quiz round completion (never the missed-words retry, since
  // onComplete above only fires for the original round) is a chance to top
  // up the story's persisted distractor pool for any word still under the
  // cap — so across many rounds the wrong-answer options keep changing
  // instead of settling into a small fixed set the student can memorize.
  // Skips the AI call entirely once every word has reached the cap.
  const growVocabularyDistractorPool = async () => {
    const candidates = planDistractorGrowth(topic);
    if (candidates.length === 0) return;

    const response = await fetch(`${getBackendUrl()}/api/vocab-quiz-distractors`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        words: candidates.map((entry) => ({
          word: entry.word,
          translation: entry.translation,
          context: entry.context,
          avoid: entry.existing,
        })),
      }),
    });
    if (!response.ok) throw new Error("Could not generate new quiz distractors.");

    const { results } = (await response.json()) as {
      results: { word: string; distractors: string[] }[];
    };
    const updates = buildDistractorPatchUpdates(candidates, results);
    if (updates.length === 0) return;

    await updateVocabularyDistractors(persistedStoryId, updates);
  };

  // Same growth pattern as growVocabularyDistractorPool above, for the
  // fill-in-the-blank cloze question pool instead.
  const growVocabularyClozePool = async () => {
    const candidates = planClozeGrowth(topic);
    if (candidates.length === 0) return;

    const response = await fetch(`${getBackendUrl()}/api/vocab-quiz-cloze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        words: candidates.map((entry) => ({
          word: entry.word,
          translation: entry.translation,
          context: entry.context,
          avoid: entry.existing,
        })),
      }),
    });
    if (!response.ok) throw new Error("Could not generate new quiz cloze questions.");

    const { results } = (await response.json()) as {
      results: { word: string; sentence: string; distractors: string[] }[];
    };
    const updates: VocabularyClozeUpdate[] = buildClozePatchUpdates(candidates, results);
    if (updates.length === 0) return;

    await updateVocabularyCloze(persistedStoryId, updates);
  };

  // Same growth pattern as growVocabularyClozePool above, for the
  // "which word means the same?" synonym question pool instead.
  const growVocabularySynonymPool = async () => {
    const candidates = planSynonymGrowth(topic);
    if (candidates.length === 0) return;

    const response = await fetch(`${getBackendUrl()}/api/vocab-quiz-synonym`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        words: candidates.map((entry) => ({
          word: entry.word,
          translation: entry.translation,
          context: entry.context,
          avoid: entry.existing,
        })),
      }),
    });
    if (!response.ok) throw new Error("Could not generate new quiz synonym questions.");

    const { results } = (await response.json()) as {
      results: { word: string; synonym: string; distractors: string[] }[];
    };
    const updates: VocabularySynonymUpdate[] = buildSynonymPatchUpdates(candidates, results);
    if (updates.length === 0) return;

    await updateVocabularySynonym(persistedStoryId, updates);
  };

  // Learning phase: overview → sorting → vocabquiz → practice → summary
  const [phase, setPhase] = useState<
    "overview" | "sorting" | "vocabquiz" | "practice" | "summary"
  >(
    enableOverview
      ? "overview"
      : enableSorting
        ? "sorting"
        : speakingLocked
          ? "vocabquiz"
          : "practice",
  );
  // Within the "practice" phase, each scene walks its own study → speaking
  // sub-steps (skipping the study step if this scene has neither vocabulary
  // nor phrases) rather than showing everything at once. Vocabulary and
  // phrases share one "study" step — both are reference material read
  // before recording, not separate tasks — so they no longer compete for a
  // tab slot of their own.
  const sceneHasVocabStep = (idx: number) =>
    (topic.vocabulary[idx] || []).length > 0;
  const sceneHasPhrasesStep = (idx: number) =>
    (topic.phrases?.[idx] || []).length > 0;
  const sceneHasStudyStep = (idx: number) =>
    sceneHasVocabStep(idx) || sceneHasPhrasesStep(idx);
  const firstScenePracticeStep = (idx: number): ScenePracticeStep =>
    sceneHasStudyStep(idx) ? "study" : "speaking";

  const [scenePracticeStep, setScenePracticeStep] = useState<ScenePracticeStep>(
    firstScenePracticeStep(selectedImageIndex),
  );
  // The teacher's model frame is a 🎯 stop on the sidebar journey rather
  // than a stacked panel — this flag swaps the practice stage for the
  // read-only example view while it's set.
  const [viewingExample, setViewingExample] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<any>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const durationIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null,
  );
  const recordingStartRef = useRef(0);
  const lastSpeechAtRef = useRef(0);
  const currentTranscriptRef = useRef("");

  useEffect(() => {
    setScenePracticeStep(firstScenePracticeStep(selectedImageIndex));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedImageIndex, topic.id]);

  useEffect(() => {
    const completed = loadCompletedVocabQuizzes()[topic.id] === true;
    setVocabQuizCompleted(completed);
    const stillLocked = hasVocabQuiz && !completed && !isAdmin;
    const defaultPhase = enableOverview
      ? "overview"
      : enableSorting
        ? "sorting"
        : stillLocked
          ? "vocabquiz"
          : "practice";
    // Resume the step a student was on before a reload, instead of always
    // reopening on the overview screen — but never resume into a phase the
    // current gates would now block (e.g. the quiz got reset elsewhere).
    const reachablePhases = (
      enableOverview
        ? ["overview", "sorting", "vocabquiz", "practice", "summary"]
        : enableSorting
          ? ["sorting", "vocabquiz", "practice", "summary"]
          : ["vocabquiz", "practice", "summary"]
    ) as typeof defaultPhase[];
    const blockedPhases = stillLocked ? new Set(["practice", "summary"]) : new Set<string>();
    const resumed = getLastScenePhase(topic.id);
    setPhase(
      resumed && reachablePhases.includes(resumed as typeof defaultPhase) && !blockedPhases.has(resumed)
        ? (resumed as typeof defaultPhase)
        : defaultPhase,
    );
  }, [topic.id, topic.images, enableSorting, enableOverview, hasVocabQuiz, isAdmin]);

  useEffect(() => {
    saveLastScenePhase(topic.id, phase);
  }, [topic.id, phase]);

  // The local flag is an offline/UI fast path. On reload, recover the same
  // gate from the canonical quiz-attempt history so a completed quiz does not
  // reappear just because this browser lost its local mirror.
  useEffect(() => {
    if (!studentId || !canUseDatabase() || !hasVocabQuiz) return;
    let cancelled = false;
    void listVocabQuizAttempts(topic.id, { studentId, studentName })
      .then((attempts) => {
        if (cancelled || attempts.length === 0) return;
        setVocabQuizCompleted(true);
        markVocabQuizCompleted(topic.id);
        setPhase((current) => (current === "vocabquiz" ? "practice" : current));
      })
      .catch(() => {
        // Keep the local mirror as the offline fallback.
      });
    return () => {
      cancelled = true;
    };
  }, [studentId, studentName, topic.id, hasVocabQuiz]);

  // Restore whatever speaking-practice progress this student already has for
  // this story, so reloading or leaving mid-scene doesn't reset attempts,
  // best scores, or the mastery/content gates back to zero. Skipped for
  // admin/guest sessions — there's no studentId to look progress up by.
  useEffect(() => {
    if (!studentId) return;
    let cancelled = false;
    (async () => {
      try {
        const localRows = readLocalSpeakingProgress(studentId, topic.id);
        let serverRows: StoredSpeakingProgress[] = [];
        if (canUseDatabase()) {
          try {
            serverRows = await listSpeakingProgress(studentId, topic.id);
          } catch (err) {
            console.error("Failed to load speaking progress from database:", err);
          }
        }
        const rows = mergeSpeakingProgress(localRows, serverRows);
        if (cancelled) return;
        setSceneProgress((prev) => {
          const next = { ...prev };
          rows.forEach((row) => {
            next[row.sceneIndex] = {
              attempts: row.attempts,
              bestTone: row.bestTone,
              bestFluency: row.bestFluency,
            };
          });
          return next;
        });
        setMasteryPassedMap((prev) => {
          const next = { ...prev };
          rows.forEach((row) => {
            next[row.sceneIndex] = row.masteryPassed;
          });
          return next;
        });
        setContentPassedMap((prev) => {
          const next = { ...prev };
          rows.forEach((row) => {
            next[row.sceneIndex] = row.contentPassed;
          });
          return next;
        });
        setClearedWordsMap((prev) => {
          const next = { ...prev };
          rows.forEach((row) => {
            next[row.sceneIndex] = row.clearedWords;
          });
          return next;
        });
        setSceneRecordings((prev) => {
          const next = { ...prev };
          rows.forEach((row) => {
            if (row.latestResult) next[row.sceneIndex] = row.latestResult;
          });
          return next;
        });
      } catch (err) {
        console.error("Failed to load speaking progress:", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [studentId, topic.id]);

  // Restore every persisted attempt for the current story. The newest attempt
  // remains the active feedback/audio result, while the full history powers
  // the retry trend. Legacy progress rows without `latestResult` get a
  // submission snapshot reconstructed from that newest audio row.
  useEffect(() => {
    if (!studentId) return;
    let cancelled = false;
    (async () => {
      try {
        const localRows = readLocalAudioRecords(studentId, topic.id);
        let serverRows: StoredAudioRecord[] = [];
        if (canUseDatabase()) {
          try {
            serverRows = await listAudioRecords({
              studentId,
              topicId: topic.id,
              limit: 1000,
            });
          } catch (err) {
            console.error("Failed to load audio records from database:", err);
          }
        }
        const rows = mergeAudioRecords(localRows, serverRows);
        if (cancelled || rows.length === 0) return;

        const latestRowsByScene = new Map<number, StoredAudioRecord>();
        rows.forEach((row) => {
          if (row.imageIndex !== undefined && !latestRowsByScene.has(row.imageIndex)) {
            latestRowsByScene.set(row.imageIndex, row);
          }
        });
        const latestRows = [...latestRowsByScene.values()];

        setPraatMetricsMap((prev) => {
          const next = { ...prev };
          latestRows.forEach((row) => {
            if (row.imageIndex === undefined || next[row.imageIndex]) return;
            if (row.praatMetrics) next[row.imageIndex] = row.praatMetrics as PraatMetrics;
          });
          return next;
        });
        setAttemptHistoryMap((prev) => {
          const next = { ...prev };
          const restoredHistory = attemptHistoryFromAudioRecords(rows);
          Object.entries(restoredHistory).forEach(([sceneIndex, history]) => {
            const numericSceneIndex = Number(sceneIndex);
            if (next[numericSceneIndex]?.length) return;
            next[numericSceneIndex] = history;
          });
          return next;
        });
        setSceneRecordings((prev) => {
          const next = { ...prev };
          latestRows.forEach((row) => {
            if (row.imageIndex === undefined || next[row.imageIndex]) return;
            const fallback = sceneSubmissionFromAudioRecord(row);
            if (fallback) next[row.imageIndex] = fallback;
          });
          return next;
        });

        // The recording itself is fetched best-effort — a missing/failed
        // fetch still leaves the restored feedback and scores usable, just
        // without audio playback for that scene (same fallback the results
        // view already has for "no recording available").
        await Promise.all(
          latestRows.map(async (row) => {
            if (row.imageIndex === undefined || !row.audioUrl) return;
            try {
              const url = row.audioUrl.startsWith("/uploads/")
                ? `${getBackendUrl()}${row.audioUrl}`
                : row.audioUrl;
              const res = await fetch(url);
              if (!res.ok || cancelled) return;
              const blob = await res.blob();
              if (cancelled) return;
              setAnalysisAudioBlobMap((prev) =>
                prev[row.imageIndex!] ? prev : { ...prev, [row.imageIndex!]: blob },
              );
            } catch {
              // Playback unavailable for this scene — feedback data still restored above.
            }
          }),
        );
      } catch (err) {
        console.error("Failed to load persisted practice results:", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [studentId, topic.id]);

  useEffect(() => {
    return () => {
      stopTracks();
      clearTimers();
    };
  }, []);

  // When firstFrameIsExample is set, skip frame 0 automatically on entering practice.
  useEffect(() => {
    if (
      topic.firstFrameIsExample &&
      selectedImageIndex === 0 &&
      topic.images.length > 1
    ) {
      onImageSelect(1);
      onImageChange(topic.images[1]);
    }
  }, [topic.id, topic.firstFrameIsExample]);

  // Load the available AI feedback engines to pick a sensible default.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${getBackendUrl()}/api/ai-providers`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled || !Array.isArray(data.providers)) return;
        const groqAvailable = data.providers.some(
          (p: AiProviderOption) => p.id === "groq" && p.available,
        );
        const openaiAvailable = data.providers.some(
          (p: AiProviderOption) => p.id === "openai" && p.available,
        );
        setGroqAsrAvailable(groqAvailable);
        setOpenaiAsrAvailable(openaiAvailable);
        const defaultProvider = (groqAvailable ? "groq" : data.default) || "";
        setAiProvider((prev) => prev || defaultProvider);
        // Sync speech source: if Groq is the default AI provider, use Groq Whisper
        // for transcription too so ASR and feedback both come from the same engine.
        // Once the student makes an explicit choice, an async provider refresh
        // must never overwrite it.
        if (groqAvailable && !speechModelChosenByStudentRef.current) {
          setSelectedModel("groq");
        }
      } catch {
        // Backend unreachable — the picker just stays hidden.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const clearTimers = () => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current);
      durationIntervalRef.current = null;
    }
  };

  const stopTracks = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const startRecording = async () => {
    try {
      setError(null);
      setPraatMetrics(null);
      setAnalysisAudioBlob(null);
      setPendingVoiceFile(null);
      setPendingVoiceFileUrl("");
      currentTranscriptRef.current = "";
      recordingStartRef.current = Date.now();
      setRecordingDuration(0);
      setSilenceDuration(0);
      lastSpeechAtRef.current = Date.now();

      if (selectedModel === "webspeech") {
        await startWebSpeechRecording();
      } else {
        await startAudioRecording(async (audioBlob) => {
          if (selectedModel === "vibevoice") {
            await analyzeSpeechAudio(audioBlob, "", "vibevoice");
          } else {
            await transcribeAudio(audioBlob);
          }
        });
        setIsRecording(true);
      }

      durationIntervalRef.current = setInterval(() => {
        const elapsed = Math.min(
          MAX_RECORDING_SECONDS,
          Math.floor((Date.now() - recordingStartRef.current) / 1000),
        );
        setRecordingDuration(elapsed);
        if (elapsed >= MAX_RECORDING_SECONDS) stopRecording();
      }, 250);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "無法存取麥克風，請檢查權限設定。 Failed to access microphone. Please check permissions.",
      );
      setIsRecording(false);
      clearTimers();
      stopTracks();
    }
  };

  const startWebSpeechRecording = async () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      throw new Error(
        "此瀏覽器不支援 Web Speech API，請使用 Chrome、Edge 或 Safari。 Web Speech API is not supported in this browser. Use Chrome, Edge, or Safari.",
      );
    }

    await startAudioRecording(async (audioBlob) => {
      await analyzeSpeechAudio(audioBlob, currentTranscriptRef.current.trim());
    });

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "zh-TW";

    recognition.onstart = () => {
      setIsRecording(true);
      startSilenceDetection(recognition);
    };

    recognition.onresult = (event: any) => {
      let heardSpeech = false;
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          currentTranscriptRef.current =
            `${currentTranscriptRef.current} ${transcript}`.trim();
          addTranscription(transcript);
          heardSpeech = true;
        } else if (transcript.trim()) {
          heardSpeech = true;
        }
      }

      if (heardSpeech) {
        lastSpeechAtRef.current = Date.now();
        setSilenceDuration(0);
      }
    };

    recognition.onerror = (event: any) => {
      // "network" means the browser can't reach Google's speech servers.
      // "no-speech" / "aborted" are benign. In all these cases the MediaRecorder
      // is still running, so just let the recording finish and fall back to the
      // backend Groq ASR for transcription.
      const nonFatal = ["network", "no-speech", "aborted"];
      if (nonFatal.includes(event.error)) {
        console.warn(`WebSpeech ${event.error} — will use backend ASR instead`);
        recognition.stop(); // triggers onend → stopAudioRecording → Groq ASR
      } else {
        setError(`Speech recognition error: ${event.error}`);
      }
    };

    recognition.onend = () => {
      setIsRecording(false);
      clearTimers();
      stopAudioRecording();
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const startSilenceDetection = (recognition: any) => {
    const silenceThreshold = 7000;
    const checkInterval = 250;

    const checkSilence = () => {
      const currentSilenceTime = Date.now() - lastSpeechAtRef.current;
      setSilenceDuration(Math.floor(currentSilenceTime / 1000));

      if (currentSilenceTime >= silenceThreshold) {
        recognition.stop();
      } else {
        silenceTimerRef.current = setTimeout(checkSilence, checkInterval);
      }
    };

    silenceTimerRef.current = setTimeout(checkSilence, checkInterval);
  };

  const startAudioRecording = async (
    onStop: (audioBlob: Blob) => Promise<void>,
  ) => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    streamRef.current = stream;

    const preferredType = MediaRecorder.isTypeSupported("audio/webm")
      ? "audio/webm"
      : "";
    const mediaRecorder = new MediaRecorder(
      stream,
      preferredType ? { mimeType: preferredType } : undefined,
    );
    mediaRecorderRef.current = mediaRecorder;
    audioChunksRef.current = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunksRef.current.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      const rawBlob = new Blob(audioChunksRef.current, {
        type: mediaRecorder.mimeType || "audio/webm",
      });
      try {
        await onStop(rawBlob);
      } finally {
        stopTracks();
      }
    };

    mediaRecorder.start();
  };

  const stopAudioRecording = () => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
  };

  const stopRecording = () => {
    if (selectedModel === "webspeech") {
      recognitionRef.current?.stop();
    } else {
      stopAudioRecording();
      setIsRecording(false);
    }

    clearTimers();
    setSilenceDuration(0);
  };

  const transcribeAudio = async (audioBlob: Blob) => {
    setIsTranscribing(true);
    let backendUrl = "the configured backend";
    try {
      backendUrl = getBackendUrl();
      const wavBlob = await convertBlobToWav(audioBlob);
      const formData = new FormData();
      formData.append("file", wavBlob, "speech.wav");
      formData.append("model", selectedModel);
      const sceneVocab = (topic.vocabulary[selectedImageIndex] || []).join(
        ", ",
      );
      if (sceneVocab) formData.append("vocab_hint", sceneVocab);

      const response = await fetch(`${backendUrl}/api/transcribe`, {
        method: "POST",
        body: formData,
        signal: AbortSignal.timeout(120_000),
      });

      if (!response.ok) {
        const errorData = await readErrorResponse(response);
        throw new Error(errorData.detail || "轉錄失敗 Transcription failed");
      }

      const data = await response.json();
      const transcript = (data.text || "").trim();
      if (transcript) {
        addTranscription(transcript);
        currentTranscriptRef.current = transcript;
      }
      await analyzeSpeechAudio(wavBlob, transcript, selectedModel);
    } catch (err) {
      setError(
        formatBackendError(err, backendUrl),
      );
    } finally {
      setIsTranscribing(false);
    }
  };

  const analyzeSpeechAudio = async (
    audioBlob: Blob,
    transcription: string,
    asrModel = "",
    recordModel: SpeechModel = selectedModel,
    version: AnalysisVersion = analysisVersion,
  ) => {
    setIsAnalyzing(true);
    let backendUrl = "the configured backend";
    try {
      backendUrl = getBackendUrl();
      const wavBlob = await convertBlobToWav(audioBlob);
      const analysisText = transcription.trim();
      // Scene context for smarter feedback
      const sceneVocab = (topic.vocabulary[selectedImageIndex] || []).join(
        ", ",
      );
      const scenePrompt = topic.prompts?.[selectedImageIndex] || topic.name;
      const scenePhrases = topic.phrases?.[selectedImageIndex];
      const sceneSuggestedAnswer = topic.suggestedAnswers?.[selectedImageIndex];
      const sceneTargetText =
        topic.listenScripts?.[selectedImageIndex]?.trim() ||
        sceneSuggestedAnswer?.trim() ||
        "";
      const sceneReferenceCurves = buildSceneReferenceCurves(topic, selectedImageIndex);
      // Pre-pilot research-logging identity (STEPs 2-6 of
      // `pilot_readiness.md`): reuses the EXISTING student id and the
      // EXISTING (topic, scene) composite item key this app already keys
      // `speaking_progress`/`audio_records` by -- no new identity system.
      // `attemptType` is a simple, non-heuristic default (attempt 1 =
      // initial, later attempts = final) -- see the report's known-limitation
      // note on why this does not yet auto-detect a focused-retry-specific
      // recording (that distinct recording flow doesn't exist in the UI yet).
      // Use the persisted cumulative attempts (sceneProgress from
      // speaking_progress DB) as the source of truth — attemptHistory is
      // only ever a single-entry restore on reload, so falling back to
      // its length would reset every scene's attempt numbering to 1 on
      // every page load and make backend analytics misidentify follow-up
      // recordings as fresh attempts.
      const priorAttemptCount =
        sceneProgress[selectedImageIndex]?.attempts ?? attemptHistory.length;
      const attemptNumberForRequest = priorAttemptCount + 1;
      const pilotContext = resolvePilotContext();
      const attemptIdForRequest = `attempt-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const attemptTypeForRequest: "WHOLE_SENTENCE_INITIAL" | "WHOLE_SENTENCE_FINAL" =
        attemptNumberForRequest === 1 ? "WHOLE_SENTENCE_INITIAL" : "WHOLE_SENTENCE_FINAL";
      const formData = buildPracticeAnalysisFormData(wavBlob, {
        transcription: analysisText,
        asrModel,
        aiProvider,
        sceneVocabulary: sceneVocab,
        scenePrompt,
        sceneImageUrl: selectedImage,
        scenePhrases: scenePhrases?.join("; "),
        sceneSuggestedAnswer,
        sceneTargetText,
        sceneReferenceCurves,
        sceneAttemptNumber: attemptNumberForRequest,
        analysisDetail: version === "phoneme_tone_v2" ? "phoneme" : undefined,
        participantId: getStudentId(),
        itemId: `${topic.id}:${selectedImageIndex}`,
        sessionId: pilotContext.sessionId,
        attemptId: attemptIdForRequest,
        attemptNumber: attemptNumberForRequest,
        attemptType: attemptTypeForRequest,
        studyPhase: pilotContext.studyPhase,
      });

      const endpoint = version === "phoneme_tone_v2" ? "/api/analyze/v2" : "/api/analyze";
      const response = await fetch(`${backendUrl}${endpoint}`, {
        method: "POST",
        body: formData,
        signal: AbortSignal.timeout(120_000),
      });

      if (!response.ok) {
        const errorData = await readErrorResponse(response);
        throw new Error(
          errorData.detail || "Praat 分析失敗 Praat analysis failed",
        );
      }

      const metrics = (await response.json()) as PraatMetrics;
      metrics.analysis_version = metrics.analysis_version ?? version;
      metrics.progression_eligible = version === "stable_v1";
      const canScorePronunciation =
        metrics.feedback_quality?.can_score_pronunciation !== false;
      const canScoreContent =
        metrics.feedback_quality?.can_score_content !== false;
      // Only real transcripts (backend ASR, or the live WebSpeech text) —
      // never the scene's vocabulary list as a stand-in. That old fallback
      // meant a silent recording got "transcribed" as the exact target
      // words and scored as if the student had said them all.
      const finalTranscription = (metrics.transcription || analysisText).trim();
      if (
        finalTranscription &&
        finalTranscription !== currentTranscriptRef.current
      ) {
        currentTranscriptRef.current = finalTranscription;
        addTranscription(finalTranscription, recordModel);
      }
      setPraatMetrics(metrics);
      setAnalysisAudioBlob(wavBlob);
      recordMeasurementEvent(createMeasurementEvent("analysis_completed", {
        studentId: studentId ?? getStudentId(),
        sessionId: pilotContext.sessionId,
        attemptId: attemptIdForRequest,
        topicId: topic.id,
        sceneIndex: selectedImageIndex,
        properties: {
          analysisVersion: version,
          toneAccuracy: Math.round(metrics.tone_accuracy),
          fluencyScore: Math.round(metrics.fluency_score),
          masteryPassed: metrics.pronunciation_mastery?.passed ?? null,
          feedbackQuality: metrics.feedback_quality?.status ?? null,
        },
      }));
      if (version === "phoneme_tone_v2") {
        // V2 is analytics-only until the KPI gate and teacher validation pass.
        await Promise.resolve(onAddRecord({
          id: `audio-${Date.now()}`,
          audioBlob: wavBlob,
          timestamp: new Date().toLocaleString(),
          duration: Math.max(1, Math.floor((Date.now() - recordingStartRef.current) / 1000)),
          transcription: finalTranscription,
          model: recordModel,
          topicId: topic.id,
          imageUrl: selectedImage,
          imageIndex: selectedImageIndex,
          praatMetrics: metrics,
          analysisVersion: version,
          analysisSchemaVersion: metrics.analysis_schema_version,
          modelVersion: metrics.model_version,
          sessionId: pilotContext.sessionId,
          attemptId: attemptIdForRequest,
          attemptNumber: attemptNumberForRequest,
          attemptType: attemptTypeForRequest,
        }));
        return;
      }
      setAttemptHistory((prev) => [
        ...prev,
        {
          tone: Math.round(metrics.tone_accuracy),
          fluency: Math.round(metrics.fluency_score),
          attempt: prev.length + 1,
        },
      ]);
      const priorProgress = sceneProgress[selectedImageIndex] ?? {
        attempts: 0,
        bestTone: 0,
        bestFluency: 0,
      };
      const nextProgress = {
        attempts: priorProgress.attempts + 1,
        bestTone: canScorePronunciation
          ? Math.max(priorProgress.bestTone, Math.round(metrics.tone_accuracy))
          : priorProgress.bestTone,
        bestFluency: canScorePronunciation
          ? Math.max(
              priorProgress.bestFluency,
              Math.round(metrics.fluency_score),
            )
          : priorProgress.bestFluency,
      };
      setSceneProgress((prev) => ({
        ...prev,
        [selectedImageIndex]: nextProgress,
      }));
      // Mastery gate verdict for this full-sentence attempt. A fresh
      // recording re-judges every word, so the per-word drill clearances
      // from the previous attempt reset alongside it.
      //
      // PART 3 of the small-teacher-validated-pilot architecture: for a
      // pilot session where the backend actually computed the assistive
      // layer (`metrics.assistive_feedback` non-null -- only true once an
      // operator has set `ENABLE_ASSISTIVE_FEEDBACK_PILOT_OVERRIDE=1`
      // server-side, per `assistive_feedback/pipeline.py`'s two-gate
      // design), the legacy `word_prosody[].passed` verdict must never
      // block progression -- NO_ISSUE_DETECTED/NO_AUTOMATIC_JUDGMENT/
      // CHECK_THIS_TONE all eventually continue (the bounded one-retry
      // flow lives in SpeakingResultsFlow via `src/utils/retryPolicy.ts`).
      // Until that env flag is set, `assistive_feedback` stays null and
      // this expression is identical to before this task -- dormant by
      // construction, matching the "do not enable pilot globally" limit.
      const pilotAssistiveFeedbackActive = isPilotSession && Boolean(metrics.assistive_feedback);
      const nextMasteryPassed =
        pilotAssistiveFeedbackActive ||
        (canScorePronunciation &&
          (metrics.pronunciation_mastery?.passed ??
            prosodyGatePassed(metrics.word_prosody)));
      const nextContentPassed =
        canScoreContent &&
        sceneContentGatePassed(metrics, Boolean(sceneTargetText?.trim()));
      setMasteryPassedMap((prev) => ({
        ...prev,
        [selectedImageIndex]: nextMasteryPassed,
      }));
      setPilotSceneReadyOverrideMap((prev) => ({
        ...prev,
        [selectedImageIndex]: pilotAssistiveFeedbackActive,
      }));
      setContentPassedMap((prev) => ({
        ...prev,
        [selectedImageIndex]: nextContentPassed,
      }));
      setClearedWordsMap((prev) => ({ ...prev, [selectedImageIndex]: [] }));
      const recordResult = onAddRecord({
        id: `audio-${Date.now()}`,
        audioBlob: wavBlob,
        timestamp: new Date().toLocaleString(),
        duration: Math.max(
          1,
          Math.floor((Date.now() - recordingStartRef.current) / 1000),
        ),
        transcription: finalTranscription,
        model: recordModel,
        topicId: topic.id,
        imageUrl: selectedImage,
        imageIndex: selectedImageIndex,
        praatMetrics: metrics,
        analysisVersion: version,
        analysisSchemaVersion: metrics.analysis_schema_version,
        modelVersion: metrics.model_version,
        sessionId: pilotContext.sessionId,
        attemptId: attemptIdForRequest,
        attemptNumber: attemptNumberForRequest,
        attemptType: attemptTypeForRequest,
      });

      // Save best snapshot for this scene (overwrite if better vocab score)
      const vc = metrics.ai_feedback?.vocabulary_coverage;
      const newSnap: SceneSubmission = {
        sceneIndex: selectedImageIndex,
        imageUrl: selectedImage,
        transcription: finalTranscription,
        vocabUsed: vc?.used ?? [],
        vocabMissing: vc?.missing ?? [],
        vocabScore: vc?.score ?? 0,
        toneAccuracy: Math.round(metrics.tone_accuracy),
        pronScore: averageWordProsodyAccuracy(metrics.word_prosody) ?? 0,
        fluencyScore: Math.round(metrics.fluency_score ?? 0),
        audioUrl: "",
        pauseCount: metrics.pause_analysis?.pause_count ?? 0,
        longestPause: metrics.pause_analysis?.longest_pause ?? 0,
        utteranceCount: metrics.pause_analysis?.utterance_count ?? 0,
        choppyPauseCount: metrics.pause_analysis?.choppy_pause_count ?? 0,
        articulationRate: metrics.pause_analysis?.articulation_rate ?? 0,
      };
      const existingSnapshot = sceneRecordings[selectedImageIndex];
      const latestResult = !existingSnapshot || newSnap.vocabScore >= existingSnapshot.vocabScore
        ? newSnap
        : existingSnapshot;
      setSceneRecordings((prev) => {
        const existing = prev[selectedImageIndex];
        if (!existing || newSnap.vocabScore >= existing.vocabScore) {
          return { ...prev, [selectedImageIndex]: newSnap };
        }
        return prev;
      });
      // Store the same accepted snapshot that story submission uses. This is
      // intentionally best-effort: a network failure must not block analysis
      // or turn an offline practice attempt into an error state.
      persistSpeakingProgress(selectedImageIndex, {
        ...nextProgress,
        masteryPassed: nextMasteryPassed,
        contentPassed: nextContentPassed,
        clearedWords: [],
        latestResult,
      });

      // Patch in the backend audio URL once the upload resolves
      const savedAudioUrl = await Promise.resolve(recordResult);
      if (savedAudioUrl) {
        setSceneRecordings((prev) => {
          const snap = prev[selectedImageIndex];
          if (!snap) return prev;
          return {
            ...prev,
            [selectedImageIndex]: { ...snap, audioUrl: savedAudioUrl },
          };
        });
        persistSpeakingProgress(selectedImageIndex, {
          ...nextProgress,
          masteryPassed: nextMasteryPassed,
          contentPassed: nextContentPassed,
          clearedWords: [],
          latestResult: { ...latestResult, audioUrl: savedAudioUrl },
        });
      }
    } catch (err) {
      setError(
        formatBackendError(err, backendUrl),
      );
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleSubmitVoiceFile = async (
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    if (!file.type.startsWith("audio/") && !hasAudioFileExtension(file.name)) {
      setError(
        `請上傳音訊檔案。不支援「${file.name}」。 Submit an audio file. "${file.name}" is not supported.`,
      );
      return;
    }

    setError(null);
    setPraatMetrics(null);
    setAnalysisAudioBlob(null);
    setPendingVoiceFile(file);
    setPendingVoiceFileUrl(URL.createObjectURL(file));
    currentTranscriptRef.current = "";
    recordingStartRef.current = Date.now();
    setRecordingDuration(0);
  };

  const analyzePendingVoiceFile = async () => {
    if (!pendingVoiceFile) return;
    const file = pendingVoiceFile;
    setPendingVoiceFile(null);
    setPendingVoiceFileUrl("");
    const uploadModel = selectedModel === "webspeech" ? "groq" : selectedModel;
    await analyzeSpeechAudio(file, "", uploadModel, uploadModel);
  };

  const clearPendingVoiceFile = () => {
    setPendingVoiceFile(null);
    setPendingVoiceFileUrl("");
    setError(null);
  };

  const addTranscription = (
    text: string,
    model: SpeechModel = selectedModel,
  ) => {
    if (!text.trim()) return;

    setTranscriptions((prev) => [
      ...prev,
      {
        text,
        timestamp: new Date().toLocaleTimeString(),
        model,
      },
    ]);
  };

  const isBusy = isRecording || isTranscribing || isAnalyzing;
  const selectedVocabulary = topic.vocabulary[selectedImageIndex] || [];
  const recordingButtonDisabled = isTranscribing || isAnalyzing;

  // When the backend's AI vocabulary_coverage is not a real judgment
  // (`judged: false` — for instance the scene-level content match went
  // unverified, so the backend dumped every target word into `missing`),
  // fall back to a plain substring check against the ASR transcript.
  // That matches what "did the student say this word" reduces to when a
  // transcript is on hand, and prevents an entire vocab list from turning
  // ✗ after reload just because sentence-level content verification did
  // not complete — see backend/ai_feedback.py:106+ for how the
  // judged:false branch overwrites used/missing.
  const effectiveVocabCoverage = (() => {
    const rawVC = praatMetrics?.ai_feedback?.vocabulary_coverage;
    if (rawVC && rawVC.judged !== false) return rawVC;
    const transcript = praatMetrics?.transcription?.trim();
    if (!transcript || selectedVocabulary.length === 0) return rawVC ?? null;
    return {
      ...(rawVC ?? {}),
      used: selectedVocabulary.filter((w) => transcript.includes(w)),
      missing: selectedVocabulary.filter((w) => !transcript.includes(w)),
    };
  })();

  const handlePrimaryRecordingAction = () => {
    if (isRecording) {
      stopRecording();
      return;
    }

    startRecording();
  };

  // A teacher-model first frame is reference material, not an activity a
  // student must record. Keep one source of truth for all gates and labels
  // so it cannot accidentally make a story impossible to finish.
  const practiceSceneIndices = practiceSceneIndicesFor(topic);
  const totalScenes = practiceSceneIndices.length;
  const selectedPracticeScenePosition = Math.max(
    practiceSceneIndices.indexOf(selectedImageIndex),
    0,
  );
  const nextPracticeSceneIndex = practiceSceneIndices[selectedPracticeScenePosition + 1];
  const completedSceneCount = practiceSceneIndices.filter(
    (index) => sceneRecordings[index],
  ).length;
  // Submission needs every scene recorded AND pronunciation-mastered — a
  // scene whose latest full-sentence attempt still has failing words keeps
  // the story locked even if an earlier snapshot was saved for it.
  const allScenesRecorded =
    totalScenes > 0 &&
    practiceSceneIndices.every(
      (index) =>
        Boolean(sceneRecordings[index]) &&
        (isAdmin ||
          ((masteryPassedMap[index] ?? false) &&
            (contentPassedMap[index] ?? false))),
    );

  const handleSubmitStory = useCallback(async () => {
    const scenes = Object.values(sceneRecordings).sort(
      (a, b) => a.sceneIndex - b.sceneIndex,
    );
    const submission = {
      id: `submission-${Date.now()}`,
      storyId: topic.id,
      storyTitle: topic.name,
      studentName,
      studentId,
      submittedAt: new Date().toISOString(),
      scenes,
    };
    try {
      if (canUseDatabase()) {
        const result = await createStorySubmission(submission);
        setStoryFeedbackResult({
          concatenatedAudioUrl: result.concatenatedAudioUrl,
          storyFeedback: result.storyFeedback,
        });
      }
      setStorySubmitted(true);
      setSubmitError(null);
      if (topic.sourceStory && topic.difficultyLevel) {
        markStoryLevelSubmitted(topic.sourceStory.id, topic.difficultyLevel);
      }
    } catch {
      setSubmitError(
        "Could not submit story — check your connection and try again.",
      );
    }
  }, [sceneRecordings, topic, studentName]);

  const allVocabulary = topic.images.flatMap(
    (_, si) => topic.vocabulary[si] || [],
  );

  const PHASES = [
    { key: "overview", label: <BiLabel k="overview" />, icon: "📖" },
    ...(enableSorting
      ? [
          {
            key: "sorting" as const,
            label: <BiLabel k="arrange_scenes" />,
            icon: "🧩",
          },
        ]
      : []),
    ...(hasVocabQuiz
      ? [
          {
            key: "vocabquiz" as const,
            label: <BiLabel k="vocabulary_map" />,
            icon: "❓",
          },
        ]
      : []),
    { key: "practice", label: <BiLabel k="speaking" />, icon: "🎙️" },
  ] as const;
  void PHASES;

  // "summary" isn't a phase-nav tab (it's only reachable after finishing
  // every scene) — treat it as past the last tab so the nav bar shows
  // every real phase as done rather than falling back to "upcoming".
  // The visible sidebar uses the simplified three-state flow below.

  // Shared scene-stop data for the journey path — rendered both in the
  // practice header (jump between scenes) and in the end-of-journey summary
  // (review everything at a glance). `goToScene` differs per caller: from
  // practice it just switches the selected image; from summary it also has
  // to switch phase back to "practice" first.
  const journeyStopsBase = topic.images
    .map((img, idx) => ({ img, idx }))
    .filter(({ idx }) => !(topic.firstFrameIsExample && idx === 0))
    .map(({ img, idx }): JourneyStopBase => {
      const prog = sceneProgress[idx];
      const ready =
        (prog ? sceneReady(prog) : isAdmin) &&
        (isAdmin ||
          ((masteryPassedMap[idx] ?? false) &&
            (contentPassedMap[idx] ?? false)));
      const started = Boolean(prog && prog.attempts > 0);
      return {
        key: idx,
        img,
        idx,
        // Completion outranks mere selection: revisiting a scene you've
        // already finished must still read as done (green ring + star),
        // not fall back to the plain "current" ring just because it's the
        // one open right now. "current" is reserved for the scene you're
        // actively still working toward finishing.
        status: (ready
          ? "done"
          : idx === selectedImageIndex
            ? "current"
            : "upcoming") as JourneyStopStatus,
        thumbnail: img,
        label: (
          <BiLabel zh={`部分 ${idx + 1}`} pinyin={`Bùfen ${idx + 1}`} en={`Scene ${idx + 1}`} />
        ),
        badge: !ready && started ? `${prog!.attempts}×` : undefined,
      };
    });

  const goToScene = (idx: number, img: string) => {
    onImageChange(img);
    onImageSelect(idx);
    currentTranscriptRef.current = "";
    setViewingExample(false);
  };

  // ── Sidebar data: vertical phase list + scene journey + summary node ──
  // Keep implementation phases private. Students only need one short journey
  // to understand: prepare, speak, then feedback.
  const sidebarPhases: SidebarPhase[] = [
    {
      key: "prepare",
      label: <><span>Prepare</span><span className="student-visually-hidden">Overview</span></>,
      icon: "📖",
      status: phase === "overview" || phase === "sorting" || phase === "vocabquiz" ? "active" : "done",
      onClick: enableOverview
        ? () => setPhase("overview")
        : phase !== "overview" && phase !== "sorting" && phase !== "vocabquiz"
          ? () => setPhase(enableSorting ? "sorting" : "practice")
          : undefined,
    },
    {
      key: "speak",
      label: "Speak",
      icon: "🎙️",
      status: phase === "practice" ? "active" : phase === "summary" ? "done" : "upcoming",
      onClick: phase === "summary" ? () => setPhase("practice") : undefined,
    },
    {
      key: "feedback",
      label: "Feedback",
      icon: "📊",
      status: phase === "summary" ? "active" : "upcoming",
    },
  ];

  const practiceReachable = phase === "practice" || phase === "summary";
  const hasExampleFrame =
    Boolean(topic.firstFrameIsExample) && topic.images.length > 1;
  const sidebarJourneyStops: JourneyStop[] = [
    ...(hasExampleFrame
      ? [
          {
            key: "example",
            status: (viewingExample ? "current" : "done") as JourneyStopStatus,
            thumbnail: topic.images[0],
            label: (
              <BiLabel zh="老師示範" pinyin="Lǎoshī shìfàn" en="Teacher example" />
            ),
            badge: "🎯",
            disabled: isBusy,
            onClick: () => {
              setViewingExample(true);
              if (phase !== "practice") setPhase("practice");
            },
          },
        ]
      : []),
    ...journeyStopsBase.map((stop) => ({
      ...stop,
      // While the example view is open no scene is "current" — show the
      // selected scene as a plain stop so the 🎯 ring reads as the place
      // the student is at.
      status: (viewingExample && stop.status === "current"
        ? "upcoming"
        : stop.status) as JourneyStopStatus,
      disabled: isBusy,
      onClick: () => {
        goToScene(stop.idx, stop.img);
        if (phase !== "practice") setPhase("practice");
      },
    })),
  ];

  const summaryStatus: SidebarSummaryStatus =
    phase === "summary"
      ? storySubmitted
        ? "done"
        : "active"
      : allScenesRecorded
        ? "available"
        : "locked";

  return (
    <div className="story-recorder">
      {/* ── Session sidebar: exit + topic name, vertical phase list, the
           scene journey threaded under Practice, raise-hand panel at the
           bottom — replaces the stacked nav panel + horizontal journey +
           page-top help strip. ── */}
      <StorySessionSidebar
        topicName={topic.name}
        onExit={onExit}
        phases={sidebarPhases}
        journeyStops={practiceReachable ? sidebarJourneyStops : undefined}
        summaryStatus={summaryStatus}
        onOpenSummary={() => setPhase("summary")}
        helpPanel={
          helpRequests ? (
            <StudentHelpPanel
              helpRequests={helpRequests}
              onRaiseHand={onRaiseHand}
              compact
            />
          ) : undefined
        }
      />

      <div className="story-session-main">
      {phase === "overview" && (
        <StoryOverviewSection
          topic={topic}
          hasVocabQuiz={hasVocabQuiz}
          speakingLocked={speakingLocked}
          allVocabulary={allVocabulary}
          enableSorting={enableSorting}
          onSelectPhase={setPhase}
        />
      )}

      {phase === "sorting" && (
        <SortingChallenge
          topic={topic}
          speakingLocked={speakingLocked}
          onContinue={setPhase}
        />
      )}

      {phase === "vocabquiz" && (
        <StoryVocabQuiz
          entries={quizEntries}
          onDone={handleVocabQuizDone}
          onComplete={handleVocabQuizComplete}
          storyId={topic.id}
          studentId={studentId}
          studentName={studentName}
          alreadyCompleted={vocabQuizCompleted}
        />
      )}

      {/* ── Teacher example view: opened from the 🎯 stop on the sidebar
           journey, shown in place of the practice stage rather than
           stacked above it. ── */}
      {phase === "practice" && viewingExample && hasExampleFrame && (
            <div className="example-frame-panel">
              <div className="example-frame-label">
                <span className="example-frame-icon">🎯</span>
                <BiLabel zh="老師示範" pinyin="Lǎoshī shìfàn" en="Teacher Model Example" />
              </div>
              <div className="example-frame-body">
                {topic.images[0] && (
                  <img
                    src={topic.images[0]}
                    alt="Teacher example"
                    className="example-frame-image"
                  />
                )}
                <div className="example-frame-content">
                  {topic.prompts?.[0] && (
                    <p className="example-frame-prompt">{topic.prompts[0]}</p>
                  )}
                  {topic.listenAudioUrls?.[0] && (
                    <audio
                      controls
                      src={topic.listenAudioUrls[0]}
                      className="example-frame-audio"
                    />
                  )}
                  {(topic.suggestedAnswers?.[0] ||
                    topic.listenScripts?.[0]) && (
                    <div className="example-frame-script-block">
                      <p className="example-frame-script-label">
                        <BiLabel zh="範例句子" pinyin="Fànlì jùzi" en="Model script" />
                      </p>
                      <p className="example-frame-script" lang="zh-TW">
                        {topic.suggestedAnswers?.[0] ||
                          topic.listenScripts?.[0]}
                      </p>
                    </div>
                  )}
                  {(topic.vocabulary?.[0] ?? []).length > 0 && (
                    <div className="example-frame-vocab">
                      {topic.vocabulary[0].map((w) => (
                        <span key={w} className="vocab-chip">
                          {w}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <footer className="example-frame-footer">
                <AppButton
                  tone="primary"
                  className="btn-scene-step-continue"
                  onClick={() => setViewingExample(false)}
                >
                  <BiLabel
                    zh="回到練習"
                    pinyin="Huí dào liànxí"
                    en="Back to practice"
                  />
                </AppButton>
              </footer>
            </div>
      )}

      {phase === "practice" && !viewingExample && (
        <>
          {/* ── Per-scene practice steps: study → speaking ──
               One continuous practice stage: a numbered stepper header
               fused to the step content below it (same visual language as
               the sidebar's phase list), instead of a floating pill row +
               a disconnected card. Scene navigation and readiness state
               live in the sidebar journey + the stage footer. ── */}
          <section className="practice-stage">
          {(() => {
            const steps: Array<{ key: ScenePracticeStep; label: JSX.Element }> = [
              ...(sceneHasStudyStep(selectedImageIndex)
                ? [{ key: "study" as const, label: <BiLabel k="study_step_tab" /> }]
                : []),
              { key: "speaking" as const, label: <BiLabel k="speaking" /> },
            ];
            const activeIdx = steps.findIndex((s) => s.key === scenePracticeStep);
            return (
              <div
                className="scene-step-tabs"
                role="tablist"
                aria-label="Practice steps"
              >
                {steps.map((step, i) => {
                  const state =
                    i < activeIdx ? "done" : i === activeIdx ? "active" : "upcoming";
                  return (
                    <button
                      key={step.key}
                      type="button"
                      role="tab"
                      aria-selected={scenePracticeStep === step.key}
                      className={`scene-step-tab scene-step-${state}${scenePracticeStep === step.key ? " active" : ""}`}
                      onClick={() => setScenePracticeStep(step.key)}
                    >
                      {state === "done" && (
                        <span className="scene-step-check" aria-hidden="true">✓</span>
                      )}
                      {step.label}
                    </button>
                  );
                })}
              </div>
            );
          })()}

          {/* ── Speaking runs as its own fixed-height app flow (record →
               results, gated Next); Vocabulary/Phrases keep the two-column
               reference workspace. ── */}
          {scenePracticeStep === "speaking" ? (
            <SpeakingFlowCard
              selectedImage={selectedImage}
              selectedImageIndex={selectedPracticeScenePosition}
              totalScenes={totalScenes}
              modelSentence={
                topic.listenScripts?.[selectedImageIndex] ||
                topic.suggestedAnswers?.[selectedImageIndex]
              }
              modelAudioUrl={topic.listenAudioUrls?.[selectedImageIndex]}
              narrativeMode={topic.narrativeMode}
              prog={sceneProgress[selectedImageIndex]}
              praatMetrics={praatMetrics}
              analysisAudioBlob={analysisAudioBlob}
              error={error}
              isRecording={isRecording}
              isBusy={isBusy}
              isTranscribing={isTranscribing}
              isAnalyzing={isAnalyzing}
              recordingDuration={recordingDuration}
              silenceDuration={silenceDuration}
              selectedModel={selectedModel}
              groqAvailable={groqAsrAvailable}
              openaiAvailable={openaiAsrAvailable}
              onSelectedModelChange={(model) => {
                speechModelChosenByStudentRef.current = true;
                setSelectedModel(model);
              }}
              recordingButtonDisabled={recordingButtonDisabled}
              onPrimaryRecordingAction={handlePrimaryRecordingAction}
              onSubmitVoiceFile={handleSubmitVoiceFile}
              pendingUploadName={pendingVoiceFile?.name}
              pendingUploadUrl={pendingVoiceFileUrl}
              onAnalyzePendingUpload={() => void analyzePendingVoiceFile()}
              onClearPendingUpload={clearPendingVoiceFile}
              masteryPassed={
                isAdmin || (masteryPassedMap[selectedImageIndex] ?? false)
              }
              contentPassed={
                isAdmin || (contentPassedMap[selectedImageIndex] ?? false)
              }
              sceneReadyOverride={
                isAdmin || (pilotSceneReadyOverrideMap[selectedImageIndex] ?? false)
              }
              clearedWords={clearedWordsMap[selectedImageIndex] ?? []}
              onWordDrillPass={handleWordDrillPass}
              onSelfEvalSubmit={handleSelfEvalSubmit}
              hasNextScene={nextPracticeSceneIndex !== undefined}
              onNextScene={() => {
                if (nextPracticeSceneIndex !== undefined) {
                  goToScene(nextPracticeSceneIndex, topic.images[nextPracticeSceneIndex]);
                }
              }}
              onViewSummary={() => setPhase("summary")}
            />
          ) : (
          <div className={`practice-workspace${scenePracticeStep === "study" ? " practice-workspace-study" : ""}`}>
            {/* Scene reference rail — ~1/5–1/4 of the width, big enough to
                actually read the scene (including any speech-bubble text),
                shared as-is with Speaking so the ratio never drifts
                between practice steps. */}
            <div className="practice-scene-col">
              <div className="practice-scene-image">
                <img
                  src={selectedImage}
                  alt={`Scene ${selectedImageIndex + 1}`}
                />
              </div>
              <span className="practice-scene-chip">
                <BiLabel
                  zh={`部分 ${selectedImageIndex + 1}/${topic.images.length}`}
                  en={`Scene ${selectedImageIndex + 1} of ${topic.images.length}`}
                />
              </span>
            </div>

            <div className="practice-scene-main">
            {scenePracticeStep === "study" && (
              <div className="practice-content practice-study-ref">
                <div className="practice-content-header">
                  <span aria-hidden="true">📖</span>
                  <div>
                    <h3>
                      <BiLabel k="study_step_tab" />
                    </h3>
                    <p>
                      <BiText k="study_step_action_copy" />
                    </p>
                  </div>
                </div>

                {selectedVocabulary.length > 0 && (
                  <div className="practice-study-block practice-vocab-ref">
                    <p className="block-label practice-vocab-heading">
                      <BiLabel k="scene_vocabulary" />
                      {praatMetrics && (
                        <span className="vocab-check-hint">
                          {" "}
                          — <BiLabel k="check_which_words_you_used" />
                        </span>
                      )}
                    </p>
                    <div
                      className="scene-vocab-table scene-vocab-table-practice"
                      role="table"
                      aria-label="Scene vocabulary"
                    >
                      {selectedVocabulary.map((w, wi) => {
                        // Prefer backend phonetic-match result; fall back to
                        // character search. `effectiveVocabCoverage` already
                        // substitutes a transcript-based used/missing when the
                        // backend's judgment was flagged unreliable.
                        const aiVC = effectiveVocabCoverage;
                        let used: boolean | null = null;
                        if (aiVC) {
                          if (aiVC.used?.includes(w)) used = true;
                          else if (aiVC.missing?.includes(w)) used = false;
                        } else if (praatMetrics?.transcription) {
                          used = praatMetrics.transcription.includes(w);
                        }
                        // Preserve legacy English-key topics, while never
                        // allowing their stored pinyin to override the
                        // canonical backend reading for Chinese text.
                        const py =
                          toPinyin(w) ||
                          (!/[\u4e00-\u9fff]/u.test(w)
                            ? topic.vocabularyPinyin?.[selectedImageIndex]?.[
                                wi
                              ] || ""
                            : "");
                        const pos =
                          topic.vocabularyPos?.[selectedImageIndex]?.[wi];
                        const translation =
                          topic.vocabularyTranslation?.[selectedImageIndex]?.[
                            wi
                          ];
                        return (
                          <div
                            key={w}
                            role="row"
                            className={`scene-vocab-row scene-vocab-row-practice ${used === true ? "scene-vocab-used" : used === false ? "scene-vocab-missed" : ""}`}
                            title={
                              used === true
                                ? "你使用了這個生詞 ✓ You used this word"
                                : used === false
                                  ? "試著加入這個生詞 Try to include this word"
                                  : undefined
                            }
                          >
                            <span
                              className="scene-vocab-status"
                              role="cell"
                              aria-hidden="true"
                            >
                              {used === true && "✓"}
                              {used === false && "✗"}
                            </span>
                            <span
                              className="scene-vocab-cell scene-vocab-hanzi"
                              role="cell"
                            >
                              {w}
                            </span>
                            <span
                              className="scene-vocab-cell scene-vocab-pinyin"
                              role="cell"
                            >
                              {py}
                            </span>
                            <span
                              className="scene-vocab-cell scene-vocab-pos"
                              role="cell"
                            >
                              {pos}
                            </span>
                            <span
                              className="scene-vocab-cell scene-vocab-meaning"
                              role="cell"
                            >
                              {translation}
                            </span>
                            <ScenePracticeWord
                              word={w}
                              audioUrl={
                                topic.vocabularyAudioUrls?.[selectedImageIndex]?.[wi] ?? undefined
                              }
                            />
                          </div>
                        );
                      })}
                    </div>
                    {effectiveVocabCoverage && (
                      <p className="vocab-coverage-line">
                        {(() => {
                          const vc = effectiveVocabCoverage;
                          const usedList = vc.used ?? [];
                          const missedList = vc.missing ?? [];
                          if (missedList.length === 0)
                            return (
                              <BiLabel k="all_vocabulary_words_used_excellent" />
                            );
                          if (usedList.length === 0)
                            return (
                              <BiLabel
                                zh={`試著加入：${missedList.slice(0, 3).join("、")}`}
                                pinyin={`Shìzhe jiārù: ${missedList.slice(0, 3).join("、")}`}
                                en={`Try to include: ${missedList.slice(0, 3).join("、")}`}
                              />
                            );
                          return (
                            <BiLabel
                              zh={`已用 ${usedList.length}/${selectedVocabulary.length}。試著加入：${missedList.slice(0, 2).join("、")}`}
                              pinyin={`Yǐ yòng ${usedList.length}/${selectedVocabulary.length}. Shìzhe jiārù: ${missedList.slice(0, 2).join("、")}`}
                              en={`Used ${usedList.length}/${selectedVocabulary.length}. Try adding: ${missedList.slice(0, 2).join("、")}`}
                            />
                          );
                        })()}
                      </p>
                    )}
                  </div>
                )}

                {(topic.phrases?.[selectedImageIndex] || []).length > 0 && (
                  <div className="practice-study-block practice-phrases-hint practice-phrases-hint-full">
                    <p className="block-label practice-phrases-label">
                      <BiLabel k="phrases_to_use" />
                    </p>
                    <div
                      className="practice-phrases-list"
                      role="table"
                      aria-label="Scene phrases"
                    >
                      {topic.phrases![selectedImageIndex].map((phrase, pi) => (
                        <div className="practice-phrase-row" role="row" key={phrase}>
                          <span className="practice-phrase-text" role="cell" lang="zh-Hant">
                            {phrase}
                          </span>
                          {topic.phrasesTranslation?.[selectedImageIndex]?.[pi] && (
                            <span className="practice-phrase-translation" role="cell">
                              {topic.phrasesTranslation[selectedImageIndex][pi]}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Footer action bar — same shape as SpeakingFlowCard's results
                footer, so both practice steps end the same way. The scene's
                readiness status lives here too (start hint / complete /
                points-to-go), instead of banners stacked above the stage —
                Speaking carries its own verdict, so this only renders on
                the Study step. */}
            <footer className="practice-footer">
              {(() => {
                const prog = sceneProgress[selectedImageIndex];
                const ready =
                  isAdmin ||
                  (Boolean(prog) &&
                    sceneReady(prog) &&
                    (masteryPassedMap[selectedImageIndex] ?? false) &&
                    (contentPassedMap[selectedImageIndex] ?? false));
                const nextIdx = nextPracticeSceneIndex;
                const hasNext = nextIdx !== undefined;
                let status: JSX.Element | null;
                if (!prog || prog.attempts === 0) {
                  status = null;
                } else if (ready) {
                  status = (
                    <span className="practice-footer-ready">
                      <span aria-hidden="true">✓ </span>
                      {hasNext ? (
                        <BiLabel
                          zh={`部分 ${selectedImageIndex + 1} 完成 · 最佳聲調 ${prog.bestTone}%`}
                          pinyin={`Bùfen ${selectedImageIndex + 1} wánchéng · zuì jiā shēngdiào ${prog.bestTone}%`}
                          en={`Scene ${selectedImageIndex + 1} complete · best tone ${prog.bestTone}%`}
                        />
                      ) : (
                        <BiLabel k="all_scenes_practiced" />
                      )}
                    </span>
                  );
                } else {
                  const charCount = (praatMetrics?.transcription || "").replace(
                    /[^一-鿿]/g,
                    "",
                  ).length;
                  const threshold = charCount <= 6 ? 70 : 65;
                  const best = charCount <= 6 ? prog.bestTone : prog.bestFluency;
                  const gap = threshold - best;
                  status = (
                    <span className="practice-footer-hint">
                      {gap > 0 ? (
                        <BiLabel
                          zh={`還需要 ${gap} 分才能打開下一個部分 — 繼續加油。`}
                          pinyin={`Hái xūyào ${gap} fēn cái néng dǎkāi xià yí ge bùfen — jìxù jiāyóu.`}
                          en={`${gap} more points needed to unlock the next scene — keep going.`}
                        />
                      ) : (
                        <BiLabel k="keep_practicing_try_to_make_the_tone_sha" />
                      )}
                    </span>
                  );
                }
                return (
                  <>
                    <div className="practice-footer-status">{status}</div>
                    <div className="practice-footer-actions">
                      <AppButton
                        tone="primary"
                        className="btn-scene-step-continue"
                        onClick={() => setScenePracticeStep("speaking")}
                      >
                        <BiLabel k="continue_to_speaking" />
                      </AppButton>
                      {ready && hasNext && (
                        <AppButton
                          tone="secondary"
                          className="scene-next-btn"
                          onClick={() => goToScene(nextIdx!, topic.images[nextIdx!])}
                        >
                          <BiLabel k="next_scene" />
                        </AppButton>
                      )}
                      {ready && !hasNext && (
                        <AppButton
                          tone="secondary"
                          className="scene-next-btn"
                          onClick={() => setPhase("summary")}
                        >
                          <BiLabel
                            zh="查看總結"
                            pinyin="Chákàn zǒngjié"
                            en="View summary"
                          />
                        </AppButton>
                      )}
                    </div>
                  </>
                );
              })()}
            </footer>
            </div>
          </div>
          )}
          </section>
        </>
      )}

      {/* ── Journey summary: reached once every scene is recorded, instead
           of the submit panel repeating on every scene's speaking step ── */}
      {phase === "summary" && (
        <StorySummarySection
          journeyStopsBase={journeyStopsBase}
          storySubmitted={storySubmitted}
          storyFeedbackResult={storyFeedbackResult}
          sceneRecordings={sceneRecordings}
          submitError={submitError}
          allScenesRecorded={allScenesRecorded}
          completedSceneCount={completedSceneCount}
          totalScenes={totalScenes}
          practiceSceneIndices={practiceSceneIndices}
          onSubmitStory={handleSubmitStory}
          onJourneyStopClick={(idx, img) => {
            goToScene(idx, img);
            setPhase("practice");
          }}
        />
      )}
      </div>
    </div>
  );
}

