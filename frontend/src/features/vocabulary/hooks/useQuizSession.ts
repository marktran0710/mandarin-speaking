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
  type VocabPriorityReviewWord,
} from "../../../services/database";
import {
  TIMER_TICK_MS,
  assessmentAnswerIsCorrect,
  buildMaintenanceAssessmentQuestions,
  buildDiagnosticRoundQuestions,
  buildPersonalizedAssessmentQuestions,
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
import { postResearchPracticeSession } from "../../../services/api/vocabulary-research";
import { getCachedResearchContext } from "../../../utils/researchContext";
import { saveLessonAttempt } from "../model/lesson-vocab-progress";
import type { VocabQuizAttempt } from "../../../services/api/quiz-analytics";
import { useQuizSessionData } from "./useQuizSessionData";

export type QuizScreen = "mode-select" | "quiz" | "review" | "summary" | "challenge-entry";

type UseQuizSessionProps = {
  entries: VocabQuizEntry[];
  storyId?: string;
  baseStoryId?: string;
  // Story text level. Stories are single-level now, so this is always "easy";
  // kept as a field only as the fallback response level when a word has no
  // published bank question (see the numeric round metadata below).
  level: "easy";
  studentId?: string;
  studentName?: string;
  onComplete?: (summary: VocabQuizSummary) => void;
};

export function correctAnswer(question: VocabQuizQuestion) {
  switch (question.kind) {
    case "translation": return question.correctTranslation;
    case "cloze": return question.correctWord;
    case "pinyin": return question.correctPinyin;
    case "pos": return question.correctPos;
    case "synonym": return question.correctSynonym;
    case "reverse":
    case "listening": return question.correctWord;
    case "assessment": return question.correctAnswer;
  }
}

export function entriesInServerPriorityOrder(entries: VocabQuizEntry[], priorityReviewWords: VocabPriorityReviewWord[]): VocabQuizEntry[] {
  return priorityReviewWords.flatMap((priorityWord) => {
    const entry = entries.find((candidate) => candidate.wordId === priorityWord.wordId)
      ?? entries.find((candidate) => candidate.word === priorityWord.word);
    if (!entry) return [];
    return priorityWord.seenQuestionTypes?.length || priorityWord.failedQuestionTypes?.length
      ? [{
        ...entry,
        bktSeenQuestionKinds: priorityWord.seenQuestionTypes as VocabQuizEntry["bktSeenQuestionKinds"],
        bktFailedQuestionKinds: priorityWord.failedQuestionTypes as VocabQuizEntry["bktFailedQuestionKinds"],
        bktObservationCount: priorityWord.observationCount,
        bktLastResponseAt: priorityWord.lastResponseAt,
      }]
      : [entry];
  });
}

export function useQuizSession({
  entries, storyId, baseStoryId, level, studentId, studentName, onComplete,
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
  const [timeLeftMs, setTimeLeftMs] = useState(0);
  const questionStartRef = useRef(Date.now());
  const quizStartRef = useRef(Date.now());
  const quizIdRef = useRef<string | null>(null);
  const attemptStartedAtRef = useRef<string | null>(null);
  const plannedQuestionCountRef = useRef(0);
  const finishedRef = useRef(false);
  const {
    stars,
    setAttempts,
    setStars,
    recordLessonEvent,
    priorityReviewWords,
    weakWords,
    masteryWords,
    strongWords,
    dueWords,
    researchDueEntries,
    sessionReady,
    lessonProgress,
    refreshWeakWords,
    refreshDueWords,
    studentScope,
  } = useQuizSessionData({
    entries,
    storyId,
    baseStoryId,
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

  const finish = async (finalResults: VocabQuizQuestionResult[]) => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    const correctCount = finalResults.filter((result) => result.correct).length;
    if (!isRetryRound) {
      const earned = attemptEarnsStar(mode, correctCount, finalResults.length);
      if (earned !== null) {
        if (baseStoryId ?? storyId) recordLocalStars(baseStoryId ?? storyId!, earned);
        setStars((current) => earned > current ? earned : current);
      }
      const summary: VocabQuizSummary = {
        mode: mode!, totalQuestions: finalResults.length, correctCount,
        totalTimeMs: Date.now() - quizStartRef.current, questionResults: finalResults,
      };
      const attempt: VocabQuizAttempt = {
        id: quizIdRef.current ?? `vocab-quiz-${Date.now()}`,
        storyId: baseStoryId ?? storyId ?? "lesson",
        studentName: studentName ?? "Student",
        studentId,
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
        } catch {
          // The local snapshot remains a recoverable migration queue. It will
          // be POST-validated the next time progression is read.
        }
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

  const choose = (option: string) => {
    if (selected) return;
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
    const nextResults = [...results, {
      word: question.word,
      correct: question.kind === "assessment"
        ? assessmentAnswerIsCorrect(question, option)
        : option === answer,
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
      void recordVocabQuizResponse({
        id: quizId,
        storyId,
        studentName: studentName ?? "Student",
        studentId,
        mode: mode!,
        baseStoryId: baseStoryId ?? storyId,
        level,
        completedAt: attemptStartedAtRef.current ?? answeredAt,
        totalQuestions: Math.max(1, plannedQuestionCountRef.current),
        correctCount: nextResults.filter((result) => result.correct).length,
        totalTimeMs: Date.now() - quizStartRef.current,
        questionResults: nextResults,
      })
      .then(() => Promise.all([refreshWeakWords(), refreshDueWords()]))
        .catch(() => { /* final attempt persistence remains the fallback */ });
    }
  };

  const next = () => {
    setSelected(null);
    if (isLast) return void finish(results);
    questionStartRef.current = Date.now();
    setIndex(index + 1);
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
    setMode(picked); setScreen("quiz"); setRoundEntries(entriesForRound); setIndex(0);
    setSelected(null); setResults([]); setTimeLeftMs(effectiveTimeLimitMs(picked) ?? 0);
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
    const hasAssessmentBank = entriesForRound.some((entry) => (entry.assessmentQuestions?.length ?? 0) > 0);
    if ((picked === "weak_words" || picked === "maintenance_review") && hasAssessmentBank) {
      const questions = picked === "weak_words"
        ? buildPersonalizedAssessmentQuestions(entriesForRound)
        : buildMaintenanceAssessmentQuestions(entriesForRound);
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
  // Epic 4: a research participant's practice round uses server-selected
  // words (the equal-budget BKT selection), never the client's own
  // accuracy-derived weakEntries. The quiz-taking mechanics stay the
  // existing "weak_words" flow - only word selection differs.
  const startResearchPractice = async () => {
    setIsRetryRound(false);
    try {
      const { wordIds } = await postResearchPracticeSession();
      const byWordId = new Map(entries.map((entry) => [entry.wordId ?? entry.word, entry]));
      const matched = wordIds.map((wordId) => byWordId.get(wordId)).filter((entry): entry is VocabQuizEntry => Boolean(entry));
      if (matched.length > 0) chooseMode("weak_words", matched, matched.length, entries);
    } catch {
      // Never strand the student on a dead button if the research endpoint
      // fails - fall back to the ordinary weak-words flow.
      if (weakEntries.length > 0) chooseMode("weak_words", weakEntries, weakEntries.length);
    }
  };
  // Epic 5: a research participant's "Review today" round uses the
  // already-fetched research retention due list (read-only, prefetched
  // above), never production's due-words queue.
  const startResearchReview = () => {
    setIsRetryRound(false);
    if (researchDueEntries.length > 0) chooseMode("maintenance_review", researchDueEntries, researchDueEntries.length);
  };
  const startWeakWords = async () => {
    if (getCachedResearchContext().active) {
      await startResearchPractice();
      return;
    }
    const entriesForRound = weakEntries.length > 0 ? weakEntries : interimReviewEntries;
    if (entriesForRound.length > 0) chooseMode("weak_words", entriesForRound, entriesForRound.length, entries);
  };
  const startDueReview = () => {
    if (getCachedResearchContext().active) {
      startResearchReview();
      return;
    }
    const byWordId = new Map(entries.map((entry) => [entry.wordId ?? entry.word, entry]));
    const entriesForRound = dueWords
      .map((item) => byWordId.get(item.wordId) ?? entries.find((entry) => entry.word === item.word))
      .filter((entry): entry is VocabQuizEntry => Boolean(entry));
    if (entriesForRound.length > 0) chooseMode("maintenance_review", entriesForRound, entriesForRound.length, entries);
  };
  const returnToModes = () => {
    setScreen("mode-select");
    if (lessonProgress.lessonCompleted) recordLessonEvent("lesson_completed", { strongWords: lessonProgress.strongWords, remainingWords: lessonProgress.remainingWords });
    // The attempt has been posted before the learner can leave the summary.
    // Refresh here so the menu reflects that newly rebuilt BKT state without
    // requiring a route reload or completion of the other diagnostic tiers.
    void Promise.all([refreshWeakWords(), refreshDueWords()]).catch(() => { /* retain the last known menu state */ });
  };

  return {
    screen, setScreen, mode, isRetryRound, setIsRetryRound, questionLimit, requestedQuestionCount,
    question, index, selected, results, timeLeftMs, stars, weakEntries, interimReviewEntries, priorityReviewWords, strongWords, dueWords, missedWords,
    missedEntries, roundEntries, isLast, showFinishButton, timeLimitMs, choose, next, finish,
    chooseMode, startTier, showChallengeEntry, startChallenge, practiceMissedWords, practiceWord,
    startResearchPractice, researchDueEntries, startResearchReview, startWeakWords, startDueReview, returnToModes, sessionReady,
    lessonProgress, challengeBestScore: lessonProgress.challenge.bestScore, challengeAttempts: lessonProgress.challenge.attempts,
  };
}
