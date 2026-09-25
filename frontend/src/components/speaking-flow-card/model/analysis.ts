import {
  failedProsodyWords,
  isContentAccepted,
  weakToneGuideItems,
} from "../../../utils/storyRecorderFeedback";
import {
  scoreScriptChunks,
  scriptMismatchTokens,
  splitScriptIntoChunks,
  splitTeacherScriptIntoPhrases,
} from "@entities/speech";
import { assessVoiceFeedbackReliability } from "@entities/speech";
import type { PraatMetrics } from "../../story-recorder/StoryRecorder";
import { buildPracticeTargets, type PracticeTarget, type ResultsStep } from "./practiceTargets";

export interface SpeakingResultAnalysisInput {
  modelSentence?: string;
  praatMetrics: PraatMetrics;
  /** Scene unlocked: score/attempts plus content and pronunciation gates. */
  ready: boolean;
  selectedImageIndex: number;
}

export type SpeakingResultVerdict = "meaning" | "vocab" | "pronounce" | "join" | "ready";

type LanguageFeedback = NonNullable<PraatMetrics["ai_feedback"]>;

/** Everything about a submitted attempt that presentation needs, decided in
 * one place instead of recomputed inline inside the results component. Pure
 * function of the attempt's metrics — carries no local UI state (self-eval
 * answer, cleared-phrase progress, drill focus), which the component still
 * owns because it only exists across re-renders of the same attempt. */
export interface SpeakingResultAnalysis {
  accepted: boolean;
  targetScript: string;
  hasTargetScript: boolean;
  recognizedText: string;
  missing: string[];
  scriptMismatches: string[];
  scriptChunks: string[];
  teacherPhraseChunks: string[];
  isChunked: boolean;
  chunkScores: ReturnType<typeof scoreScriptChunks>;
  failedChunks: ReturnType<typeof scoreScriptChunks>;
  weakItems: ReturnType<typeof weakToneGuideItems>;
  pronunciationMastery: PraatMetrics["pronunciation_mastery"];
  masteryCounts: { passed: number; total: number } | undefined;
  contentAccuracy: LanguageFeedback["content_accuracy"];
  corrective: LanguageFeedback["corrective_feedback"];
  meaningJudged: boolean;
  feedbackReliability: ReturnType<typeof assessVoiceFeedbackReliability>;
  failedWords: ReturnType<typeof failedProsodyWords>;
  contentMatchVerified: boolean;
  contentNeedsRetry: boolean;
  contentMismatchChunks: ReturnType<typeof scoreScriptChunks>;
  hasChunkMismatch: boolean;
  effectiveScriptMismatches: string[];
  legacyPracticeWords: ReturnType<typeof failedProsodyWords>;
  hasScriptMismatch: boolean;
  needsPhrasePractice: boolean;
  phrasePracticeItems: string[];
  practicePartLabels: string[];
  practiceTargets: PracticeTarget[];
  practicePartCount: number;
  verdict: SpeakingResultVerdict;
  showCorrective: boolean;
  hasFix: boolean;
  hasPhrasePractice: boolean;
  hasPractice: boolean;
  steps: ResultsStep[];
}

export function analyzeSpeakingResult({
  modelSentence,
  praatMetrics,
  ready,
  selectedImageIndex: _selectedImageIndex,
}: SpeakingResultAnalysisInput): SpeakingResultAnalysis {
  const ai = praatMetrics.ai_feedback;
  const targetScript = modelSentence ?? "";
  const hasTargetScript = Boolean(targetScript.trim());
  const accepted = isContentAccepted(praatMetrics);
  const vocabCoverage = ai?.vocabulary_coverage;
  const missing = vocabCoverage?.missing ?? [];
  const recognizedText =
    praatMetrics.recognized_text ??
    (hasTargetScript && praatMetrics.content_match === null ? "" : praatMetrics.transcription ?? "");

  const scriptMismatches = scriptMismatchTokens(targetScript, recognizedText);
  const scriptChunks = splitScriptIntoChunks(targetScript);
  const teacherPhraseChunks = splitTeacherScriptIntoPhrases(targetScript);
  const isChunked = scriptChunks.length > 1;
  const chunkScores = isChunked
    ? scoreScriptChunks(targetScript, recognizedText, praatMetrics.word_prosody)
    : [];
  const failedChunks = chunkScores.filter((chunk) => !chunk.passed);
  const weakItems = weakToneGuideItems(praatMetrics.word_prosody || []);
  const pronunciationMastery = praatMetrics.pronunciation_mastery;
  const masteryCounts =
    pronunciationMastery &&
    typeof pronunciationMastery.passed_syllables === "number" &&
    typeof pronunciationMastery.total_syllables === "number"
      ? { passed: pronunciationMastery.passed_syllables, total: pronunciationMastery.total_syllables }
      : undefined;
  const contentAccuracy = ai?.content_accuracy;
  const corrective = ai?.corrective_feedback;
  const meaningJudged = Boolean(contentAccuracy?.judged);
  const feedbackReliability = assessVoiceFeedbackReliability({
    feedbackQuality: praatMetrics.feedback_quality,
    contentJudged: meaningJudged,
    pitchContour: praatMetrics.pitch_contour,
    wordProsody: praatMetrics.word_prosody,
    transcription: recognizedText,
  });
  const failedWords = failedProsodyWords(praatMetrics.word_prosody);
  const contentMatchVerified = praatMetrics.content_match === true;
  const contentNeedsRetry = hasTargetScript && !contentMatchVerified;
  const contentMismatchChunks = contentMatchVerified
    ? []
    : failedChunks.filter((chunk) => chunk.mismatch.length > 0);
  const hasChunkMismatch = isChunked && contentMismatchChunks.length > 0;
  const effectiveScriptMismatches = contentMatchVerified ? [] : scriptMismatches;
  const legacyPracticeWords = [...failedWords].sort(
    (a, b) => (a.shape_accuracy ?? a.tone_accuracy ?? 0) - (b.shape_accuracy ?? b.tone_accuracy ?? 0),
  );
  const hasScriptMismatch =
    contentNeedsRetry || (isChunked ? hasChunkMismatch : effectiveScriptMismatches.length > 0);
  const needsPhrasePractice =
    hasScriptMismatch || ((!accepted || missing.length > 0) && scriptChunks.length > 0);
  const phrasePracticeItems = needsPhrasePractice
    ? isChunked
      ? contentMismatchChunks.length > 0
        ? contentMismatchChunks.map((chunk) => chunk.text)
        : (() => {
            const vocabChunks = scriptChunks.filter((chunk) => missing.some((word) => chunk.includes(word)));
            return vocabChunks.length > 0 ? vocabChunks : scriptChunks;
          })()
      : scriptChunks
    : [];
  const practicePartLabels = pronunciationMastery
    ? pronunciationMastery.practice_parts ??
      Array.from(
        new Set([
          ...(pronunciationMastery.failed_words ?? []),
          ...(pronunciationMastery.missing_target_units ?? []),
        ]),
      )
    : legacyPracticeWords.map((word) => word.token);
  const practiceTargets = buildPracticeTargets(practicePartLabels, praatMetrics.word_prosody ?? []);
  const practicePartCount = practiceTargets.length;
  const verdict: SpeakingResultVerdict =
    !accepted || hasScriptMismatch
      ? "meaning"
      : missing.length > 0
        ? "vocab"
        : isChunked && !ready
          ? "join"
          : ready
            ? "ready"
            : "pronounce";
  const showCorrective =
    !(accepted && missing.length === 0) &&
    Boolean(corrective) &&
    Boolean(corrective!.errors.length > 0 || corrective!.hint || corrective!.correct_version);
  const hasFix = !accepted || missing.length > 0 || hasScriptMismatch;
  const hasPhrasePractice = phrasePracticeItems.length > 0;
  const hasPractice = hasPhrasePractice || (accepted && !hasScriptMismatch && practiceTargets.length > 0);
  const steps: ResultsStep[] = [
    ...(ready ? (["selfEval"] as const) : []),
    "overview",
    ...(hasFix ? (["fix"] as const) : []),
    ...(hasPractice ? (["practice"] as const) : []),
  ];

  return {
    accepted,
    targetScript,
    hasTargetScript,
    recognizedText,
    missing,
    scriptMismatches,
    scriptChunks,
    teacherPhraseChunks,
    isChunked,
    chunkScores,
    failedChunks,
    weakItems,
    pronunciationMastery,
    masteryCounts,
    contentAccuracy,
    corrective,
    meaningJudged,
    feedbackReliability,
    failedWords,
    contentMatchVerified,
    contentNeedsRetry,
    contentMismatchChunks,
    hasChunkMismatch,
    effectiveScriptMismatches,
    legacyPracticeWords,
    hasScriptMismatch,
    needsPhrasePractice,
    phrasePracticeItems,
    practicePartLabels,
    practiceTargets,
    practicePartCount,
    verdict,
    showCorrective,
    hasFix,
    hasPhrasePractice,
    hasPractice,
    steps,
  };
}
