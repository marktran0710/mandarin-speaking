// @ts-nocheck
import { useEffect, useRef, useState } from "react";
import { BiLabel } from "./BiLabel";
import SelfEvalStep from "./SelfEvalStep";
import { failedProsodyWords, isContentAccepted, weakToneGuideItems } from "../utils/storyRecorderFeedback";
import { scoreScriptChunks, scriptAlignmentText, scriptMismatchTokens, splitScriptIntoChunks, splitTeacherScriptIntoPhrases } from "../utils/scriptAlignment";
import { primePinyin } from "../utils/pinyin";
import type { SelfEvalLevel } from "../utils/selfEvalComparison";
import { assessVoiceFeedbackReliability } from "../utils/voiceFeedbackReliability";
import { buildPracticeTargets, type ResultsStep, type SpeakingResultsFlowProps } from "./SpeakingResultsFlow.helpers";
import SpeakingResultsOverviewStep from "./SpeakingResultsFlow.OverviewStep";
import SpeakingResultsFixStep from "./SpeakingResultsFlow.FixStep";
import SpeakingResultsPracticeStep from "./SpeakingResultsFlow.PracticeStep";
import SpeakingResultsFlowShell from "./SpeakingResultsFlow.Shell";

export default function SpeakingResultsFlow({
  selectedImage, selectedImageIndex, modelSentence, modelAudioUrl,
  attempts, ready, canContinue = ready, masteryPassed, praatMetrics, analysisAudioBlob, submittedAudioName,
  clearedWords, onWordDrillPass, onSelfEvalSubmit, hasNextScene, onNextScene,
  onViewSummary, onRecordAgain, assistiveFeedback = null, assistiveRetriesUsed = 0,
  analysisVersion = "stable_v1", comparison,
}: SpeakingResultsFlowProps) {
  const ai = praatMetrics.ai_feedback;
  const targetScript = modelSentence ?? "";
  const hasTargetScript = Boolean(targetScript.trim());
  const accepted = isContentAccepted(praatMetrics);
  const vocabCoverage = ai?.vocabulary_coverage;
  const missing = vocabCoverage?.missing ?? [];
  const recognizedText = praatMetrics.recognized_text ?? (hasTargetScript && praatMetrics.content_match === null ? "" : praatMetrics.transcription ?? "");
  const alignmentPinyinQuery = [scriptAlignmentText(targetScript), scriptAlignmentText(recognizedText)].join("\u0000");
  const [, setAlignmentPinyinRevision] = useState(0);
  useEffect(() => {
    let active = true;
    const texts = alignmentPinyinQuery.split("\u0000").filter(Boolean);
    if (texts.length === 0) return undefined;
    void primePinyin(texts).then(() => { if (active) setAlignmentPinyinRevision((revision) => revision + 1); }).catch(() => {});
    return () => { active = false; };
  }, [alignmentPinyinQuery]);

  const scriptMismatches = scriptMismatchTokens(targetScript, recognizedText);
  const scriptChunks = splitScriptIntoChunks(targetScript);
  const teacherPhraseChunks = splitTeacherScriptIntoPhrases(targetScript);
  const isChunked = scriptChunks.length > 1;
  const chunkScores = isChunked ? scoreScriptChunks(targetScript, recognizedText, praatMetrics.word_prosody) : [];
  const failedChunks = chunkScores.filter((chunk) => !chunk.passed);
  const weakItems = weakToneGuideItems(praatMetrics.word_prosody || []);
  const pronunciationMastery = praatMetrics.pronunciation_mastery;
  const masteryCounts = pronunciationMastery && typeof pronunciationMastery.passed_syllables === "number" && typeof pronunciationMastery.total_syllables === "number" ? { passed: pronunciationMastery.passed_syllables, total: pronunciationMastery.total_syllables } : undefined;
  const contentAccuracy = ai?.content_accuracy;
  const corrective = ai?.corrective_feedback;
  const meaningJudged = Boolean(contentAccuracy?.judged);
  const feedbackReliability = assessVoiceFeedbackReliability({ feedbackQuality: praatMetrics.feedback_quality, contentJudged: meaningJudged, pitchContour: praatMetrics.pitch_contour, wordProsody: praatMetrics.word_prosody, transcription: recognizedText });
  const failedWords = failedProsodyWords(praatMetrics.word_prosody);
  const contentMatchVerified = praatMetrics.content_match === true;
  const contentNeedsRetry = hasTargetScript && !contentMatchVerified;
  const contentMismatchChunks = contentMatchVerified ? [] : failedChunks.filter((chunk) => chunk.mismatch.length > 0);
  const hasChunkMismatch = isChunked && contentMismatchChunks.length > 0;
  const effectiveScriptMismatches = contentMatchVerified ? [] : scriptMismatches;
  const legacyPracticeWords = [...failedWords].sort((a, b) => (a.shape_accuracy ?? a.tone_accuracy ?? 0) - (b.shape_accuracy ?? b.tone_accuracy ?? 0));
  const hasScriptMismatch = contentNeedsRetry || (isChunked ? hasChunkMismatch : effectiveScriptMismatches.length > 0);
  const needsPhrasePractice = hasScriptMismatch || ((!accepted || missing.length > 0) && scriptChunks.length > 0);
  const phrasePracticeItems = needsPhrasePractice ? (isChunked ? (contentMismatchChunks.length > 0 ? contentMismatchChunks.map((chunk) => chunk.text) : (() => {
    const vocabChunks = scriptChunks.filter((chunk) => missing.some((word) => chunk.includes(word)));
    return vocabChunks.length > 0 ? vocabChunks : scriptChunks;
  })()) : scriptChunks) : [];
  const [clearedPhrases, setClearedPhrases] = useState<string[]>([]);
  const remainingPracticePhrases = phrasePracticeItems.filter((phrase) => !clearedPhrases.includes(phrase));
  const allPhrasesCleared = phrasePracticeItems.length > 0 && remainingPracticePhrases.length === 0;
  const practicePartLabels = pronunciationMastery ? pronunciationMastery.practice_parts ?? Array.from(new Set([...(pronunciationMastery.failed_words ?? []), ...(pronunciationMastery.missing_target_units ?? [])])) : legacyPracticeWords.map((word) => word.token);
  const practiceTargets = buildPracticeTargets(practicePartLabels, praatMetrics.word_prosody ?? []);
  const practicePartCount = practiceTargets.length;
  const remainingDrillTargets = practiceTargets.filter((target) => !target.word || !clearedWords.includes(target.word.token));
  const allDrillsCleared = practiceTargets.length > 0 && practiceTargets.every((target) => Boolean(target.word) && clearedWords.includes(target.word!.token));
  const verdict: "meaning" | "ready" | "vocab" | "pronounce" | "join" = !accepted || hasScriptMismatch ? "meaning" : missing.length > 0 ? "vocab" : isChunked && !ready ? "join" : ready ? "ready" : "pronounce";
  const showCorrective = !(accepted && missing.length === 0) && corrective && (corrective.errors.length > 0 || corrective.hint || corrective.correct_version);
  const hasFix = !accepted || missing.length > 0 || hasScriptMismatch;
  const hasPhrasePractice = phrasePracticeItems.length > 0;
  const hasPractice = hasPhrasePractice || (accepted && !hasScriptMismatch && practiceTargets.length > 0);
  const steps: ResultsStep[] = [...(ready ? (["selfEval"] as const) : []), "overview", ...(hasFix ? (["fix"] as const) : []), ...(hasPractice ? (["practice"] as const) : [])];

  const [step, setStep] = useState<ResultsStep>(() => steps[0]);
  const [maxVisited, setMaxVisited] = useState(0);
  const [feedbackModalOpen, setFeedbackModalOpen] = useState(false);
  const feedbackTriggerRef = useRef<HTMLButtonElement | null>(null);
  const feedbackModalRef = useRef<HTMLElement | null>(null);
  const feedbackModalCloseRef = useRef<HTMLButtonElement | null>(null);
  const closeFeedbackModal = () => { setFeedbackModalOpen(false); feedbackTriggerRef.current?.focus(); };
  const closeFeedbackModalRef = useRef(closeFeedbackModal);
  closeFeedbackModalRef.current = closeFeedbackModal;
  useEffect(() => {
    if (!feedbackModalOpen) return;
    const previousOverflow = document.body.style.overflow;
    const previousPaddingRight = document.body.style.paddingRight;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    // Hiding the page scrollbar for the modal otherwise widens the results
    // column by ~15px and makes the footer/buttons jump sideways underneath
    // the backdrop. Reserve that exact width while the modal is open.
    if (scrollbarWidth > 0) document.body.style.paddingRight = `${scrollbarWidth}px`;
    document.body.style.overflow = "hidden";
    const focusTimer = window.setTimeout(() => feedbackModalCloseRef.current?.focus(), 0);
    const getFocusable = () => Array.from(feedbackModalRef.current?.querySelectorAll<HTMLElement>(
      'a[href], area[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) ?? []);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeFeedbackModalRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = getFocusable();
      if (focusable.length === 0) {
        event.preventDefault();
        feedbackModalRef.current?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      document.body.style.paddingRight = previousPaddingRight;
    };
  }, [feedbackModalOpen]);
  const goToStep = (target: ResultsStep) => {
    const index = steps.indexOf(target);
    if (index === -1) return;
    setStep(target);
    setMaxVisited((previous) => Math.max(previous, index));
  };

  const [selfEvalAnswer, setSelfEvalAnswer] = useState<{ content: SelfEvalLevel; pronunciation: SelfEvalLevel } | null>(null);
  const handleSelfEvalSubmit = (levels: { content: SelfEvalLevel; pronunciation: SelfEvalLevel }) => { setSelfEvalAnswer(levels); onSelfEvalSubmit?.(levels); goToStep("overview"); };
  const [focusKey, setFocusKey] = useState<string | null>(() => practiceTargets.find((target) => target.word && !clearedWords.includes(target.word.token))?.key ?? practiceTargets[0]?.key ?? null);
  const focusTarget = practiceTargets.find((target) => target.key === focusKey);
  const focusWord = focusTarget?.word ?? null;
  useEffect(() => {
    if (focusKey && practiceTargets.some((target) => target.key === focusKey)) return;
    const nextKey = practiceTargets.find((target) => target.word && !clearedWords.includes(target.word.token))?.key ?? practiceTargets[0]?.key ?? null;
    if (nextKey !== focusKey) setFocusKey(nextKey);
  }, [clearedWords, focusKey, practiceTargets]);
  const [phraseFocusIndex, setPhraseFocusIndex] = useState(0);
  const focusPhrase = phrasePracticeItems[phraseFocusIndex];
  const advanceTimer = useRef<number | null>(null);
  useEffect(() => () => { if (advanceTimer.current !== null) window.clearTimeout(advanceTimer.current); }, []);
  const handleDrillPass = (token: string) => {
    onWordDrillPass(token);
    const clearedNow = new Set([...clearedWords, token]);
    const currentIndex = focusTarget ? practiceTargets.findIndex((target) => target.key === focusTarget.key) : -1;
    const after = practiceTargets.findIndex((target, index) => index > currentIndex && target.word !== null && !clearedNow.has(target.word.token));
    const fallback = practiceTargets.findIndex((target) => target.word !== null && !clearedNow.has(target.word.token));
    const target = after !== -1 ? after : fallback;
    if (target !== -1 && practiceTargets[target].key !== focusKey) advanceTimer.current = window.setTimeout(() => setFocusKey(practiceTargets[target].key), 1500);
  };
  const handlePhrasePass = (phrase: string) => {
    setClearedPhrases((current) => current.includes(phrase) ? current : [...current, phrase]);
    const currentIndex = phrasePracticeItems.indexOf(phrase);
    const nextIndex = phrasePracticeItems.findIndex((candidate, index) => index > currentIndex && !clearedPhrases.includes(candidate));
    if (nextIndex !== -1) advanceTimer.current = window.setTimeout(() => setPhraseFocusIndex(nextIndex), 1200);
  };

  const verdictContent = {
    meaning: { icon: "feedback", className: "sfc-verdict-meaning", text: null },
    vocab: { icon: "stories", className: "sfc-verdict-vocab", text: <BiLabel zh={`還缺 ${missing.length} 個詞：${missing.join("、")}`} pinyin={`Hái quē ${missing.length} ge cí: ${missing.join("、")}`} en={`${missing.length} word${missing.length > 1 ? "s" : ""} still missing: ${missing.join("、")}`} /> },
    pronounce: { icon: "voice", className: "sfc-verdict-pronounce", text: weakItems[0] ? <BiLabel zh={`生詞都用到了！現在練「${weakItems[0].token}」的聲調。`} pinyin={`Shēngcí dōu yòng dào le! Xiànzài liàn “${weakItems[0].token}” de shēngdiào.`} en={`All words used! Now practice the tone of "${weakItems[0].token}".`} /> : <BiLabel zh="再錄一次，讓聲調更清楚。" pinyin="Zài lù yí cì, ràng shēngdiào gèng qīngchu." en="Record again and make your tones clearer." /> },
    join: { icon: "analyze", className: "sfc-verdict-join", text: <BiLabel zh="每個部分都不錯！現在試著把整句連起來，說得更順。" pinyin="Měi ge bùfen dōu búcuò! Xiànzài shìzhe bǎ zhěng jù liánqǐlái, shuō de gèng shùn." en="Every part sounds good! Now try saying the whole sentence smoothly, all connected." /> },
    ready: { icon: "check", className: "sfc-verdict-ready", text: <BiLabel zh={`部分 ${selectedImageIndex + 1} 完成！可以前往下一個部分。`} pinyin={`Bùfen ${selectedImageIndex + 1} wánchéng! Kěyǐ qiánwǎng xià yí ge bùfen.`} en={`Scene ${selectedImageIndex + 1} complete! You can move on.`} /> },
  }[verdict];

  const stepBody = {
    selfEval: <SelfEvalStep onSubmit={handleSelfEvalSubmit} onSkip={() => goToStep("overview")} />,
    overview: <SpeakingResultsOverviewStep {...{ verdict, verdictContent, feedbackReliability, attempts, hasTargetScript, targetScript, recognizedText, praatMetrics, pronunciationMastery, contentNeedsRetry, selfEvalAnswer, hasScriptMismatch, submittedAudioName, practicePartCount, assistiveFeedback, analysisVersion, comparison, hasFix, hasPractice, hasPhrasePractice, goToStep, onRecordAgain }} />,
    fix: <SpeakingResultsFixStep {...{ accepted, meaningJudged, showCorrective, contentAccuracy, corrective, hasScriptMismatch, isChunked, targetScript, recognizedText, praatMetrics, chunkScores, scriptMismatches, missing, hasPractice, hasPhrasePractice, goToStep, onRecordAgain }} />,
    practice: <SpeakingResultsPracticeStep {...{ hasPhrasePractice, allDrillsCleared, practiceTargets, clearedWords, focusKey, setFocusKey, focusTarget, focusWord, onDrillPass: handleDrillPass, allPhrasesCleared, phrasePracticeItems, clearedPhrases, phraseFocusIndex, setPhraseFocusIndex, focusPhrase, onPhrasePass: handlePhrasePass, onRecordAgain }} />,
  }[step];

  return <SpeakingResultsFlowShell {...{ selectedImage, selectedImageIndex, modelAudioUrl, modelSentence, analysisAudioBlob, practicePartCount, feedbackTriggerRef, feedbackModalRef, feedbackModalCloseRef, feedbackModalOpen, onOpenFeedback: () => setFeedbackModalOpen(true), steps, step, maxVisited, setStep, stepBody, onCloseFeedback: closeFeedbackModal, praatMetrics, targetScript, recognizedText, teacherPhraseChunks, assistiveFeedback, masteryCounts, hasPhrasePractice, allPhrasesCleared, remainingPracticePhrases, ready, canContinue, masteryPassed, practiceTargets, remainingDrillTargets, attempts, assistiveRetriesUsed, onRecordAgain, hasNextScene, onNextScene, onViewSummary }} />;
}
