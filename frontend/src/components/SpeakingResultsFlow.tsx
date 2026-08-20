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
  scriptMismatchTokens,
  splitScriptIntoChunks,
  splitTeacherScriptIntoPhrases,
} from "../utils/scriptAlignment";
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

interface AnalysisRun {
  version: AnalysisVersion;
  schemaVersion: string;
  status: "success" | "failed";
  latencyMs: number;
  result: PraatMetrics | null;
  error?: string;
}

interface ComparisonResult {
  audioAttemptId: string;
  comparisonGroupId?: string;
  runs: Partial<Record<AnalysisVersion, AnalysisRun>>;
}

interface PracticeTarget {
  /** Stable identity for the word-level record or an unmatched backend part. */
  key: string;
  label: string;
  word: WordProsody | null;
}

function practiceWordKey(word: WordProsody): string {
  return `word:${word.index}`;
}

/**
 * Join the backend's learner-facing practice parts to the exact word-level
 * records that contain the contour, tone and feedback. The old implementation
 * used an index into a separately filtered/sorted list; when a backend part
 * was uncertain or otherwise filtered out, the index stayed at zero and the
 * first word was shown instead.
 */
function buildPracticeTargets(
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

function AudioCompare({ modelAudioUrl, modelSentence, analysisAudioBlob }: {
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

function ProgressSnapshot({
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

type ResultsStep = "selfEval" | "overview" | "fix" | "practice";

const STEP_LABELS: Record<ResultsStep, { zh: string; en: string }> = {
  selfEval: { zh: "自評", en: "Self-check" },
  overview: { zh: "結果", en: "Results" },
  fix: { zh: "改句子", en: "Fix it" },
  practice: { zh: "練習", en: "Practice" },
};

interface SpeakingResultsFlowProps {
  selectedImage: string;
  selectedImageIndex: number;
  totalScenes: number;
  modelSentence?: string;
  modelAudioUrl?: string;
  narrativeMode: Topic["narrativeMode"];
  attempts: number;
  /** Scene unlocked: score/attempts plus content and pronunciation gates. */
  ready: boolean;
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
export default function SpeakingResultsFlow({
  selectedImage,
  selectedImageIndex,
  totalScenes,
  modelSentence,
  modelAudioUrl,
  narrativeMode,
  attempts,
  ready,
  masteryPassed,
  praatMetrics,
  analysisAudioBlob,
  submittedAudioName,
  clearedWords,
  onWordDrillPass,
  onSelfEvalSubmit,
  hasNextScene,
  onNextScene,
  onViewSummary,
  onRecordAgain,
  assistiveFeedback = null,
  assistiveRetriesUsed = 0,
  analysisVersion = "stable_v1",
  comparison,
}: SpeakingResultsFlowProps) {
  const ai = praatMetrics.ai_feedback;
  const targetScript = modelSentence ?? "";
  const hasTargetScript = Boolean(targetScript.trim());
  const accepted = isContentAccepted(praatMetrics);
  const vocabCoverage = ai?.vocabulary_coverage;
  const missing = vocabCoverage?.missing ?? [];
  const recognizedText =
    praatMetrics.recognized_text ??
    (hasTargetScript && praatMetrics.content_match === null
      ? ""
      : praatMetrics.transcription ?? "");
  const scriptMismatches = scriptMismatchTokens(targetScript, recognizedText);
  // Punctuation defines the preferred meaning-chunk boundaries. Long scripts
  // without punctuation still receive compact fallback chunks so the learner
  // is never sent back to a whole sentence as their only repair action.
  const scriptChunks = splitScriptIntoChunks(targetScript);
  const teacherPhraseChunks = splitTeacherScriptIntoPhrases(targetScript);
  const isChunked = scriptChunks.length > 1;
  const chunkScores = isChunked
    ? scoreScriptChunks(targetScript, recognizedText, praatMetrics.word_prosody)
    : [];
  const failedChunks = chunkScores.filter((chunk) => !chunk.passed);
  const usedCount = vocabCoverage?.used?.length ?? 0;
  const vocabTotal = usedCount + missing.length;
  const weakItems = weakToneGuideItems(praatMetrics.word_prosody || []);
  const pronunciationMastery = praatMetrics.pronunciation_mastery;
  const masteryCounts = pronunciationMastery &&
    typeof pronunciationMastery.passed_syllables === "number" &&
    typeof pronunciationMastery.total_syllables === "number"
    ? {
        passed: pronunciationMastery.passed_syllables,
        total: pronunciationMastery.total_syllables,
      }
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
  // The backend's content verdict is authoritative for accepted Taiwan
  // Mandarin variants such as 你/妳. The local character LCS is still useful
  // as a fallback, but it must not turn an accepted homophone into a whole
  // sentence-sized practice part.
  const contentMatchVerified = praatMetrics.content_match === true;
  const contentNeedsRetry = hasTargetScript && !contentMatchVerified;
  const contentMismatchChunks = contentMatchVerified
    ? []
    : failedChunks.filter((chunk) => chunk.mismatch.length > 0);
  const hasChunkMismatch = isChunked && contentMismatchChunks.length > 0;
  const effectiveScriptMismatches = contentMatchVerified ? [] : scriptMismatches;
  // Practice order: weakest shape first — the word the student most needs
  // is the first one the focus view lands on.
  const legacyPracticeWords = [...failedWords].sort(
    (a, b) =>
      (a.shape_accuracy ?? a.tone_accuracy ?? 0) -
      (b.shape_accuracy ?? b.tone_accuracy ?? 0),
  );
  const hasScriptMismatch = contentNeedsRetry || (isChunked
    ? hasChunkMismatch
    : effectiveScriptMismatches.length > 0);
  const needsPhrasePractice =
    hasScriptMismatch || ((!accepted || missing.length > 0) && scriptChunks.length > 0);
  const phrasePracticeItems = needsPhrasePractice
    ? (isChunked
      ? (contentMismatchChunks.length > 0
        ? contentMismatchChunks.map((chunk) => chunk.text)
        : (() => {
          const vocabChunks = scriptChunks.filter((chunk) =>
            missing.some((word) => chunk.includes(word)),
          );
          return vocabChunks.length > 0 ? vocabChunks : scriptChunks;
        })())
      : scriptChunks)
    : [];
  const [clearedPhrases, setClearedPhrases] = useState<string[]>([]);
  const remainingPracticePhrases = phrasePracticeItems.filter(
    (phrase) => !clearedPhrases.includes(phrase),
  );
  const allPhrasesCleared =
    phrasePracticeItems.length > 0 && remainingPracticePhrases.length === 0;
  // Meaning isn't fixed yet: only ever point at the teacher's own script
  // (mismatched parts + missing vocabulary). word_prosody tokens come from
  // the ASR transcript of whatever the student actually said, so once the
  // sentence has drifted from the script those tokens are the student's
  // wrong words, not something worth drilling. Once content is accepted,
  // switch to pronunciation polish on the words that were actually said.
  // The backend pronunciation mastery payload is the single source of truth
  // for the compact practice list shown to the learner. Local alignment is
  // still used for navigation, but never creates a competing list.
  const practicePartLabels = pronunciationMastery
    ? pronunciationMastery.practice_parts ?? Array.from(
      new Set([
        ...(pronunciationMastery.failed_words ?? []),
        ...(pronunciationMastery.missing_target_units ?? []),
      ]),
    )
    : legacyPracticeWords.map((word) => word.token);
  const practiceTargets = buildPracticeTargets(
    practicePartLabels,
    praatMetrics.word_prosody ?? [],
  );
  const practicePartCount = practiceTargets.length;
  const remainingDrillTargets = practiceTargets.filter(
    (target) => !target.word || !clearedWords.includes(target.word.token),
  );
  const allDrillsCleared =
    practiceTargets.length > 0 &&
    practiceTargets.every(
      (target) => Boolean(target.word) && clearedWords.includes(target.word!.token),
    );

  // The one-verdict ladder: meaning and required vocabulary gate the unlock;
  // pronunciation polish follows only after the learner has said the script.
  // A chunked script that has cleared every chunk but still isn't ready adds
  // one more rung — the chunks are each fine alone, so what's missing is
  // saying them together smoothly, not more word-level drilling.
  const verdict: "meaning" | "ready" | "vocab" | "pronounce" | "join" = !accepted || hasScriptMismatch
    ? "meaning"
    : missing.length > 0
      ? "vocab"
      : isChunked && !ready
        ? "join"
        : ready
          ? "ready"
          : "pronounce";

  const showCorrective =
    narrativeMode !== "listen_retell" &&
    !(accepted && missing.length === 0) &&
    corrective &&
    (corrective.errors.length > 0 || corrective.hint || corrective.correct_version);

  // Adaptive step list. A meaning failure never leads to word practice —
  // drilling pronunciation of a sentence that means the wrong thing is
  // wasted effort, so the flow stops at "fix it" and points back to record.
  const hasFix = !accepted || missing.length > 0 || hasScriptMismatch;
  const hasPhrasePractice = phrasePracticeItems.length > 0;
  const hasPractice = hasPhrasePractice || (accepted && !hasScriptMismatch && practiceTargets.length > 0);
  // Self-eval only fires on the attempt that actually completes the scene —
  // asking on every failed retry would be pure friction with nothing to
  // compare against yet.
  const showSelfEval = ready;
  const steps: ResultsStep[] = [
    ...(showSelfEval ? (["selfEval"] as const) : []),
    "overview",
    ...(hasFix ? (["fix"] as const) : []),
    ...(hasPractice ? (["practice"] as const) : []),
  ];

  const [step, setStep] = useState<ResultsStep>(() => steps[0]);
  const [maxVisited, setMaxVisited] = useState(0);
  const [feedbackModalOpen, setFeedbackModalOpen] = useState(false);
  const feedbackTriggerRef = useRef<HTMLButtonElement | null>(null);
  const closeFeedbackModal = () => {
    setFeedbackModalOpen(false);
    feedbackTriggerRef.current?.focus();
  };

  useEffect(() => {
    if (!feedbackModalOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeFeedbackModal();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [feedbackModalOpen]);
  const goToStep = (target: ResultsStep) => {
    const index = steps.indexOf(target);
    if (index === -1) return;
    setStep(target);
    setMaxVisited((prev) => Math.max(prev, index));
  };

  // The student's own pick, kept only for this mount (one per analysis) so
  // the overview step's comparison strip can show it next to the system's
  // verdict. null until answered; stays null if skipped.
  const [selfEvalAnswer, setSelfEvalAnswer] = useState<{
    content: SelfEvalLevel;
    pronunciation: SelfEvalLevel;
  } | null>(null);
  const handleSelfEvalSubmit = (levels: {
    content: SelfEvalLevel;
    pronunciation: SelfEvalLevel;
  }) => {
    setSelfEvalAnswer(levels);
    onSelfEvalSubmit?.(levels);
    goToStep("overview");
  };
  const handleSelfEvalSkip = () => {
    goToStep("overview");
  };

  // Focus mode starts on the first unresolved backend practice target.
  const [focusKey, setFocusKey] = useState<string | null>(() => {
    const first = practiceTargets.find(
      (target) => target.word && !clearedWords.includes(target.word.token),
    );
    return first?.key ?? practiceTargets[0]?.key ?? null;
  });
  const focusTarget = practiceTargets.find((target) => target.key === focusKey);
  const focusWord = focusTarget?.word ?? null;
  useEffect(() => {
    if (focusKey && practiceTargets.some((target) => target.key === focusKey)) {
      return;
    }
    const first = practiceTargets.find(
      (target) => target.word && !clearedWords.includes(target.word.token),
    );
    const nextKey = first?.key ?? practiceTargets[0]?.key ?? null;
    if (nextKey !== focusKey) setFocusKey(nextKey);
  }, [clearedWords, focusKey, practiceTargets]);
  const [phraseFocusIndex, setPhraseFocusIndex] = useState(0);
  const focusPhrase = phrasePracticeItems[phraseFocusIndex];

  // After a drill pass, linger briefly so the student sees their ✓ result,
  // then move focus to the next word still waiting.
  const advanceTimer = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (advanceTimer.current !== null) {
        window.clearTimeout(advanceTimer.current);
      }
    },
    [],
  );
  const handleDrillPass = (token: string) => {
    onWordDrillPass(token);
    const clearedNow = new Set([...clearedWords, token]);
    const currentIndex = focusTarget
      ? practiceTargets.findIndex((target) => target.key === focusTarget.key)
      : -1;
    const after = practiceTargets.findIndex(
      (target, index) =>
        index > currentIndex &&
        target.word !== null &&
        !clearedNow.has(target.word.token),
    );
    const fallback = practiceTargets.findIndex(
      (target) => target.word !== null && !clearedNow.has(target.word.token),
    );
    const target = after !== -1 ? after : fallback;
    if (target !== -1 && practiceTargets[target].key !== focusKey) {
      advanceTimer.current = window.setTimeout(() => {
        setFocusKey(practiceTargets[target].key);
      }, 1500);
    }
  };

  const handlePhrasePass = (phrase: string) => {
    setClearedPhrases((current) =>
      current.includes(phrase) ? current : [...current, phrase],
    );
    const currentIndex = phrasePracticeItems.indexOf(phrase);
    const nextIndex = phrasePracticeItems.findIndex(
      (candidate, index) =>
        index > currentIndex && !clearedPhrases.includes(candidate),
    );
    if (nextIndex !== -1) {
      advanceTimer.current = window.setTimeout(
        () => setPhraseFocusIndex(nextIndex),
        1200,
      );
    }
  };

  /* scene label intentionally omitted from results to avoid repeating sidebar context. */
  const unusedSceneChip = (
    <span className="sfc-scene-chip">
      <BiLabel
        zh={`部分 ${selectedImageIndex + 1}/${totalScenes}`}
        en={`Scene ${selectedImageIndex + 1} of ${totalScenes}`}
      />
      {attempts > 0 && (
        <span className="sfc-attempt-chip">
          <BiLabel zh={`第 ${attempts} 次`} en={`Attempt ${attempts}`} />
        </span>
      )}
    </span>
  );
  void unusedSceneChip;

  const verdictContent = {
    meaning: {
      icon: "🧭",
      className: "sfc-verdict-meaning",
      // No fixed banner text: the "meaning" verdict fires for anything from a
      // real content-accuracy rejection to just one short ASR-mismatched
      // chunk (e.g. a proper noun) — the Fix It step's own feedback already
      // says what's actually wrong, so a generic "your meaning is wrong"
      // line here was often misleading rather than helpful.
      text: null,
    },
    vocab: {
      icon: "📝",
      className: "sfc-verdict-vocab",
      text: (
        <BiLabel
          zh={`還缺 ${missing.length} 個詞：${missing.join("、")}`}
          pinyin={`Hái quē ${missing.length} ge cí: ${missing.join("、")}`}
          en={`${missing.length} word${missing.length > 1 ? "s" : ""} still missing: ${missing.join("、")}`}
        />
      ),
    },
    pronounce: {
      icon: "🎯",
      className: "sfc-verdict-pronounce",
      text: weakItems[0] ? (
        <BiLabel
          zh={`生詞都用到了！現在練「${weakItems[0].token}」的聲調。`}
          pinyin={`Shēngcí dōu yòng dào le! Xiànzài liàn “${weakItems[0].token}” de shēngdiào.`}
          en={`All words used! Now practice the tone of "${weakItems[0].token}".`}
        />
      ) : (
        <BiLabel
          zh="再錄一次，讓聲調更清楚。"
          pinyin="Zài lù yí cì, ràng shēngdiào gèng qīngchu."
          en="Record again and make your tones clearer."
        />
      ),
    },
    join: {
      icon: "🔗",
      className: "sfc-verdict-join",
      text: (
        <BiLabel
          zh="每個部分都不錯！現在試著把整句連起來，說得更順。"
          pinyin="Měi ge bùfen dōu búcuò! Xiànzài shìzhe bǎ zhěng jù liánqǐlái, shuō de gèng shùn."
          en="Every part sounds good! Now try saying the whole sentence smoothly, all connected."
        />
      ),
    },
    ready: {
      icon: "🎉",
      className: "sfc-verdict-ready",
      text: (
        <BiLabel
          zh={`部分 ${selectedImageIndex + 1} 完成！可以前往下一個部分。`}
          pinyin={`Bùfen ${selectedImageIndex + 1} wánchéng! Kěyǐ qiánwǎng xià yí ge bùfen.`}
          en={`Scene ${selectedImageIndex + 1} complete! You can move on.`}
        />
      ),
    },
  }[verdict];

  // ── Step body: overview ───────────────────────────────────────────────
  const overviewStep = (
    <div className="sfc-step-panel">
      <header
        className={`sfc-verdict ${verdictContent.className}${verdictContent.text ? "" : " sfc-verdict--compact"}`}
      >
        <div className="sfc-verdict-lead">
          <span className="sfc-verdict-icon" aria-hidden="true">
            {verdictContent.icon}
          </span>
          {verdictContent.text && (
            <p className="sfc-verdict-text">{verdictContent.text}</p>
          )}
        </div>
      </header>

      <VoiceFeedbackReliabilityNotice
        assessment={feedbackReliability}
        attemptCount={attempts}
      />
      {hasTargetScript && (
        <ContentDiffDisplay
          target={targetScript}
          heard={recognizedText || null}
          diff={praatMetrics.content_diff}
          contentMatch={praatMetrics.content_match}
        />
      )}
      {pronunciationMastery && (
        <div
          className={`sfc-mastery-banner${pronunciationMastery.status === "passed" ? " is-cleared" : ""}`}
          role="status"
          aria-label="Pronunciation mastery status"
        >
          <p className="sfc-mastery-lead">
            {contentNeedsRetry
              ? "Content not verified — record the script again"
              : pronunciationMastery.status === "passed"
              ? "✓ Pronunciation passed"
              : pronunciationMastery.status === "not_judged"
                ? "尚未判定 / Not judged yet"
                : "發音需要練習 / Needs practice"}
          </p>
          {pronunciationMastery.message && <p>{pronunciationMastery.message}</p>}
          {contentNeedsRetry && <small>Tone measurements are reference-only until the script matches.</small>}
        </div>
      )}

      {selfEvalAnswer && (
        <div className="self-eval-compare">
          <div className="self-eval-compare-row">
            <span className="self-eval-compare-label">
              <BiLabel zh="意思" en="Meaning" />
            </span>
            <span className="self-eval-compare-side">
              <BiLabel zh="你" en="You" />{" "}
              <span className="self-eval-compare-emoji">
                {SELF_EVAL_EMOJI[selfEvalAnswer.content]}
              </span>
            </span>
            <span className="self-eval-compare-side">
              <BiLabel zh="系統" en="System" />{" "}
              <span className="self-eval-compare-emoji">
                {SELF_EVAL_EMOJI[systemContentLevel(praatMetrics, hasScriptMismatch)]}
              </span>
            </span>
          </div>
          <div className="self-eval-compare-row">
            <span className="self-eval-compare-label">
              <BiLabel zh="發音" en="Pronunciation" />
            </span>
            <span className="self-eval-compare-side">
              <BiLabel zh="你" en="You" />{" "}
              <span className="self-eval-compare-emoji">
                {SELF_EVAL_EMOJI[selfEvalAnswer.pronunciation]}
              </span>
            </span>
            <span className="self-eval-compare-side">
              <BiLabel zh="系統" en="System" />{" "}
              <span className="self-eval-compare-emoji">
                {SELF_EVAL_EMOJI[systemPronunciationLevel(praatMetrics)]}
              </span>
            </span>
          </div>
        </div>
      )}

      {/* The recording itself already plays from the persistent AudioCompare
          card in the scene column (see practice-scene-col above) — showing
          it a second time here just duplicated the same native <audio>
          element on screen. This block now only carries the extras that
          aren't shown there: the recognized transcript and submitted file
          name. */}
      {(recognizedText || submittedAudioName) && (
        <div className="sfc-results-scene-extras">
          {recognizedText && (
            <p className="sfc-transcript">
              <BiLabel k="you_said" />{" "}
              <em lang="zh-TW">{recognizedText}</em>
            </p>
          )}
          {submittedAudioName && (
            <p className="submitted-audio-name">✓ {submittedAudioName}</p>
          )}
        </div>
      )}
      <ProgressSnapshot
        attempts={attempts}
        mastery={pronunciationMastery}
        practicePartCount={practicePartCount}
      />
      {assistiveFeedback && assistiveFeedback.length > 0 && (() => {
        const rolledUpState = worstState(assistiveFeedback);
        return rolledUpState ? <AssistiveFeedbackNotice state={rolledUpState} /> : null;
      })()}

      {analysisVersion === "phoneme_tone_v2" && (
        <section className="experimental-analysis-panel" aria-label="Experimental analysis">
          <div className="experimental-analysis-heading">
            <strong>Experimental V2</strong><span className="analysis-version-badge">Character + phoneme + T1–T5</span>
          </div>
          <p>This result is for evaluation only and does not change progression or mastery.</p>
          {praatMetrics.character_prosody?.length ? (
            <div className="experimental-character-grid">
              {praatMetrics.character_prosody.map((item) => (
                <div className="experimental-character-card" key={`${item.char_index}-${item.char}`}>
                  <strong>{item.char}</strong><span>{item.pinyin}</span>
                  <small>Expected T{item.expected_tone ?? "?"} · Detected {item.detected_tone ? `T${item.detected_tone}` : item.tone_status}</small>
                </div>
              ))}
            </div>
          ) : <p>Character alignment is not available for this attempt.</p>}
        </section>
      )}

      {comparison && (
        <section className="analysis-compare-panel" aria-label="Stable and experimental comparison">
          <h3>Comparison</h3>
          <div className="analysis-compare-grid">
            {(["stable_v1", "phoneme_tone_v2"] as AnalysisVersion[]).map((version) => {
              const run = comparison.runs[version];
              return <div className="analysis-compare-card" key={version}>
                <strong>{version === "stable_v1" ? "Stable V1 — Current" : "Experimental V2"}</strong>
                <span>{run?.status ?? "not run"} · {run?.latencyMs ?? 0} ms</span>
                {run?.error ? <small>{run.error}</small> : run?.result?.character_prosody ? <small>{run.result.character_prosody.length} characters aligned</small> : <small>Current tone and prosody result</small>}
              </div>;
            })}
          </div>
        </section>
      )}

      {vocabTotal > 0 && (
        <p className="sfc-stats-line">
          <span>
            📝{" "}
            <BiLabel
              zh={`生詞 ${usedCount}/${vocabTotal}`}
              en={`Vocabulary ${usedCount}/${vocabTotal}`}
            />
          </span>
        </p>
      )}

      {/* Forward CTA — where the verdict points, one obvious next action. */}
      {verdict === "meaning" && hasFix && (
        <AppButton
          tone="primary"
          className="sfc-btn-next sfc-step-cta"
          onClick={() => goToStep("fix")}
        >
          <BiLabel zh="看怎麼改" en="See how to fix it" /> →
        </AppButton>
      )}
      {verdict === "vocab" && hasFix && (
        <AppButton
          tone="primary"
          className="sfc-btn-next sfc-step-cta"
          onClick={() => goToStep("fix")}
        >
          <BiLabel zh="看少了的生詞" en="See the missing words" /> →
        </AppButton>
      )}
      {verdict === "join" && (
        <AppButton
          tone="primary"
          className="sfc-btn-next sfc-step-cta"
          onClick={onRecordAgain}
        >
          🎙️ <BiLabel zh="再錄一次，說順一點" en="Record again, smoother this time" />
        </AppButton>
      )}
      {verdict === "pronounce" &&
        (hasPractice ? (
          <AppButton
            tone="primary"
            className="sfc-btn-next sfc-step-cta"
            onClick={() => goToStep("practice")}
          >
            <BiLabel zh="練習生詞" en={hasPhrasePractice ? "Practice the parts" : "Practice the words"} /> →
          </AppButton>
        ) : (
          <AppButton
            tone="primary"
            className="sfc-btn-next sfc-step-cta"
            onClick={onRecordAgain}
          >
            🎙️ <BiLabel zh="再錄一次" en="Record again" />
          </AppButton>
        ))}
    </div>
  );

  // ── Step body: fix (meaning + vocabulary) ─────────────────────────────
  const fixStep = (
    <div className="sfc-step-panel">
      {!accepted && (meaningJudged || showCorrective) && (
        <section className="sfc-result-card sfc-result-card--meaning is-bad">
          <header className="sfc-result-card-header">
            <span aria-hidden="true">🧭</span>
            <BiLabel zh="意思" en="Meaning" />
          </header>

          {meaningJudged && contentAccuracy?.feedback && (
            <div className="sfc-result-card-body">
              <p className="content-accuracy-feedback">
                {contentAccuracy.feedback}
              </p>
              {contentAccuracy.missed_details.length > 0 && (
                <p className="content-accuracy-missed">
                  ✗ {contentAccuracy.missed_details.join(", ")}
                </p>
              )}
            </div>
          )}

          {showCorrective && (
            <div
              className={`sfc-result-card-body sfc-corrective${corrective!.reveal_answer ? "" : " is-hint"}`}
            >
              <p className="sfc-corrective-heading">
                {corrective!.reveal_answer ? (
                  <BiLabel zh="正確答案" en="Correct version" />
                ) : (
                  <BiLabel zh="提示" en="Hint" />
                )}
              </p>
              {corrective!.hint && <p>{corrective!.hint}</p>}
              {corrective!.reveal_answer && corrective!.correct_version && (
                <p>
                  <strong>{corrective!.correct_version}</strong>
                </p>
              )}
            </div>
          )}
        </section>
      )}

      {hasScriptMismatch && isChunked && (
        <section className="sfc-result-card sfc-result-card--vocab">
          <header className="sfc-result-card-header">
            <span aria-hidden="true">📝</span>
            <BiLabel zh="跟讀對照（分段）" en="Script check (by part)" />
          </header>
          <div className="sfc-result-card-body">
            <p className="sfc-result-card-lead">
              <BiLabel zh="先練好還沒過的部分，再說一次整句" en="Practice the parts below, then say the whole sentence again." />
            </p>
            <ContentDiffDisplay
              target={targetScript}
              heard={recognizedText || null}
              diff={praatMetrics.content_diff}
              contentMatch={praatMetrics.content_match}
            />
            <div className="sfc-missing-chips">
              {chunkScores.map((chunk, index) => (
                <span
                  key={`${chunk.text}-${index}`}
                  className={`vocab-chip sfc-missing-chip${chunk.passed ? " is-cleared" : ""}`}
                >
                  {chunk.text} {chunk.passed ? "✓" : "✗"}
                </span>
              ))}
            </div>
          </div>
        </section>
      )}

      {hasScriptMismatch && !isChunked && (
        <section className="sfc-result-card sfc-result-card--vocab">
          <header className="sfc-result-card-header">
            <span aria-hidden="true">📝</span>
            <BiLabel zh="跟讀對照" en="Script check" />
          </header>
          <div className="sfc-result-card-body">
            <p className="sfc-result-card-lead">
              <BiLabel zh="這些字和範例句不同，請再說一次" en="These parts differ from the model sentence. Say them again." />
            </p>
            <ContentDiffDisplay
              target={targetScript}
              heard={recognizedText || null}
              diff={praatMetrics.content_diff}
              contentMatch={praatMetrics.content_match}
            />
            <div className="sfc-missing-chips">
              {scriptMismatches.map((word) => (
                <span key={word} className="vocab-chip sfc-missing-chip">
                  {word}
                </span>
              ))}
            </div>
          </div>
        </section>
      )}

      {missing.length > 0 && (
        <section className="sfc-result-card sfc-result-card--vocab">
          <header className="sfc-result-card-header">
            <span aria-hidden="true">📝</span>
            <BiLabel zh="生詞" en="Vocabulary" />
          </header>
          <div className="sfc-result-card-body">
            <p className="sfc-result-card-lead">
              <BiLabel zh="試著加入" en="Try to include" />
            </p>
            <div className="sfc-missing-chips">
              {missing.map((w) => (
                <span key={w} className="vocab-chip sfc-missing-chip">
                  {w}
                </span>
              ))}
            </div>
            {accepted && showCorrective && (
              <div
                className={`sfc-corrective${corrective!.reveal_answer ? "" : " is-hint"}`}
              >
                <p className="sfc-corrective-heading">
                  {corrective!.reveal_answer ? (
                    <BiLabel zh="正確答案" en="Correct version" />
                  ) : (
                    <BiLabel zh="提示" en="Hint" />
                  )}
                </p>
                {corrective!.hint && <p>{corrective!.hint}</p>}
                {corrective!.reveal_answer && corrective!.correct_version && (
                  <p>
                    <strong>{corrective!.correct_version}</strong>
                  </p>
                )}
              </div>
            )}
          </div>
        </section>
      )}

      <div className="sfc-step-cta-row">
        {!hasPractice && (
        <AppButton
          tone="primary"
          className="sfc-btn-next sfc-step-cta"
          onClick={onRecordAgain}
        >
          🎙️ <BiLabel zh="再錄一次" en="Record again" />
        </AppButton>
        )}
        {hasPractice && (
          <AppButton
            tone="primary"
            className="sfc-btn-next sfc-step-cta"
            onClick={() => goToStep("practice")}
          >
            <BiLabel zh="練習生詞" en={hasPhrasePractice ? "Practice the parts" : "Practice the words"} /> →
          </AppButton>
        )}
      </div>
    </div>
  );

  // ── Step body: practice (one word at a time) ──────────────────────────
  const wordPracticeStep = (
    <div className="sfc-step-panel">
      {allDrillsCleared ? (
        <div className="sfc-mastery-banner is-cleared">
          <p className="sfc-mastery-lead">
            🎉{" "}
            <BiLabel
              zh="這些字都好了！現在再錄一次整句。"
              pinyin="Zhèxiē zì dōu hǎo le! Xiànzài zài lù yí cì zhěng jù."
              en="All words cleared! Now record the whole sentence again."
            />
          </p>
        </div>
      ) : (
        <p className="sfc-mastery-lead sfc-practice-lead">
          🔑{" "}
          <BiLabel
            zh="先練好這些字，再錄整句："
            pinyin="Xiān liàn hǎo zhèxiē zì, zài lù zhěng jù:"
            en="First practice these words, then re-record the sentence:"
          />
        </p>
      )}

      <div className="sfc-practice-chips">
        {practiceTargets.map((target) => {
          const cleared = Boolean(
            target.word && clearedWords.includes(target.word.token),
          );
          const current = target.key === focusKey;
          return (
            <button
              key={target.key}
              type="button"
              className={`sfc-mastery-chip sfc-practice-chip ${cleared ? "is-cleared" : "is-pending"}${target.word ? "" : " is-unavailable"}${current ? " is-current" : ""}`}
              onClick={() => setFocusKey(target.key)}
              aria-pressed={current}
            >
              <span className="sfc-practice-chip-word">
                {target.label} {cleared ? "✓" : target.word ? "✗" : "—"}
              </span>
              {target.word ? (
                <span className="sfc-practice-chip-pinyin">
                  {toPinyin(target.word.token)}
                </span>
              ) : (
                <span className="sfc-practice-chip-pinyin">
                  No word-level result
                </span>
              )}
            </button>
          );
        })}
      </div>

      {focusTarget && (
        <>
          {focusWord && (
            <div
              className="sfc-pronounce-legend mini-contour-legend"
              aria-hidden="true"
            >
            <span className="mini-contour-legend-actual">
              <BiLabel zh="你的音高" en="Your pitch" />
            </span>
            <span className="mini-contour-legend-reference">
              <BiLabel zh="目標形狀" en="Target shape" />
            </span>
            </div>
          )}
          <div className="sfc-focus-word">
            {focusWord ? (
              <WordProsodyCard
                key={focusTarget?.key}
                item={focusWord}
                onDrillPass={handleDrillPass}
                drillDefaultOpen
              />
            ) : (
              <div className="sfc-practice-unavailable" role="status">
                <strong>No word-level result / 暫無單字分析</strong>
                <span>{focusTarget?.label}</span>
              </div>
            )}
          </div>
        </>
      )}

      {allDrillsCleared && (
        <AppButton
          tone="primary"
          className="sfc-btn-next sfc-step-cta"
          onClick={onRecordAgain}
        >
          🎙️ <BiLabel zh="再錄整句" en="Record the whole sentence" />
        </AppButton>
      )}
    </div>
  );

  const phrasePracticeStep = (
    <div className="sfc-step-panel">
      {allPhrasesCleared ? (
        <div className="sfc-mastery-banner is-cleared">
          <p className="sfc-mastery-lead">
            🎉{" "}
            <BiLabel
              zh="每個部分都通過了！現在自然地說一次整句。"
              pinyin="Měi ge bùfen dōu tōngguò le! Xiànzài zìrán de shuō yí cì zhěng jù."
              en="Every part has passed! Now say the whole sentence naturally."
            />
          </p>
        </div>
      ) : (
        <p className="sfc-mastery-lead sfc-practice-lead">
          🔑{" "}
          <BiLabel
            zh="一次練一個部分，藍線是你的音高，虛線是目標形狀。"
            pinyin="Yí cì liàn yí ge bùfen, lán xiàn shì nǐ de yīngāo, xūxiàn shì mùbiāo xíngzhuàng."
            en="Practice one part at a time. The blue line is your pitch; the dashed line is the target shape."
          />
        </p>
      )}

      <div className="sfc-practice-chips" aria-label="Phrase practice progress">
        {phrasePracticeItems.map((phrase, index) => {
          const cleared = clearedPhrases.includes(phrase);
          return (
            <button
              key={`${phrase}-${index}`}
              type="button"
              className={`sfc-mastery-chip sfc-practice-chip ${cleared ? "is-cleared" : "is-pending"}${index === phraseFocusIndex ? " is-current" : ""}`}
              onClick={() => setPhraseFocusIndex(index)}
              aria-pressed={index === phraseFocusIndex}
            >
              {phrase} {cleared ? "✓" : ""}
            </button>
          );
        })}
      </div>

      {focusPhrase && !allPhrasesCleared && (
        <>
          <div
            className="sfc-pronounce-legend mini-contour-legend"
            aria-hidden="true"
          >
            <span className="mini-contour-legend-actual">
              <BiLabel zh="你的音高" en="Your pitch" />
            </span>
            <span className="mini-contour-legend-reference">
              <BiLabel zh="目標形狀" en="Target shape" />
            </span>
          </div>
          <div className="sfc-focus-word sfc-focus-phrase">
            <PhrasePracticeDrill
              key={focusPhrase}
              phrase={focusPhrase}
              onPass={handlePhrasePass}
            />
          </div>
        </>
      )}

      {allPhrasesCleared && (
        <AppButton
          tone="primary"
          className="sfc-btn-next sfc-step-cta"
          onClick={onRecordAgain}
        >
          🎙️ <BiLabel zh="再錄整句" pinyin="Zài lù zhěng jù" en="Record the whole sentence" />
        </AppButton>
      )}
    </div>
  );

  const practiceStep = hasPhrasePractice ? phrasePracticeStep : wordPracticeStep;

  const selfEvalStep = (
    <SelfEvalStep onSubmit={handleSelfEvalSubmit} onSkip={handleSelfEvalSkip} />
  );

  const stepBody = {
    selfEval: selfEvalStep,
    overview: overviewStep,
    fix: fixStep,
    practice: practiceStep,
  }[step];

  return (
    <section
      className="speaking-flow-card sfc-results sfc-screen"
      aria-label="Recording results"
    >
      <div className="practice-workspace">
        {/* The scene image persists from the record screen at the same
            width/ratio — the anchor that makes record → results read as one
            continuous place. */}
        <div className="practice-scene-col">
          <div className="practice-scene-image">
            <img src={selectedImage} alt={`Scene ${selectedImageIndex + 1}`} />
          </div>
          <AudioCompare
            modelAudioUrl={modelAudioUrl}
            modelSentence={modelSentence}
            analysisAudioBlob={analysisAudioBlob}
          />
          <div className="sfc-left-feedback">
            <button
              ref={feedbackTriggerRef}
              type="button"
              className="sfc-left-feedback-summary"
              aria-haspopup="dialog"
              aria-expanded={feedbackModalOpen}
              aria-controls="sfc-feedback-modal"
              onClick={() => setFeedbackModalOpen(true)}
            >
              <BiLabel zh="發音分析" en="Pronunciation feedback" />
              <span>
                <BiLabel
                  zh={practicePartCount > 0
                    ? `還有 ${practicePartCount} 個部分要練習`
                    : "已通過評量音調"}
                  en={practicePartCount > 0
                    ? `${practicePartCount} part${practicePartCount === 1 ? "" : "s"} to practise`
                    : "Measured tones cleared"}
                />
              </span>
            </button>
          </div>
        </div>

        <div className="sfc-results-main">
          {steps.length > 1 && (
            <nav className="sfc-stepper" aria-label="Feedback steps">
              {steps.map((s, index) => {
                const current = s === step;
                const visited = index <= maxVisited;
                return (
                  <button
                    key={s}
                    type="button"
                    className={`sfc-step${current ? " is-current" : ""}${visited && !current ? " is-visited" : ""}`}
                    disabled={!visited}
                    aria-current={current ? "step" : undefined}
                    onClick={() => setStep(s)}
                  >
                    <span className="sfc-step-num" aria-hidden="true">
                      {visited && !current ? "✓" : index + 1}
                    </span>
                    <BiLabel zh={STEP_LABELS[s].zh} en={STEP_LABELS[s].en} />
                  </button>
                );
              })}
            </nav>
          )}
          {stepBody}
        </div>
      </div>

      {feedbackModalOpen && (
        <div
          className="sfc-feedback-modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeFeedbackModal();
          }}
        >
          <section
            id="sfc-feedback-modal"
            className="sfc-feedback-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="sfc-feedback-modal-title"
          >
            <header className="sfc-feedback-modal-header">
              <div id="sfc-feedback-modal-title">
                <BiLabel zh="發音分析" en="Pronunciation feedback" />
              </div>
              <button
                type="button"
                className="sfc-feedback-modal-close"
                aria-label="Close pronunciation feedback"
                onClick={closeFeedbackModal}
              >
                ×
              </button>
            </header>
            <div className="sfc-feedback-modal-body">
              <PronunciationBreakdown
                words={praatMetrics.word_prosody || []}
                targetText={targetScript}
                transcription={recognizedText}
                teacherPhrases={teacherPhraseChunks}
                assistiveFeedback={assistiveFeedback}
                masteryCounts={masteryCounts}
              />
            </div>
          </section>
        </div>
      )}

      <footer className="sfc-footer">
        {hasPhrasePractice && !allPhrasesCleared ? (
          <p className="sfc-unlock-note">
            🔒{" "}
            <BiLabel
              zh={`還有 ${remainingPracticePhrases.length} 個部分要練，才能錄整句`}
              pinyin={`Hái yǒu ${remainingPracticePhrases.length} ge bùfen yào liàn, cáinéng lù zhěng jù`}
              en={`${remainingPracticePhrases.length} more part${remainingPracticePhrases.length === 1 ? "" : "s"} to practice before recording the whole sentence`}
            />
          </p>
        ) : hasPhrasePractice && allPhrasesCleared && !ready ? (
          <p className="sfc-unlock-note">
            🔒{" "}
            <BiLabel
              zh="每個部分都通過了，再錄一次整句就能完成這一部分。"
              pinyin="Měi ge bùfen dōu tōngguò le, zài lù yí cì zhěng jù jiù néng wánchéng zhè yí bùfen."
              en="All parts passed. Record the full sentence once more to complete this scene."
            />
          </p>
        ) : !ready && !masteryPassed && practiceTargets.length > 0 ? (
          <p className="sfc-unlock-note">
            🔒{" "}
            <BiLabel
              zh={`每個字都要 ✓ 才能過關 — 還有 ${remainingDrillTargets.length > 0 ? `${remainingDrillTargets.length} 個部分要練` : "整句要再錄一次"}`}
              pinyin={`Měi ge zì dōu yào ✓ cáinéng guòguān — hái yǒu ${remainingDrillTargets.length > 0 ? `${remainingDrillTargets.length} ge bùfèn yào liàn` : "zhěng jù yào zài lù yí cì"}`}
              en={`Every practice part needs a ✓ — ${remainingDrillTargets.length > 0 ? `${remainingDrillTargets.length} part${remainingDrillTargets.length > 1 ? "s" : ""} left to practice` : "re-record the whole sentence"}`}
            />
          </p>
        ) : !ready ? (
          <p className="sfc-unlock-note">
            🔒{" "}
            <BiLabel
              zh={`聲調 70 分、流暢 65 分，或練習 4 次即可打開（目前 ${attempts} 次）`}
              pinyin={`Shēngdiào 70 fēn, liúchàng 65 fēn, huò liànxí 4 cì jí kě dǎkāi (mùqián ${attempts} cì)`}
              en={`Unlock with tone 70, fluency 65, or 4 attempts (now: ${attempts})`}
            />
          </p>
        ) : null}
        {/* Recording again is always available. It used to sit inside the
            `ready` branch along with the forward actions, which meant that
            before the scene unlocked the footer was a 🔒 note and nothing
            else — while that same note told the student to "re-record the
            whole sentence". Re-recording is not progression: the mastery gate
            still decides what unlocks, and it is untouched. */}
        {/* STEP 3's bounded retry offer: at most one, only for a syllable
            actually flagged CHECK_THIS_TONE, and always optional -- the
            "Record again" button above/below is already unconditionally
            available regardless, so declining costs nothing. */}
        {assistiveFeedback && shouldOfferRetry(worstState(assistiveFeedback), assistiveRetriesUsed) && (
          <p className="sfc-assistive-retry-hint">
            <BiLabel
              zh="想再試一次這個音嗎？"
              pinyin="Xiǎng zài shì yí cì zhège yīn ma?"
              en="Want to try that tone once more? Totally optional."
            />
          </p>
        )}
        <div className="sfc-footer-actions">
          <AppButton tone="subtle" className="sfc-btn-again" onClick={onRecordAgain}>
            🎙️ <BiLabel zh="再錄一次" pinyin="Zài lù yí cì" en="Record again" />
          </AppButton>
          {ready &&
            (hasNextScene ? (
              <AppButton
                tone="secondary"
                className="sfc-btn-next"
                onClick={onNextScene}
              >
                <BiLabel k="next_scene" /> →
              </AppButton>
            ) : (
              <AppButton
                tone="secondary"
                className="sfc-btn-next"
                onClick={onViewSummary}
              >
                <BiLabel zh="查看總結" pinyin="Chákàn zǒngjié" en="View summary" /> →
              </AppButton>
            ))}
        </div>
      </footer>
    </section>
  );
}
