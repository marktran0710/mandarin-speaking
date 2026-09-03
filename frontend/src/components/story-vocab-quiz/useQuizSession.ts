import { useEffect, useRef, useState } from "react";
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
} from "../../services/database";
import {
  TIMER_TICK_MS,
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
  useEffect(() => {
    if (!storyId || !canUseDatabase()) {
      setStarsReady(true);
      return;
    }
    let cancelled = false;
    listVocabQuizAttempts(storyId, { studentId, studentName })
      .then((attempts) => {
        if (!cancelled) {
          const derived = starsFromAttempts(attempts);
          // Keep the local mirror in sync with the database-derived result,
          // so the picker and recorder agree after a learner returns on this
          // device (including after completing a quiz elsewhere).
          if (derived !== 0) recordLocalStars(storyId, derived);
          setStars((current) => derived > current ? derived : current);
        }
      })
      .catch(() => { /* localStorage stars still apply */ })
      .finally(() => { if (!cancelled) setStarsReady(true); });
    return () => { cancelled = true; };
  }, [storyId, studentId, studentName]);

  const [weakWords, setWeakWords] = useState<string[]>([]);
  const [weakWordsReady, setWeakWordsReady] = useState(false);
  useEffect(() => {
    if (!storyId || !canUseDatabase()) {
      setWeakWordsReady(true);
      return;
    }
    let cancelled = false;
    getVocabQuizWeakWords(storyId, { studentId, studentName })
      .then((words) => { if (!cancelled) setWeakWords(words); })
      .catch(() => { /* the weak-words card stays hidden */ })
      .finally(() => { if (!cancelled) setWeakWordsReady(true); });
    return () => { cancelled = true; };
  }, [storyId, studentId, studentName]);

  const sessionReady = starsReady && weakWordsReady;

  const question = questions[index];
  const isLast = questionLimit !== null && index === questionLimit - 1;
  const showFinishButton = mode === "free" && questionLimit === null;
  const weakEntries = entries.filter((entry) => weakWords.includes(entry.word));
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
    setSelected(option);
    setResults([...results, {
      word: question.word,
      correct: option === correctAnswer(question),
      timeMs: Date.now() - questionStartRef.current,
      itemId: quizItemId(baseStoryId ?? storyId ?? "unknown-story", question.word, question.kind),
      conceptId: quizConceptId(question.word), questionKind: question.kind, level,
      baseStoryId: baseStoryId ?? storyId, itemVersion: "v1",
    }]);
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
    const requestedCount = limit ?? entriesForRound.length;
    const plan = planQuizSession(shuffle(entriesForRound), picked, requestedCount,
      (entry, planMode, context) => buildQuizQuestion(entry, entriesForRound, planMode, context));
    setQuestions(plan.questions); setQuestionLimit(plan.questions.length); setRequestedQuestionCount(requestedCount);
    quizStartRef.current = Date.now(); questionStartRef.current = Date.now(); finishedRef.current = false;
  };

  const startTier = (tierMode: TierMode) => { setIsRetryRound(false); chooseMode(tierMode, entries, TIER_CONFIGS[tierMode].questionCount); };
  const practiceMissedWords = () => { setIsRetryRound(true); chooseMode("free", missedEntries, missedEntries.length); };

  return {
    screen, setScreen, mode, isRetryRound, setIsRetryRound, questionLimit, requestedQuestionCount,
    question, index, selected, results, timeLeftMs, stars, weakEntries, missedWords,
    missedEntries, isLast, showFinishButton, timeLimitMs, choose, next, finish,
    speakWord, chooseMode, startTier, practiceMissedWords, sessionReady,
  };
}
