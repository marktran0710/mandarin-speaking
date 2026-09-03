import { useCallback, useEffect, useRef, useState } from "react";
import {
  TIER_CONFIGS,
  attemptEarnsStar,
  loadLocalStars,
  recordLocalStars,
  starsFromAttempts,
  tierConfigFromMode,
  type QuizTier,
  type TierMode,
} from "../../utils/quizTiers";
import { planQuizSession } from "../../utils/quizSessionPlanner";
import {
  canUseDatabase,
  getVocabQuizWeakWords,
  listVocabQuizAttempts,
  recordVocabQuizResponse,
  type VocabPriorityReviewWord,
} from "../../services/database";
import {
  TIMER_TICK_MS,
  assessmentAnswerIsCorrect,
  buildAssessmentQuestions,
  buildQuizQuestion,
  canUseSpeechSynthesis,
  quizConceptId,
  quizItemId,
  shuffle,
  type VocabQuizEntry,
  type VocabQuizMode,
  type VocabQuizQuestion,
  type VocabQuizQuestionResult,
  type VocabQuizSummary,
} from "./model";

export type QuizScreen = "mode-select" | "quiz" | "review" | "summary";

type UseQuizSessionProps = {
  entries: VocabQuizEntry[];
  storyId?: string;
  baseStoryId?: string;
  level: "easy" | "medium" | "hard";
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
  const [stars, setStars] = useState<0 | QuizTier>(() => storyId ? loadLocalStars(storyId) : 0);

  // starsReady/weakWordsReady: the mode-select screen used to mount
  // immediately with stars=0 and no "弱項複習 Weak words" card, then have
  // both pop in late once these two fetches resolved — exactly the
  // piecemeal-loading pattern flagged elsewhere in this app. sessionReady
  // below lets the screen wait for both to settle before it ever paints,
  // the same "load fully, then show" discipline used by App.tsx and
  // StoryRecorderRuntime.
  const [starsReady, setStarsReady] = useState(false);
  const hasApprovedMaterial = entries.some(
    (entry) => entry.bktValidationStatus === "APPROVED",
  );
  useEffect(() => {
    if (!storyId || !canUseDatabase()) {
      setStarsReady(true);
      return;
    }
    let cancelled = false;
    listVocabQuizAttempts(storyId, { studentId, studentName })
      .then((attempts) => {
        if (!cancelled) {
          // Once an approved assessment bank is attached to the story, old
          // draft-material attempts must not mark the new CSV rounds as
          // complete. Those attempts are intentionally excluded from BKT by
          // the server as well, so using them for stars creates the misleading
          // "all rounds complete, no weak words" state.
          const progressAttempts = hasApprovedMaterial
            ? attempts.filter((attempt) =>
              Boolean(
                attempt.questionResults?.length &&
                attempt.questionResults.every(
                  (result) => result.bktValidationStatus === "APPROVED",
                ),
              ),
            )
            : attempts;
          const derived = starsFromAttempts(progressAttempts);
          // Keep the local mirror in sync with the database-derived result,
          // so the picker and recorder agree after a learner returns on this
          // device (including after completing a quiz elsewhere).
          if (derived !== 0) recordLocalStars(storyId, derived);
          // A successful database read is authoritative for this student and
          // story. Do not keep a stale local max here: it can mark all rounds
          // complete even when this learner has no passed round on the server.
          setStars(derived);
        }
      })
      .catch(() => { /* localStorage stars still apply */ })
      .finally(() => { if (!cancelled) setStarsReady(true); });
    return () => { cancelled = true; };
  }, [hasApprovedMaterial, storyId, studentId, studentName]);

  const [weakWords, setWeakWords] = useState<string[]>([]);
  const [priorityReviewWords, setPriorityReviewWords] = useState<VocabPriorityReviewWord[]>([]);
  const [weakWordsReady, setWeakWordsReady] = useState(false);
  const refreshWeakWords = useCallback(async () => {
    if (!storyId || !canUseDatabase()) return;
    // Weak Words is a story-wide summary. Medium/Hard topic ids are only
    // presentation tiers, so the API must receive the source story id and
    // aggregate every tier into one learner list.
    const words = await getVocabQuizWeakWords(baseStoryId ?? storyId, { studentId, studentName });
    setWeakWords(words);
    setPriorityReviewWords(words.priorityReview ?? []);
  }, [storyId, baseStoryId, studentId, studentName]);
  useEffect(() => {
    if (!storyId || !canUseDatabase()) {
      setWeakWordsReady(true);
      return;
    }
    let cancelled = false;
    refreshWeakWords()
      .catch(() => { /* the always-visible card falls back to its empty state */ })
      .finally(() => { if (!cancelled) setWeakWordsReady(true); });
    return () => { cancelled = true; };
  }, [storyId, refreshWeakWords]);

  const sessionReady = starsReady && weakWordsReady;

  const question = questions[index];
  const isLast = questionLimit !== null && index === questionLimit - 1;
  const showFinishButton = mode === "free" && questionLimit === null;
  // The API's wordId is the canonical concept identity. Display text is not:
  // CSV rows may use variants such as "哪裡 / 哪兒", while the mastery ledger
  // can return one normalized display form. Keep the text fallback for legacy
  // stories that have no stable ids, but never let a display-form mismatch
  // hide a real weak word from the actionable card.
  const priorityByWordId = new Map(priorityReviewWords.map((word) => [word.wordId, word]));
  const priorityByWord = new Map(priorityReviewWords.map((word) => [word.word, word]));
  const weakEntries = entries.filter((entry) => {
    const matchesPriorityId = Boolean(entry.wordId && priorityByWordId.has(entry.wordId));
    return matchesPriorityId || weakWords.includes(entry.word);
  }).map((entry) => {
    const reviewWord = (entry.wordId ? priorityByWordId.get(entry.wordId) : undefined)
      ?? priorityByWord.get(entry.word);
    return reviewWord?.seenQuestionTypes?.length
      ? { ...entry, bktSeenQuestionKinds: reviewWord.seenQuestionTypes as VocabQuizEntry["bktSeenQuestionKinds"] }
      : entry;
  });
  const missedWords = results.filter((result) => !result.correct);
  const missedEntries = roundEntries.filter((entry) => missedWords.some((result) => result.word === entry.word));
  const timeLimitMs = tierConfigFromMode(mode)?.timeLimitMs ?? null;

  const finish = (finalResults: VocabQuizQuestionResult[]) => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    const correctCount = finalResults.filter((result) => result.correct).length;
    if (!isRetryRound) {
      const earned = attemptEarnsStar(mode, correctCount, finalResults.length);
      if (earned !== null) {
        if (storyId) recordLocalStars(storyId, earned);
        setStars((current) => earned > current ? earned : current);
      }
      onComplete?.({
        mode: mode!, totalQuestions: finalResults.length, correctCount,
        totalTimeMs: Date.now() - quizStartRef.current, questionResults: finalResults,
      });
    }
    setScreen("summary");
  };

  const choose = (option: string) => {
    if (selected) return;
    const entry = roundEntries.find((candidate) => candidate.word === question.word);
    const bktType = question.kind === "translation" || question.kind === "reverse" || question.kind === "listening"
      || (question.kind === "assessment" && question.assessment.level === "easy");
    const diagnosticMode = mode === "tier1" || mode === "tier2" || mode === "tier3";
    const isBktEligible = Boolean(
      !isRetryRound && level === "easy" && diagnosticMode && bktType && entry?.bktValidationStatus === "APPROVED",
    );
    const bktEligibilityErrors = isBktEligible ? [] : [
      ...(level !== "easy" ? ["NON_DIAGNOSTIC_LEVEL"] : []),
      ...(!diagnosticMode ? ["NON_DIAGNOSTIC_MODE"] : []),
      ...(!bktType ? ["UNSUPPORTED_BKT_QUESTION_TYPE"] : []),
      ...(entry?.bktValidationStatus !== "APPROVED" ? ["UNAPPROVED_RESEARCH_ITEM"] : []),
    ];
    const itemVersion = `${level}:v1`;
    const assessment = question.kind === "assessment" ? question.assessment : null;
    const resultLevel = assessment?.level ?? level;
    const itemId = assessment?.questionId
      ?? quizItemId(baseStoryId ?? storyId ?? "unknown-story", question.word, question.kind, itemVersion);
    const conceptId = assessment?.wordId ?? quizConceptId(question.word);
    const resultQuestionKind = assessment?.questionType ?? question.kind;
    const answer = correctAnswer(question);
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
      conceptId, questionKind: resultQuestionKind, level: resultLevel,
      baseStoryId: baseStoryId ?? storyId, itemVersion,
      isBktEligible,
      bktEligibilityErrors,
      diagnosticExposureId: diagnosticMode
        ? `${baseStoryId ?? storyId ?? "unknown-story"}:${resultLevel}:${mode}:${itemId}`
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
    if (storyId && studentId && canUseDatabase() && isBktEligible) {
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
        .then(() => refreshWeakWords())
        .catch(() => { /* final attempt persistence remains the fallback */ });
    }
  };

  const next = () => {
    setSelected(null);
    if (isLast) return finish(results);
    questionStartRef.current = Date.now();
    setIndex(index + 1);
  };

  const speakWord = (text: string) => {
    if (!canUseSpeechSynthesis()) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "zh-TW";
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
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

  useEffect(() => {
    if (screen === "quiz" && question?.kind === "listening" && !selected) speakWord(question.correctWord);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, index, question?.kind]);

  const chooseMode = (picked: VocabQuizMode, entriesForRound: VocabQuizEntry[], limit: number | null) => {
    setMode(picked); setScreen("quiz"); setRoundEntries(entriesForRound); setIndex(0);
    setSelected(null); setResults([]); setTimeLeftMs(tierConfigFromMode(picked)?.timeLimitMs ?? 0);
    const assessmentLevel = picked === "tier1" ? "easy" : picked === "tier2" ? "medium" : picked === "tier3" ? "hard" : null;
    const importedQuestions = assessmentLevel
      ? buildAssessmentQuestions(entriesForRound, assessmentLevel)
      : [];
    if (importedQuestions.length > 0) {
      plannedQuestionCountRef.current = importedQuestions.length;
      setQuestions(importedQuestions);
      setQuestionLimit(importedQuestions.length);
      setRequestedQuestionCount(importedQuestions.length);
      quizIdRef.current = `vocab-quiz-${baseStoryId ?? storyId ?? "unknown-story"}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      attemptStartedAtRef.current = new Date().toISOString();
      quizStartRef.current = Date.now(); questionStartRef.current = Date.now(); finishedRef.current = false;
      return;
    }
    const requestedCount = limit ?? entriesForRound.length;
    const plan = planQuizSession(shuffle(entriesForRound), picked, requestedCount,
      (entry, planMode, context) => buildQuizQuestion(entry, entriesForRound, planMode, context));
    plannedQuestionCountRef.current = plan.questions.length;
    setQuestions(plan.questions); setQuestionLimit(plan.questions.length); setRequestedQuestionCount(requestedCount);
    quizIdRef.current = `vocab-quiz-${baseStoryId ?? storyId ?? "unknown-story"}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    attemptStartedAtRef.current = new Date().toISOString();
    quizStartRef.current = Date.now(); questionStartRef.current = Date.now(); finishedRef.current = false;
  };

  const startTier = (tierMode: TierMode) => { setIsRetryRound(false); chooseMode(tierMode, entries, TIER_CONFIGS[tierMode].questionCount); };
  const practiceMissedWords = () => { setIsRetryRound(true); chooseMode("free", missedEntries, missedEntries.length); };
  const returnToModes = () => {
    setScreen("mode-select");
    // The attempt has been posted before the learner can leave the summary.
    // Refresh here so the menu reflects that newly rebuilt BKT state without
    // requiring a route reload or completion of the other diagnostic tiers.
    void refreshWeakWords().catch(() => { /* retain the last known menu state */ });
  };

  return {
    screen, setScreen, mode, isRetryRound, setIsRetryRound, questionLimit, requestedQuestionCount,
    question, index, selected, results, timeLeftMs, stars, weakEntries, priorityReviewWords, missedWords,
    missedEntries, isLast, showFinishButton, timeLimitMs, choose, next, finish,
    speakWord, chooseMode, startTier, practiceMissedWords, returnToModes, sessionReady,
  };
}
