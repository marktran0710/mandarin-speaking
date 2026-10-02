import { useEffect, useMemo, useState } from "react";
import type { Topic } from "@entities/topic";
import type { TierMode, VocabQuizMode } from "@entities/vocabulary";
import { isTierUnlocked, latestRoundScores, topicQuizEntries } from "@entities/vocabulary";
import { getStudentId, getStudentName } from "../../../utils/studentSession";
import { topicStoryId } from "../../../utils/lessonGroups";
import { markPhaseSeen } from "@shared/lib/studyProgressFlags";
import { computeRoundResult, TIER_SEQUENCE, type RoundResult } from "../model/tierRounds";
import { useQuizSession } from "./useQuizSession";

interface UseVocabQuizFlowArgs {
  topic: Topic;
  onFinished: () => void;
  onStartPractice?: (practice: "story-speaking" | "conversation") => void;
  /** A diagnostic round was just finished (its attempt is saved). */
  onRoundCompleted?: () => void;
}

export interface PracticeResult {
  mode: VocabQuizMode;
  correctCount: number;
  totalQuestions: number;
}

export type VocabQuizFlowView = "loading" | "mode-select" | "quiz" | "round-result" | "practice-result";

/** Production quiz navigation: three diagnostic rounds finished in order
 * (the score is shown, never a gate), then any round can be redone, plus
 * server-selected weak-word practice and due SM-2 maintenance review. */
export function useVocabQuizFlow({ topic, onFinished, onStartPractice, onRoundCompleted }: UseVocabQuizFlowArgs) {
  const entries = useMemo(() => topicQuizEntries(topic), [topic]);
  const session = useQuizSession({
    entries,
    storyId: topic.id,
    baseStoryId: topic.sourceStory?.id,
    vocabularyVersion: topic.sourceStory?.vocabularyVersion ?? topic.vocabularyVersion,
    level: "easy",
    studentId: getStudentId(),
    studentName: getStudentName(),
  });
  const roundsDone = session.stars ?? 0;
  const [tierPos, setTierPos] = useState(0);
  const [roundResult, setRoundResult] = useState<RoundResult | null>(null);
  const [practiceResult, setPracticeResult] = useState<PracticeResult | null>(null);
  const latestScores = latestRoundScores(session.attempts ?? []);

  useEffect(() => {
    if (session.screen === "mode-select" && !roundResult && !practiceResult) {
      setTierPos(Math.min(roundsDone, TIER_SEQUENCE.length - 1));
    }
  }, [practiceResult, roundResult, session.screen, roundsDone]);

  useEffect(() => {
    if (session.screen !== "summary") return;
    const diagnosticMode = session.mode === "tier1" || session.mode === "tier2" || session.mode === "tier3";
    if (diagnosticMode) {
      setRoundResult(computeRoundResult(tierPos, session.results));
      onRoundCompleted?.();
    } else if (session.mode) {
      setPracticeResult({
        mode: session.mode,
        correctCount: session.results.filter((result) => result.correct).length,
        totalQuestions: session.results.length,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.screen]);

  const startRound = (tier: TierMode) => {
    const position = TIER_SEQUENCE.indexOf(tier);
    if (position < 0 || !isTierUnlocked((position + 1) as 1 | 2 | 3, roundsDone)) return;
    setRoundResult(null);
    setPracticeResult(null);
    setTierPos(position);
    session.startTier(tier);
  };

  /** The next round the learner has not finished yet (or the last round). */
  const startTier = () => startRound(TIER_SEQUENCE[Math.min(roundsDone, TIER_SEQUENCE.length - 1)]);

  const retry = () => startRound(TIER_SEQUENCE[tierPos]);

  const allRoundsDone = roundsDone >= TIER_SEQUENCE.length;

  /** From a round result: go on to the first unfinished round. */
  const continueToNext = () => {
    if (allRoundsDone) {
      returnToModes();
      return;
    }
    startRound(TIER_SEQUENCE[roundsDone]);
  };

  const finishQuiz = () => {
    markPhaseSeen(topicStoryId(topic), "quiz");
    onFinished();
  };

  const choosePractice = (practice: "story-speaking" | "conversation") => {
    markPhaseSeen(topicStoryId(topic), "quiz");
    if (onStartPractice) onStartPractice(practice);
    else onFinished();
  };

  const startWeakWords = () => {
    setPracticeResult(null);
    void session.startWeakWords?.();
  };

  const startDueReview = () => {
    setPracticeResult(null);
    session.startDueReview?.();
  };

  function returnToModes() {
    setRoundResult(null);
    setPracticeResult(null);
    session.returnToModes();
  }

  const ready = session.sessionReady !== false;
  const view: VocabQuizFlowView = !ready
    ? "loading"
    : roundResult
      ? "round-result"
      : practiceResult
        ? "practice-result"
        : session.screen === "mode-select"
          ? "mode-select"
          : session.screen === "quiz" && session.question
            ? "quiz"
            : "loading";

  return {
    view,
    vocabularyChanged: session.vocabularyChanged,
    practiceError: session.practiceError,
    entries,
    tierPos,
    roundsDone,
    allRoundsDone,
    latestScores,
    roundResult,
    practiceResult,
    mode: session.mode,
    retry,
    continueToNext,
    finishQuiz,
    choosePractice,
    startTier,
    startRound,
    startWeakWords,
    startDueReview,
    returnToModes,
    question: session.question,
    index: session.index,
    questionLimit: session.questionLimit,
    timeLeftMs: session.timeLeftMs,
    timeLimitMs: session.timeLimitMs,
    selected: session.selected,
    results: session.results,
    isFinishing: session.isFinishing,
    choose: session.choose,
    stars: roundsDone,
    weakEntries: session.weakEntries ?? [],
    interimReviewEntries: session.interimReviewEntries ?? [],
    dueWords: session.dueWords ?? [],
  };
}
