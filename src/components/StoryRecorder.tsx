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
  updateVocabularyCloze,
  updateVocabularyDistractors,
  updateVocabularyLookalike,
  updateVocabularySynonym,
  type HelpRequest,
  type SceneSubmission,
  type StoryFeedback,
  type VocabularyClozeUpdate,
  type VocabularyDistractorUpdate,
  type VocabularyLookalikeUpdate,
  type VocabularySynonymUpdate,
} from "../services/database";
import ScenePracticeWord from "./ScenePracticeWord";
import StoryVocabQuiz, {
  collectQuizEntries,
  type VocabQuizSummary,
} from "./StoryVocabQuiz";
import { type JourneyStop, type JourneyStopStatus } from "./JourneyPath";
import { toPinyin } from "../utils/pinyin";
import { markStoryLevelSubmitted } from "../utils/storyLevelProgress";
import type { CustomTeacherStory, StoryDifficultyLevel } from "../utils/teacherStories";
import { convertBlobToWav } from "../utils/audio";
import {
  sceneReady,
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

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

// Mirrors the backend's MAX_VOCAB_DISTRACTORS_PER_WORD cap — checked
// client-side so a story where every word already has a full pool skips the
// AI call entirely instead of generating distractors the backend would just
// discard.
const MAX_VOCAB_DISTRACTORS_PER_WORD = 8;

export function vocabTooltip(
  pos?: string,
  translation?: string,
): string | undefined {
  if (pos && translation) return `(${pos}) ${translation}`;
  if (pos) return `(${pos})`;
  if (translation) return translation;
  return undefined;
}

export type SpeechModel = "webspeech" | "ctwhisper" | "groq" | "vibevoice";

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
  vocabularyLookalike?: Record<number, string[][]>;
  vocabularyCloze?: Record<number, Array<{ sentence: string; distractors: string[] }[]>>;
  vocabularySynonym?: Record<number, Array<{ synonym: string; distractors: string[] }[]>>;
  suggestedAnswers?: Record<number, string>;
  listenAudioUrls?: Record<number, string>;
  listenScripts?: Record<number, string>;
  linear?: boolean;
  lessonNumber?: number | null;
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

// Mirrors the backend's MAX_VOCAB_LOOKALIKE_PER_WORD cap.
const MAX_VOCAB_LOOKALIKE_PER_WORD = 6;

export interface LookalikeGrowthCandidate {
  frameIndex: number;
  wordIndex: number;
  word: string;
  translation: string;
  context?: string;
  existing: string[];
}

/** Pure planning step for growVocabularyLookalikePool: picks the words in a
 * story whose persisted look-alike pool hasn't reached the cap yet, pairing
 * each with its existing pool (sent as the AI's "avoid" list). Mirrors
 * planDistractorGrowth above. */
export function planLookalikeGrowth(
  topic: Pick<
    Topic,
    "images" | "vocabulary" | "vocabularyTranslation" | "vocabularyLookalike" | "suggestedAnswers"
  >,
): LookalikeGrowthCandidate[] {
  const candidates: LookalikeGrowthCandidate[] = [];
  topic.images.forEach((_, si) => {
    const sceneSuggestedAnswer = topic.suggestedAnswers?.[si];
    (topic.vocabulary[si] || []).forEach((word, i) => {
      const translation = topic.vocabularyTranslation?.[si]?.[i];
      if (!translation) return;
      const existing = topic.vocabularyLookalike?.[si]?.[i] ?? [];
      if (existing.length >= MAX_VOCAB_LOOKALIKE_PER_WORD) return;
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

/** Pairs each growth candidate with the AI-generated look-alikes for its
 * word (matched by word text), dropping any candidate the AI returned
 * nothing for. Mirrors buildDistractorPatchUpdates above. */
export function buildLookalikePatchUpdates(
  candidates: LookalikeGrowthCandidate[],
  results: Array<{ word: string; lookalikes: string[] }>,
): VocabularyLookalikeUpdate[] {
  const byWord = new Map(results.map((r) => [r.word, r.lookalikes]));
  return candidates
    .map((candidate) => ({
      frameIndex: candidate.frameIndex,
      wordIndex: candidate.wordIndex,
      lookalikes: byWord.get(candidate.word) ?? [],
    }))
    .filter((update) => update.lookalikes.length > 0);
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
}

export interface WordProsody {
  token: string;
  index: number;
  start_time: number;
  end_time: number;
  pitch_contour: Array<[number, number]>;
  reference_contour?: Array<[number, number]>;
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
  // Per-syllable directional scores + verdicts. The word-level scores
  // average across syllables, which lets a clean syllable hide a
  // wrong-direction one — `passed` is the MIN-rule verdict (every syllable
  // must clear the backend's pass bar). Absent/null for non-Chinese tokens.
  syllables?: WordProsodySyllable[];
  passed?: boolean | null;
}

export interface WordProsodySyllable {
  char: string;
  tone: number;
  score: number;
  passed: boolean;
}

interface LanguageFeedback {
  provider: string;
  vocabulary_coverage: {
    score: number;
    used: string[];
    missing: string[];
    feedback: string;
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
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<SpeechModel>("webspeech");
  const [aiProvider, setAiProvider] = useState<string>("");
  const [silenceDuration, setSilenceDuration] = useState(0);
  const [recordingDuration, setRecordingDuration] = useState(0);

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
  const [clearedWordsMap, setClearedWordsMap] = useState<
    Record<number, string[]>
  >({});
  const handleWordDrillPass = useCallback(
    (token: string) => {
      setClearedWordsMap((prev) => {
        const current = prev[selectedImageIndex] ?? [];
        if (current.includes(token)) return prev;
        return { ...prev, [selectedImageIndex]: [...current, token] };
      });
    },
    [selectedImageIndex],
  );
  const [submittedAudioName, setSubmittedAudioName] = useState("");
  // Completed scene snapshots for story submission
  const [sceneRecordings, setSceneRecordings] = useState<
    Record<number, SceneSubmission>
  >({});
  const [storySubmitted, setStorySubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [storyFeedbackResult, setStoryFeedbackResult] = useState<{
    concatenatedAudioUrl?: string | null;
    storyFeedback?: StoryFeedback | null;
  } | null>(null);

  // Every glossed word across every scene, deduped — the pool the
  // pre-practice vocabulary quiz draws its questions from. Even a single
  // translated word is enough for a real question: buildQuizQuestions pads
  // out missing distractors with generic filler words. A word only
  // qualifies if it also appears in its scene's suggested-answer sentence
  // (when one exists) — confirms it's used in real context, not just an
  // isolated flashcard pair.
  const quizEntries = useMemo(() => {
    const words: string[] = [];
    const translations: Array<string | undefined> = [];
    const suggestedAnswers: Array<string | undefined> = [];
    const aiDistractors: Array<string[] | undefined> = [];
    const pinyins: Array<string | undefined> = [];
    const aiCloze: Array<Array<{ sentence: string; distractors: string[] }> | undefined> = [];
    const partsOfSpeech: Array<string | undefined> = [];
    const aiSynonyms: Array<Array<{ synonym: string; distractors: string[] }> | undefined> = [];
    const aiLookalikes: Array<string[] | undefined> = [];
    topic.images.forEach((_, si) => {
      const sceneSuggestedAnswer = topic.suggestedAnswers?.[si];
      (topic.vocabulary[si] || []).forEach((word, i) => {
        words.push(word);
        translations.push(topic.vocabularyTranslation?.[si]?.[i]);
        suggestedAnswers.push(sceneSuggestedAnswer);
        aiDistractors.push(topic.vocabularyDistractors?.[si]?.[i]);
        pinyins.push(topic.vocabularyPinyin?.[si]?.[i]);
        aiCloze.push(topic.vocabularyCloze?.[si]?.[i]);
        partsOfSpeech.push(topic.vocabularyPos?.[si]?.[i]);
        aiSynonyms.push(topic.vocabularySynonym?.[si]?.[i]);
        aiLookalikes.push(topic.vocabularyLookalike?.[si]?.[i]);
      });
    });
    return collectQuizEntries(
      words,
      translations,
      suggestedAnswers,
      aiDistractors,
      pinyins,
      aiCloze,
      partsOfSpeech,
      aiSynonyms,
      aiLookalikes,
    );
  }, [topic]);
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
  const speakingLocked = hasVocabQuiz && !vocabQuizCompleted;

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
    growVocabularyLookalikePool().catch((error) => {
      console.warn("Failed to grow vocabulary look-alike pool:", error);
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

    const response = await fetch(`${BACKEND_URL}/api/vocab-quiz-distractors`, {
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
  // tier-3 look-alike (face-confusion) trap pool instead.
  const growVocabularyLookalikePool = async () => {
    const candidates = planLookalikeGrowth(topic);
    if (candidates.length === 0) return;

    const response = await fetch(`${BACKEND_URL}/api/vocab-quiz-lookalike`, {
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
    if (!response.ok) throw new Error("Could not generate new look-alike traps.");

    const { results } = (await response.json()) as {
      results: { word: string; lookalikes: string[] }[];
    };
    const updates = buildLookalikePatchUpdates(candidates, results);
    if (updates.length === 0) return;

    await updateVocabularyLookalike(persistedStoryId, updates);
  };

  // Same growth pattern as growVocabularyDistractorPool above, for the
  // fill-in-the-blank cloze question pool instead.
  const growVocabularyClozePool = async () => {
    const candidates = planClozeGrowth(topic);
    if (candidates.length === 0) return;

    const response = await fetch(`${BACKEND_URL}/api/vocab-quiz-cloze`, {
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

    const response = await fetch(`${BACKEND_URL}/api/vocab-quiz-synonym`, {
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
    const stillLocked = hasVocabQuiz && !completed;
    setPhase(
      enableOverview
        ? "overview"
        : enableSorting
          ? "sorting"
          : stillLocked
            ? "vocabquiz"
            : "practice",
    );
  }, [topic.id, topic.images, enableSorting, enableOverview, hasVocabQuiz]);

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
        const defaultProvider = (groqAvailable ? "groq" : data.default) || "";
        setAiProvider((prev) => prev || defaultProvider);
        // Sync speech source: if Groq is the default AI provider, use Groq Whisper
        // for transcription too so ASR and feedback both come from the same engine.
        if (groqAvailable) {
          setSelectedModel((prev) => (prev === "webspeech" ? "groq" : prev));
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
      setSubmittedAudioName("");
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
        setRecordingDuration(
          Math.floor((Date.now() - recordingStartRef.current) / 1000),
        );
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
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
    try {
      const backendUrl = getBackendUrl();
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
      await analyzeSpeechAudio(wavBlob, transcript);
    } catch (err) {
      setError(
        formatBackendError(err, BACKEND_URL || "the configured backend"),
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
  ) => {
    setIsAnalyzing(true);
    try {
      const backendUrl = getBackendUrl();
      const wavBlob = await convertBlobToWav(audioBlob);
      const formData = new FormData();
      formData.append("file", wavBlob, "speech.wav");
      const analysisText = transcription.trim();
      formData.append("transcription", analysisText);
      if (asrModel) {
        formData.append("asr_model", asrModel);
      }
      // Scene context for smarter feedback
      const sceneVocab = (topic.vocabulary[selectedImageIndex] || []).join(
        ", ",
      );
      const scenePrompt = topic.prompts?.[selectedImageIndex] || topic.name;
      formData.append("scene_vocabulary", sceneVocab);
      formData.append("scene_prompt", scenePrompt);
      if (selectedImage) {
        formData.append("scene_image_url", selectedImage);
      }
      if (aiProvider) {
        formData.append("ai_provider", aiProvider);
      }
      const scenePhrases = topic.phrases?.[selectedImageIndex];
      if (scenePhrases && scenePhrases.length > 0) {
        formData.append("scene_phrases", scenePhrases.join("; "));
      }
      const sceneSuggestedAnswer = topic.suggestedAnswers?.[selectedImageIndex];
      if (sceneSuggestedAnswer) {
        formData.append("scene_suggested_answer", sceneSuggestedAnswer);
      }
      formData.append(
        "scene_attempt_number",
        String(attemptHistory.length + 1),
      );

      const response = await fetch(`${backendUrl}/api/analyze`, {
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
      setAttemptHistory((prev) => [
        ...prev,
        {
          tone: Math.round(metrics.tone_accuracy),
          fluency: Math.round(metrics.fluency_score),
          attempt: prev.length + 1,
        },
      ]);
      setSceneProgress((prev) => {
        const curr = prev[selectedImageIndex] ?? {
          attempts: 0,
          bestTone: 0,
          bestFluency: 0,
        };
        return {
          ...prev,
          [selectedImageIndex]: {
            attempts: curr.attempts + 1,
            bestTone: Math.max(
              curr.bestTone,
              Math.round(metrics.tone_accuracy),
            ),
            bestFluency: Math.max(
              curr.bestFluency,
              Math.round(metrics.fluency_score),
            ),
          },
        };
      });
      // Mastery gate verdict for this full-sentence attempt. A fresh
      // recording re-judges every word, so the per-word drill clearances
      // from the previous attempt reset alongside it.
      setMasteryPassedMap((prev) => ({
        ...prev,
        [selectedImageIndex]: prosodyGatePassed(metrics.word_prosody),
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
      setSceneRecordings((prev) => {
        const existing = prev[selectedImageIndex];
        if (!existing || newSnap.vocabScore >= existing.vocabScore) {
          return { ...prev, [selectedImageIndex]: newSnap };
        }
        return prev;
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
      }
    } catch (err) {
      setError(
        formatBackendError(err, BACKEND_URL || "the configured backend"),
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
    setSubmittedAudioName(file.name);
    currentTranscriptRef.current = "";
    recordingStartRef.current = Date.now();
    setRecordingDuration(0);

    const uploadModel = selectedModel === "webspeech" ? "groq" : selectedModel;
    await analyzeSpeechAudio(file, "", uploadModel, uploadModel);
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

  const handlePrimaryRecordingAction = () => {
    if (isRecording) {
      stopRecording();
      return;
    }

    startRecording();
  };

  const totalScenes = topic.images.length;
  const completedSceneCount = Object.keys(sceneRecordings).length;
  // Submission needs every scene recorded AND pronunciation-mastered — a
  // scene whose latest full-sentence attempt still has failing words keeps
  // the story locked even if an earlier snapshot was saved for it.
  const allScenesRecorded =
    completedSceneCount >= totalScenes &&
    Object.keys(sceneRecordings).every(
      (key) => masteryPassedMap[Number(key)] ?? false,
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

  const phaseOrder = PHASES.map((p) => p.key);
  // "summary" isn't a phase-nav tab (it's only reachable after finishing
  // every scene) — treat it as past the last tab so the nav bar shows
  // every real phase as done rather than falling back to "upcoming".
  const currentPhaseIdx =
    phase === "summary"
      ? phaseOrder.length
      : phaseOrder.indexOf(phase as (typeof phaseOrder)[number]);

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
        (prog ? sceneReady(prog) : false) && (masteryPassedMap[idx] ?? false);
      const started = Boolean(prog && prog.attempts > 0);
      return {
        key: idx,
        img,
        idx,
        status: (idx === selectedImageIndex
          ? "current"
          : ready
            ? "done"
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
  const sidebarPhases: SidebarPhase[] = PHASES.map((p, i) => {
    const status =
      i < currentPhaseIdx ? "done" : i === currentPhaseIdx ? "active" : "upcoming";
    return {
      key: p.key,
      label: p.label,
      icon: p.icon,
      status,
      // Same jump-back rule as the old horizontal stepper: only completed
      // phases are clickable.
      onClick: status === "done" ? () => setPhase(p.key) : undefined,
    };
  });

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
                <button
                  type="button"
                  className="btn-scene-step-continue"
                  onClick={() => setViewingExample(false)}
                >
                  <BiLabel
                    zh="回到練習"
                    pinyin="Huí dào liànxí"
                    en="Back to practice"
                  />
                </button>
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
              selectedImageIndex={selectedImageIndex}
              totalScenes={topic.images.length}
              modelSentence={topic.suggestedAnswers?.[selectedImageIndex]}
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
              submittedAudioName={submittedAudioName}
              selectedModel={selectedModel}
              recordingButtonDisabled={recordingButtonDisabled}
              onPrimaryRecordingAction={handlePrimaryRecordingAction}
              onSubmitVoiceFile={handleSubmitVoiceFile}
              masteryPassed={masteryPassedMap[selectedImageIndex] ?? false}
              clearedWords={clearedWordsMap[selectedImageIndex] ?? []}
              onWordDrillPass={handleWordDrillPass}
              hasNextScene={selectedImageIndex + 1 < topic.images.length}
              onNextScene={() => {
                const nextIdx = selectedImageIndex + 1;
                goToScene(nextIdx, topic.images[nextIdx]);
              }}
              onViewSummary={() => setPhase("summary")}
            />
          ) : (
          <div className="practice-workspace">
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
                        // Prefer backend phonetic-match result; fall back to character search
                        const aiVC =
                          praatMetrics?.ai_feedback?.vocabulary_coverage;
                        let used: boolean | null = null;
                        if (aiVC) {
                          if (aiVC.used?.includes(w)) used = true;
                          else if (aiVC.missing?.includes(w)) used = false;
                        } else if (praatMetrics?.transcription) {
                          used = praatMetrics.transcription.includes(w);
                        }
                        const py =
                          topic.vocabularyPinyin?.[selectedImageIndex]?.[wi] ||
                          toPinyin(w);
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
                            <ScenePracticeWord word={w} pinyin={py} />
                          </div>
                        );
                      })}
                    </div>
                    {praatMetrics?.ai_feedback?.vocabulary_coverage && (
                      <p className="vocab-coverage-line">
                        {(() => {
                          const vc =
                            praatMetrics.ai_feedback!.vocabulary_coverage!;
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
                  Boolean(prog) &&
                  sceneReady(prog) &&
                  (masteryPassedMap[selectedImageIndex] ?? false);
                const nextIdx = selectedImageIndex + 1;
                const hasNext = nextIdx < topic.images.length;
                let status: JSX.Element;
                if (!prog || prog.attempts === 0) {
                  status = (
                    <span className="practice-footer-hint">
                      <span aria-hidden="true">👀 </span>
                      <BiLabel
                        zh="新的部分：先看看生詞，然後開始錄音。"
                        pinyin="Xīn de bùfen: xiān kànkan shēngcí, ránhòu kāishǐ lùyīn."
                        en="New scene: read the words first, then start recording."
                      />
                    </span>
                  );
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
                      <button
                        type="button"
                        className="btn-scene-step-continue"
                        onClick={() => setScenePracticeStep("speaking")}
                      >
                        <BiLabel k="continue_to_speaking" />
                      </button>
                      {ready && hasNext && (
                        <button
                          type="button"
                          className="scene-next-btn"
                          onClick={() => goToScene(nextIdx, topic.images[nextIdx])}
                        >
                          <BiLabel k="next_scene" />
                        </button>
                      )}
                      {ready && !hasNext && (
                        <button
                          type="button"
                          className="scene-next-btn"
                          onClick={() => setPhase("summary")}
                        >
                          <BiLabel
                            zh="查看總結"
                            pinyin="Chákàn zǒngjié"
                            en="View summary"
                          />
                        </button>
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
          topic={topic}
          journeyStopsBase={journeyStopsBase}
          storySubmitted={storySubmitted}
          storyFeedbackResult={storyFeedbackResult}
          sceneRecordings={sceneRecordings}
          submitError={submitError}
          allScenesRecorded={allScenesRecorded}
          completedSceneCount={completedSceneCount}
          totalScenes={totalScenes}
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

