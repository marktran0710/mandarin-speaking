import { useEffect, useRef, useState } from "react";
import {
  DIAGNOSTIC_ROUNDS,
  attemptEarnsStar,
  effectiveTimeLimitMs,
  recordLocalStars,
  type TierMode,
} from "@entities/vocabulary";
import { planQuizSession } from "@entities/vocabulary";
import {
  canUseDatabase,
  createVocabQuizAttempt,
  recordVocabQuizResponse,
} from "../../../services/database";
import {
  TIMER_TICK_MS,
  assessmentAnswerIsCorrect,
  buildMaintenanceAssessmentQuestions,
  buildDiagnosticRoundQuestions,
  buildPersonalizedAssessmentQuestions,
  MissingPracticeAssessmentError,
  buildQuizQuestion,
  quizConceptId,
  quizItemId,
  shuffle,
  validateRoundCoverage,
  type VocabQuizEntry,
  type VocabQuizMode,
  type VocabQuizQuestion,
  type VocabQuizQuestionResult,
  type VocabQuizSummary,
} from "@entities/vocabulary";
import { saveLessonAttempt } from "../model/lesson-vocab-progress";
import { VocabularyChangedError, type VocabQuizAttempt } from "../../../services/api/quiz-analytics";
import { resetLocalVocabularyProgress } from "../../../utils/serverVocabularyProgress";
import { correctAnswer, entriesInServerPriorityOrder } from "./answerKey";
import { useQuizSessionData } from "./useQuizSessionData";

export type QuizScreen = "mode-select" | "quiz" | "review" | "summary" | "challenge-entry";

type UseQuizSessionProps = {
  entries: VocabQuizEntry[];
  storyId?: string;
  baseStoryId?: string;
  vocabularyVersion?: number;
  // Story text level. Stories are single-level now, so this is always "easy";
  // kept as a field only as the fallback response level when a word has no
  // published bank question (see the numeric round metadata below).
  level: "easy";
  studentId?: string;
  studentName?: string;
  onComplete?: (summary: VocabQuizSummary) => void;
};

export { correctAnswer, entriesInServerPriorityOrder } from "./answerKey";

type PendingResponseSave = {
  attempt: VocabQuizAttempt;
  results: VocabQuizQuestionResult[];
  isLast: boolean;
};

export function useQuizSession({
  entries, storyId, baseStoryId, vocabularyVersion, level, studentId, studentName, onComplete,
}: UseQuizSessionProps) {
  const [screen, setScreen] = useState<QuizScreen>("mode-select");
  const [mode, setMode] = useState<VocabQuizMode | null>(null);
  const [roundEntries, setRoundEntries] = useState(entries);
  const [isRetryRound, setIsRetryRound] = useState(false);
  const [questionLimit, setQuestionLimit] = useState<number | null>(null);
  const [requestedQuestionCount, setRequestedQuestionCount] = useState(0);
  const [questions, setQuestions] = useState<VocabQuizQuestion[]>([]);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [results, setResults] = useState<VocabQuizQuestionResult[]>([]);
  const [isFinishing, setIsFinishing] = useState(false);
  const [vocabularyChanged, setVocabularyChanged] = useState(false);
  const [practiceError, setPracticeError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSavingResponse, setIsSavingResponse] = useState(false);
  const [timeLeftMs, setTimeLeftMs] = useState(0);
  // Lock answer handlers synchronously, including calls made before React renders.
  const questionStateRef = useRef({ index: 0, answered: false });
  const questionStartRef = useRef(Date.now());
  const quizStartRef = useRef(Date.now());
  const quizIdRef = useRef<string | null>(null);
  const attemptStartedAtRef = useRef<string | null>(null);
  const plannedQuestionCountRef = useRef(0);
  const finishedRef = useRef(false);
  // Per-answer response saves still in flight. The weak/due menu is refreshed
  // once these settle (end of round / back to modes) rather than after every
  // answer: each refresh re-runs the full server BKT replay twice
  // (weak-words + review-queue), and nothing on the quiz screen reads it.
  const pendingResponsesRef = useRef(new Set<Promise<unknown>>());
  const pendingResponseSaveRef = useRef<PendingResponseSave | null>(null);
  const pendingFinalAttemptRef = useRef<VocabQuizAttempt | null>(null);
  const responseSaveLockRef = useRef(false);
  const {
    stars,
    attempts,
    setAttempts,
    setStars,
    recordLessonEvent,
    priorityReviewWords,
    weakWords,
    masteryWords,
    strongWords,
    dueWords,
    sessionReady,
    lessonProgress,
    refreshReview,
    studentScope,
  } = useQuizSessionData({
    entries,
    storyId,
    baseStoryId,
    vocabularyVersion,
    studentId,
    studentName,
    quizIdRef,
  });
  const question = questions[index];
  const isLast = questionLimit !== null && index === questionLimit - 1;
  const showFinishButton = mode === "free" && questionLimit === null;
  // The API's wordId is the canonical concept identity. Display text is not:
  // CSV rows may use variants such as "哪裡 / 哪兒", while the mastery ledger
  // can return one normalized display form. Keep the text fallback for legacy
  // stories that have no stable ids, but never let a display-form mismatch
  // hide a real weak word from the actionable card.
  // The API returns Bottom-K in final tie-broken order. Keep that order while
  // joining it to local entries; filtering `entries` would silently reorder it.
  // Fall back to the flat weak-word list for older payloads (and tests) that
  // return only word strings without the ranked priorityReview objects.
  const rankedWeakEntries = entriesInServerPriorityOrder(entries, priorityReviewWords);
  const weakEntries = rankedWeakEntries.length > 0
    ? rankedWeakEntries
    : entries.filter((entry) => weakWords.includes(entry.word));
  // Provisional review is server-selected before the three-round diagnostic
  // unlocks the formal weak-word list. The client renders the server review
  // status and rank; it does not recreate a BKT threshold locally.
  const masteryByWordId = new Map(masteryWords.map((word) => [word.wordId, word] as const));
  const masteryByWord = new Map(masteryWords.map((word) => [word.word, word] as const));
  const interimReviewEntries = entries
    .map((entry) => {
      const mastery = (entry.wordId ? masteryByWordId.get(entry.wordId) : undefined) ?? masteryByWord.get(entry.word);
      // A word leaves this list once its provisional mastery crosses the same
      const reviewStatus = mastery?.vocabularyState?.review.status ?? mastery?.status;
      const needsReview = reviewStatus === "PROVISIONAL_REVIEW" || reviewStatus === "NEEDS_PRACTICE";
      return mastery && needsReview
        ? { entry, reviewRank: mastery.reviewRank ?? Number.MAX_SAFE_INTEGER }
        : null;
    })
    .filter((row): row is { entry: VocabQuizEntry; reviewRank: number } => row !== null)
    .sort((a, b) => a.reviewRank - b.reviewRank)
    .map((row) => row.entry);
  const missedWords = results.filter((result) => !result.correct);
  const missedEntries = roundEntries.filter((entry) => missedWords.some((result) => result.word === entry.word));
  const timeLimitMs = effectiveTimeLimitMs(mode);
  const revokeStaleSession = () => {
    setVocabularyChanged(true);
    setStars(0);
    if (baseStoryId ?? storyId) resetLocalVocabularyProgress(baseStoryId ?? storyId!);
  };

  const finish = async (finalResults: VocabQuizQuestionResult[]) => {
    if (finishedRef.current || vocabularyChanged) return;
    finishedRef.current = true;
    setIsFinishing(true);
    const correctCount = finalResults.filter((result) => result.correct).length;
    if (!isRetryRound) {
      const pendingAttempt = pendingFinalAttemptRef.current;
      const summary: VocabQuizSummary = pendingAttempt
        ? {
            mode: pendingAttempt.mode as VocabQuizMode,
            totalQuestions: pendingAttempt.totalQuestions,
            correctCount: pendingAttempt.correctCount,
            totalTimeMs: pendingAttempt.totalTimeMs,
            questionResults: pendingAttempt.questionResults as VocabQuizQuestionResult[],
          }
        : {
            mode: mode!, totalQuestions: finalResults.length, correctCount,
            totalTimeMs: Date.now() - quizStartRef.current, questionResults: finalResults,
          };
      const attempt: VocabQuizAttempt = pendingAttempt ?? {
        id: quizIdRef.current ?? `vocab-quiz-${Date.now()}`,
        storyId: baseStoryId ?? storyId ?? "lesson",
        studentName: studentName ?? "Student",
        studentId,
        vocabularyVersion,
        mode: summary.mode,
        level,
        completedAt: new Date().toISOString(),
        totalQuestions: summary.totalQuestions,
        correctCount: summary.correctCount,
        totalTimeMs: summary.totalTimeMs,
        questionResults: summary.questionResults,
      };
      if (canUseDatabase() && studentId) {
        try {
          // A completed attempt is the server completion boundary. Await it
          // before exposing the tier result so a refresh cannot race the save.
          await createVocabQuizAttempt(attempt);
        } catch (error) {
          if (error instanceof VocabularyChangedError) {
            pendingFinalAttemptRef.current = null;
            revokeStaleSession();
            setIsFinishing(false);
            return;
          }
          // Keep the exact payload and its identity so a retry is safe even if
          // the server committed it but the response was lost in transit.
          pendingFinalAttemptRef.current = attempt;
          setSaveError("Your answers are not saved yet. Please try again.");
          setIsFinishing(false);
          finishedRef.current = false;
          return;
        }
      }
      pendingFinalAttemptRef.current = null;
      setSaveError(null);
      const earned = attemptEarnsStar(mode, correctCount, finalResults.length);
      if (earned !== null) {
        if (baseStoryId ?? storyId) recordLocalStars(baseStoryId ?? storyId!, earned);
        setStars((current) => earned > current ? earned : current);
      }
      setAttempts((current) => [...current.filter((item) => item.id !== attempt.id), attempt]);
      saveLessonAttempt(studentScope, attempt.storyId, attempt);
      const completedEvent = mode === "tier1"
        ? "round1_completed"
        : mode === "tier2"
          ? "round2_completed"
          : mode === "tier3"
            ? "round3_completed"
            : mode === "weak_words"
              ? "personalized_completed"
              : mode === "challenge"
                ? "challenge_completed"
                : null;
      if (completedEvent) recordLessonEvent(completedEvent, { correctCount, totalQuestions: finalResults.length });
      onComplete?.(summary);
    }
    setScreen("summary");
  };

  const advanceAfterSavedAnswer = (nextResults: VocabQuizQuestionResult[], wasLast: boolean) => {
    if (wasLast) {
      void refreshReview();
      void finish(nextResults);
      return;
    }
    setSelected(null);
    questionStateRef.current = { index: index + 1, answered: false };
    questionStartRef.current = Date.now();
    setIndex(index + 1);
  };

  const persistPendingResponse = async () => {
    const pending = pendingResponseSaveRef.current;
    if (!pending || responseSaveLockRef.current) return;
    responseSaveLockRef.current = true;
    setIsSavingResponse(true);
    setSaveError(null);
    const saved: Promise<unknown> = recordVocabQuizResponse(pending.attempt);
    pendingResponsesRef.current.add(saved);
    try {
      await saved;
      pendingResponseSaveRef.current = null;
      advanceAfterSavedAnswer(pending.results, pending.isLast);
    } catch (error) {
      pendingResponsesRef.current.delete(saved);
      if (error instanceof VocabularyChangedError) {
        pendingResponseSaveRef.current = null;
        revokeStaleSession();
      } else {
        setSaveError("Your answer is not saved yet. Retry to continue.");
      }
    } finally {
      pendingResponsesRef.current.delete(saved);
      responseSaveLockRef.current = false;
      setIsSavingResponse(false);
    }
  };

  const retrySave = async () => {
    if (pendingFinalAttemptRef.current) {
      await finish(pendingFinalAttemptRef.current.questionResults as VocabQuizQuestionResult[]);
      return;
    }
    await persistPendingResponse();
  };

  const choose = (option: string) => {
    if (screen !== "quiz" || !question || selected !== null || finishedRef.current || vocabularyChanged
      || questionStateRef.current.index !== index || questionStateRef.current.answered) return;
    questionStateRef.current.answered = true;
    const entry = roundEntries.find((candidate) => candidate.word === question.word);
    const diagnosticMode = mode === "tier1" || mode === "tier2" || mode === "tier3";
    const assessment = question.kind === "assessment" ? question.assessment : null;
    // Assessment-backed lessons use the new three-dimension diagnostic
    // contract. Legacy story snapshots have no validated assessment bank and
    // continue through the existing planner for backward compatibility.
    const diagnosticConfig = diagnosticMode && assessment ? DIAGNOSTIC_ROUNDS[mode] : null;
    const bktType = diagnosticConfig && assessment
      ? assessment.questionType === diagnosticConfig.questionKind
      : question.kind === "translation" || question.kind === "reverse";
    const isBktEligible = Boolean(
      !isRetryRound && diagnosticMode && bktType && entry?.bktValidationStatus === "APPROVED",
    );
    const bktEligibilityErrors = isBktEligible ? [] : [
      ...(diagnosticConfig && assessment && assessment.round !== undefined && assessment.round !== diagnosticConfig.round ? ["ROUND_MISMATCH"] : []),
      ...(!diagnosticMode ? ["NON_DIAGNOSTIC_MODE"] : []),
      ...(!bktType ? ["UNSUPPORTED_BKT_QUESTION_TYPE"] : []),
      ...(entry?.bktValidationStatus !== "APPROVED" ? ["UNAPPROVED_RESEARCH_ITEM"] : []),
    ];
    const itemVersion = diagnosticConfig ? `round${diagnosticConfig.round}:v1` : `${level}:v1`;
    const itemId = assessment?.questionId
      ?? quizItemId(baseStoryId ?? storyId ?? "unknown-story", question.word, question.kind, itemVersion);
    // Weak-words/practice questions have no assessment bank, but the entry
    // still carries the stable wordId the diagnostic recorded under. Prefer it
    // over the normalized display text, otherwise practice answers accrue to a
    // different concept id (e.g. "哪裡 / 哪兒" vs "MC1_003") and a weak word can
    // never be relearned out of the list.
    const conceptId = assessment?.wordId ?? entry?.wordId ?? quizConceptId(question.word);
    const resultQuestionKind = assessment?.questionType ?? question.kind;
    const answer = correctAnswer(question);
    const activityType: VocabQuizQuestionResult["activityType"] = diagnosticConfig
      ? "diagnostic"
      : mode === "weak_words" ? "personalized_practice" : mode === "maintenance_review" ? "scheduled_maintenance" : mode === "challenge" ? "challenge" : "practice";
    const questionPrompt = assessment?.prompt ?? (question.kind === "cloze"
      ? question.sentenceWithBlank
        : question.kind === "reverse"
          ? question.translation
          : question.word);
    const answeredAt = new Date().toISOString();
    const quizId = quizIdRef.current ?? `vocab-quiz-${baseStoryId ?? storyId ?? "unknown-story"}-${Date.now()}`;
    quizIdRef.current = quizId;
    setSelected(option);
    const isCorrect = question.kind === "assessment"
      ? assessmentAnswerIsCorrect(question, option)
      : option === answer;
    const nextResults = [...results, {
      word: question.word,
      correct: isCorrect,
      timeMs: Date.now() - questionStartRef.current,
      itemId,
      conceptId, questionKind: resultQuestionKind, tier: diagnosticConfig?.mode,
      ...(!diagnosticConfig ? { level } : {}),
      round: diagnosticConfig?.round,
      knowledgeDimension: diagnosticConfig?.knowledgeDimension,
      activityType,
      baseStoryId: baseStoryId ?? storyId, itemVersion,
      isBktEligible,
      bktEligibilityErrors,
      diagnosticExposureId: diagnosticMode
        ? `${baseStoryId ?? storyId ?? "unknown-story"}:round${diagnosticConfig?.round ?? mode}:${itemId}`
        : undefined,
      assistedResponse: false,
      bktValidationStatus: entry?.bktValidationStatus,
      selectedAnswer: option,
      correctAnswer: answer,
      presentedOptions: [...question.options],
      questionPrompt,
      answeredAt,
      questionIndex: index,
      lessonId: baseStoryId ?? storyId,
      // The response ledger uses this stable id to upsert the partial answer
      // and the final attempt without counting the same answer twice.
      quizId,
    }];
    setResults(nextResults);

    // BKT evidence is recorded immediately after each eligible diagnostic
    // answer. The list remains locked for speaking until all three tiers are
    // complete, but Weak Words can now reflect the learner's latest answer.
    const shouldRecordLearningResponse = isBktEligible || mode === "weak_words" || mode === "maintenance_review";
    if (storyId && studentId && canUseDatabase() && shouldRecordLearningResponse) {
      const attempt: VocabQuizAttempt = {
        id: quizId,
        storyId,
        studentName: studentName ?? "Student",
        studentId,
        vocabularyVersion,
        mode: mode!,
        baseStoryId: baseStoryId ?? storyId,
        level,
        completedAt: attemptStartedAtRef.current ?? answeredAt,
        totalQuestions: Math.max(1, plannedQuestionCountRef.current),
        correctCount: nextResults.filter((result) => result.correct).length,
        totalTimeMs: Date.now() - quizStartRef.current,
        questionResults: nextResults,
      };
      pendingResponseSaveRef.current = { attempt, results: nextResults, isLast };
      void persistPendingResponse();
      return;
    }

    // Submit once, then advance without revealing correctness or offering a retry.
    // Keep the final answer locked until the completed attempt has been saved.
    advanceAfterSavedAnswer(nextResults, isLast);
  };

  useEffect(() => {
    if (timeLimitMs === null || screen !== "quiz" || selected) return;
    const tick = window.setInterval(() => {
      const remaining = timeLimitMs - (Date.now() - quizStartRef.current);
      if (remaining <= 0) { setTimeLeftMs(0); finish(results); return; }
      setTimeLeftMs(remaining);
    }, TIMER_TICK_MS);
    return () => window.clearInterval(tick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeLimitMs, screen, selected, index]);

  const chooseMode = (picked: VocabQuizMode, entriesForRound: VocabQuizEntry[], limit: number | null, distractorPool: VocabQuizEntry[] = entriesForRound) => {
    const hasAssessmentBank = entriesForRound.some((entry) => (entry.assessmentQuestions?.length ?? 0) > 0);
    let reviewQuestions: VocabQuizQuestion[] | null = null;
    try {
      if (picked === "weak_words" && (hasAssessmentBank || entriesForRound.some((entry) => entry.bktNextDimension))) {
        reviewQuestions = buildPersonalizedAssessmentQuestions(entriesForRound);
      } else if (picked === "maintenance_review" && hasAssessmentBank) {
        reviewQuestions = buildMaintenanceAssessmentQuestions(entriesForRound);
      }
    } catch (error) {
      if (!(error instanceof MissingPracticeAssessmentError)) throw error;
      setPracticeError(error.message);
      return;
    }
    setPracticeError(null);
    setMode(picked); setScreen("quiz"); setRoundEntries(entriesForRound); setIndex(0);
    setSelected(null); setResults([]); setIsFinishing(false); setIsSavingResponse(false); setSaveError(null); setTimeLeftMs(effectiveTimeLimitMs(picked) ?? 0);
    questionStateRef.current = { index: 0, answered: false };
    finishedRef.current = false;
    const startedEvent = picked === "tier1"
      ? "round1_started"
      : picked === "tier2"
        ? "round2_started"
        : picked === "tier3"
          ? "round3_started"
          : picked === "weak_words"
            ? "personalized_started"
            : picked === "challenge"
              ? "challenge_started"
              : null;
    if (startedEvent) recordLessonEvent(startedEvent, { totalWords: entriesForRound.length });
    if (reviewQuestions !== null) {
      const questions = reviewQuestions;
      plannedQuestionCountRef.current = questions.length;
      setQuestions(questions);
      setQuestionLimit(questions.length);
      setRequestedQuestionCount(questions.length);
      quizIdRef.current = `vocab-quiz-${baseStoryId ?? storyId ?? "unknown-story"}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      attemptStartedAtRef.current = new Date().toISOString();
      quizStartRef.current = Date.now(); questionStartRef.current = Date.now(); finishedRef.current = false;
      return;
    }
    const importedQuestions = hasAssessmentBank && (picked === "tier1" || picked === "tier2" || picked === "tier3")
      ? buildDiagnosticRoundQuestions(entriesForRound, picked)
      : [];
    if (importedQuestions.length > 0 && (picked === "tier1" || picked === "tier2" || picked === "tier3")) {
      const coverage = validateRoundCoverage({ lessonVocabulary: entriesForRound, roundQuestions: importedQuestions });
      if (!coverage.valid) throw new Error(`Diagnostic round coverage failed: ${coverage.errors.join(", ")}`);
      const questions = importedQuestions.map((assessment) => ({
        kind: "assessment" as const,
        word: assessment.targetWord,
        prompt: assessment.prompt,
        options: assessment.options,
        correctAnswer: assessment.correctAnswer,
        acceptedAnswers: assessment.acceptedAnswers,
        explanation: assessment.explanation,
        assessment,
        isAiGenerated: false as const,
      }));
      plannedQuestionCountRef.current = questions.length;
      setQuestions(questions);
      setQuestionLimit(questions.length);
      setRequestedQuestionCount(questions.length);
      quizIdRef.current = `vocab-quiz-${baseStoryId ?? storyId ?? "unknown-story"}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      attemptStartedAtRef.current = new Date().toISOString();
      quizStartRef.current = Date.now(); questionStartRef.current = Date.now(); finishedRef.current = false;
      return;
    }
    const requestedCount = limit ?? entriesForRound.length;
    const plan = planQuizSession(shuffle(entriesForRound), picked, requestedCount,
      (entry, planMode, context) => buildQuizQuestion(entry, distractorPool, planMode, context));
    plannedQuestionCountRef.current = plan.questions.length;
    setQuestions(plan.questions); setQuestionLimit(plan.questions.length); setRequestedQuestionCount(requestedCount);
    quizIdRef.current = `vocab-quiz-${baseStoryId ?? storyId ?? "unknown-story"}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    attemptStartedAtRef.current = new Date().toISOString();
    quizStartRef.current = Date.now(); questionStartRef.current = Date.now(); finishedRef.current = false;
  };

  const startTier = (tierMode: TierMode) => { setIsRetryRound(false); chooseMode(tierMode, entries, entries.length); };
  const showChallengeEntry = () => setScreen("challenge-entry");
  const startChallenge = () => {
    if (lessonProgress.challenge.attempts > 0) recordLessonEvent("challenge_retried", { attempt: lessonProgress.challenge.attempts + 1 });
    setIsRetryRound(false); chooseMode("challenge", entries, entries.length);
  };
  const practiceMissedWords = () => { setIsRetryRound(true); chooseMode("free", missedEntries, missedEntries.length); };
  // Practice one specific word on demand — e.g. a strong word that dropped
  // off the weak-word list but the learner still wants to review. Distractors
  // are drawn from the whole lesson so a single-word round still forms real
  // multiple-choice questions; the answer still feeds BKT, so getting it wrong
  // pulls the word back into the weak-word list on its own.
  const practiceWord = (target: VocabQuizEntry) => { setIsRetryRound(false); chooseMode("weak_words", [target], 1, entries); };
  const startWeakWords = async () => {
    const entriesForRound = weakEntries.length > 0 ? weakEntries : interimReviewEntries;
    if (entriesForRound.length > 0) chooseMode("weak_words", entriesForRound, entriesForRound.length, entries);
  };
  const startDueReview = () => {
    // Preserve the server's coverage/count metadata so the maintenance
    // selector rotates dimensions instead of treating every due word as unseen.
    const entriesForRound = entriesInServerPriorityOrder(entries, dueWords);
    if (entriesForRound.length > 0) chooseMode("maintenance_review", entriesForRound, entriesForRound.length, entries);
  };
  const returnToModes = () => {
    setPracticeError(null);
    setScreen("mode-select");
    if (lessonProgress.lessonCompleted) recordLessonEvent("lesson_completed", { strongWords: lessonProgress.strongWords, remainingWords: lessonProgress.remainingWords });
    // The attempt has been posted before the learner can leave the summary.
    // Refresh here so the menu reflects that newly rebuilt BKT state without
    // requiring a route reload or completion of the other diagnostic tiers.
    void Promise.allSettled([...pendingResponsesRef.current])
      .then(() => refreshReview())
      .catch(() => { /* retain the last known menu state */ });
  };

  return {
    screen, setScreen, mode, practiceError, saveError, retrySave, isRetryRound, setIsRetryRound, questionLimit, requestedQuestionCount,
    question, index, selected, results, isFinishing: isFinishing || isSavingResponse || Boolean(saveError), vocabularyChanged, timeLeftMs, stars, attempts, weakEntries, interimReviewEntries, priorityReviewWords, strongWords, dueWords, missedWords,
    missedEntries, roundEntries, isLast, showFinishButton, timeLimitMs, choose, finish,
    chooseMode, startTier, showChallengeEntry, startChallenge, practiceMissedWords, practiceWord,
    startWeakWords, startDueReview, returnToModes, sessionReady,
    lessonProgress, challengeBestScore: lessonProgress.challenge.bestScore, challengeAttempts: lessonProgress.challenge.attempts,
  };
}
