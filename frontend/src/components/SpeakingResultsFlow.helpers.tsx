// @ts-nocheck
import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import { BiLabel } from "./BiLabel";
import AppButton from "./AppButton";
import RecordingPlayback from "./RecordingPlayback";
import ReferenceAudioCard from "./ReferenceAudioCard";
import PhrasePracticeDrill from "./PhrasePracticeDrill";
import ContentDiffDisplay from "./ContentDiffDisplay";
import WordProsodyCard from "./WordProsodyCard";
import PronunciationBreakdown from "./PronunciationBreakdown";
import SelfEvalStep from "./SelfEvalStep";
import {
  failedProsodyWords,
  isContentAccepted,
  weakToneGuideItems,
} from "../utils/storyRecorderFeedback";
import {
  scoreScriptChunks,
  scriptAlignmentText,
  scriptMismatchTokens,
  splitScriptIntoChunks,
  splitTeacherScriptIntoPhrases,
} from "../utils/scriptAlignment";
import { primePinyin } from "../utils/pinyin";
import {
  SELF_EVAL_EMOJI,
  systemContentLevel,
  systemPronunciationLevel,
  type SelfEvalLevel,
} from "../utils/selfEvalComparison";
import type { PraatMetrics, Topic, WordProsody } from "./StoryRecorder";
import { toPinyin } from "../utils/pinyin";
import VoiceFeedbackReliabilityNotice, {
  AssistiveFeedbackNotice,
} from "./VoiceFeedbackReliabilityNotice";
import { assessVoiceFeedbackReliability } from "../utils/voiceFeedbackReliability";
import { worstState, type AssistiveFeedbackSyllable } from "../utils/assistiveFeedback";
import { shouldOfferRetry } from "../utils/retryPolicy";
import type { AnalysisVersion } from "../utils/analysisVersion";
export interface AnalysisRun {
  version: AnalysisVersion;
  schemaVersion: string;
  status: "success" | "failed";
  latencyMs: number;
  result: PraatMetrics | null;
  error?: string;
}

export interface ComparisonResult {
  audioAttemptId: string;
  comparisonGroupId?: string;
  runs: Partial<Record<AnalysisVersion, AnalysisRun>>;
}

export interface PracticeTarget {
  /** Stable identity for the word-level record or an unmatched backend part. */
  key: string;
  label: string;
  word: WordProsody | null;
}

export function practiceWordKey(word: WordProsody): string {
  return `word:${word.index}`;
}

/**
 * Join the backend's learner-facing practice parts to the exact word-level
 * records that contain the contour, tone and feedback. The old implementation
 * used an index into a separately filtered/sorted list; when a backend part
 * was uncertain or otherwise filtered out, the index stayed at zero and the
 * first word was shown instead.
 */
export function buildPracticeTargets(
  parts: string[],
  words: WordProsody[],
): PracticeTarget[] {
  const usedWordKeys = new Set<string>();

  return parts.map((rawPart, partIndex) => {
    const label = rawPart.trim();
    const word = words.find((candidate) => {
      const key = practiceWordKey(candidate);
      return candidate.token === label && !usedWordKeys.has(key);
    });

    if (word) {
      const key = practiceWordKey(word);
      usedWordKeys.add(key);
      return { key, label, word };
    }

    // Keep an unmatched backend part visible, but never silently replace it
    // with another word's result.
    return { key: `part:${partIndex}:${label}`, label, word: null };
  });
}

export function AudioCompare({ modelAudioUrl, modelSentence, analysisAudioBlob }: {
  modelAudioUrl?: string;
  modelSentence?: string;
  analysisAudioBlob: Blob | null;
}) {
  return (
    <div className="sfc-audio-compare" aria-label="Listen and compare">
      <ReferenceAudioCard audioUrl={modelAudioUrl} sentence={modelSentence} />
      {analysisAudioBlob ? (
        <RecordingPlayback blob={analysisAudioBlob} />
      ) : (
        <div className="sfc-recording-unavailable" role="status">
          <BiLabel zh="暫無你的錄音" en="Your recording unavailable" />
        </div>
      )}
    </div>
  );
}

export function ProgressSnapshot({
  attempts,
  mastery,
  practicePartCount,
}: {
  attempts: number;
  mastery: PraatMetrics["pronunciation_mastery"];
  practicePartCount: number;
}) {
  const passed = mastery?.passed_syllables;
  const total = mastery?.total_syllables;
  return (
    <section className="sfc-progress-snapshot" aria-label="Practice progress">
      <div className="sfc-progress-snapshot-heading">
        <strong>學習進度 / Progress</strong>
        <span>本次 / Current</span>
      </div>
      <div className="sfc-progress-snapshot-grid">
        <div><strong>{attempts}</strong><span>次數 / Attempts</span></div>
        <div><strong>{typeof passed === "number" && typeof total === "number" ? `${passed}/${total}` : "—"}</strong><span>音節 / Syllables</span></div>
        <div><strong>{practicePartCount}</strong><span>待練 / To practise</span></div>
      </div>
    </section>
  );
}

export type ResultsStep = "selfEval" | "overview" | "fix" | "practice";

export const STEP_LABELS: Record<ResultsStep, { zh: string; en: string }> = {
  selfEval: { zh: "自評", en: "Self-check" },
  overview: { zh: "結果", en: "Results" },
  fix: { zh: "改句子", en: "Fix it" },
  practice: { zh: "練習", en: "Practice" },
};

export interface SpeakingResultsFlowProps {
  selectedImage: string;
  selectedImageIndex: number;
  totalScenes: number;
  modelSentence?: string;
  modelAudioUrl?: string;
  attempts: number;
  /** Scene unlocked: score/attempts plus content and pronunciation gates. */
  ready: boolean;
  /** A completed analysis lets the student continue while keeping feedback visible. */
  canContinue?: boolean;
  /** Pronunciation gate only; used for the word-drill guidance. */
  masteryPassed: boolean;
  praatMetrics: PraatMetrics;
  analysisAudioBlob: Blob | null;
  /** Optional: set when this attempt was submitted as a named audio file
   * rather than recorded live. No current caller passes this — kept
   * optional (not reintroduced as required) since StoryRecorder no longer
   * threads it through; the JSX guard below already handles it being
   * undefined. */
  submittedAudioName?: string;
  clearedWords: string[];
  onWordDrillPass: (token: string) => void;
  /** Fired when the student answers the self-eval step (not on skip) — the
   * caller merges these into the scene's submission snapshot. */
  onSelfEvalSubmit?: (levels: {
    content: SelfEvalLevel;
    pronunciation: SelfEvalLevel;
  }) => void;
  hasNextScene: boolean;
  onNextScene: () => void;
  onViewSummary: () => void;
  onRecordAgain: () => void;
  /** Additive ACCEPT/UNCERTAIN/NEEDS_PRACTICE layer; absent/null unless the
   * backend has the assistive-feedback flag enabled. Never gates `ready` or
   * `onNextScene`/`onViewSummary` -- see `src/utils/retryPolicy.ts`. */
  assistiveFeedback?: AssistiveFeedbackSyllable[] | null;
  /** How many focused retries this attempt has already used; caller-owned
   * (this component has no attempt-scoped state of its own). Defaults to 0. */
  assistiveRetriesUsed?: number;
  analysisVersion?: AnalysisVersion;
  comparison?: ComparisonResult | null;
  /** Retained as an optional compatibility shape for previously stored
   * analysis records; the student flow no longer populates or renders it. */
}

/** The results half of the Speaking step, as a guided mini-flow instead of
 * one dense readout:
 *
 *   [0] selfEval — student rates their own meaning/pronunciation first,
 *                  before seeing any system verdict (only on a ready take)
 *   [1] overview — verdict, playback, stats, overall pronunciation notes
 *   [2] fix      — meaning correction + missing vocabulary (only when needed)
 *   [3] practice — one failed word at a time, weakest first, drill in place
 *
 * Steps are adaptive: a step that has nothing to show doesn't exist (not
 * "disabled"). Forward movement goes through each step's CTA; any step
 * already visited can be revisited from the stepper. The parent remounts
 * this component (key) per new analysis, which resets the flow to step 1. */
