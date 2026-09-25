import { useEffect, useMemo, useState } from "react";
import type { Topic } from "@entities/topic";
import type { VocabQuizMode } from "@entities/vocabulary";
import { topicQuizEntries } from "@entities/vocabulary";
import { getStudentId, getStudentName } from "../../../utils/studentSession";
import { topicStoryId } from "../../../utils/lessonGroups";
import { markPhaseSeen } from "@shared/lib/studyProgressFlags";
import { computeRoundResult, TIER_SEQUENCE, type RoundResult } from "../model/tierRounds";
import { useQuizSession } from "./useQuizSession";

interface UseVocabQuizFlowArgs {
  topic: Topic;
  onFinished: () => void;
}

export interface PracticeResult {
  mode: VocabQuizMode;
  correctCount: number;
  totalQuestions: number;
}

export type VocabQuizFlowView = "loading" | "mode-select" | "quiz" | "round-result" | "practice-result";

/** Production quiz navigation: diagnostic BKT rounds plus server-selected
 * weak-word practice and due SM-2 maintenance review. */
export function useVocabQuizFlow({ topic, onFinished }: UseVocabQuizFlowArgs) {
  const entries = useMemo(() => topicQuizEntries(topic), [topic]);
  const session = useQuizSession({
    entries,
    storyId: topic.id,
    baseStoryId: topic.sourceStory?.id,
    level: "easy",
    studentId: getStudentId(),
    studentName: getStudentName(),
  });
  const [tierPos, setTierPos] = useState(0);
  const [roundResult, setRoundResult] = useState<RoundResult | null>(null);
  const [practiceResult, setPracticeResult] = useState<PracticeResult | null>(null);

  useEffect(() => {
    if (session.screen === "mode-select" && !roundResult && !practiceResult) {
      setTierPos(Math.min(session.stars ?? 0, TIER_SEQUENCE.length - 1));
    }
  }, [practiceResult, roundResult, session.screen, session.stars]);

  useEffect(() => {
    if (session.screen !== "summary") return;
    const diagnosticMode = session.mode === "tier1" || session.mode === "tier2" || session.mode === "tier3";
    if (diagnosticMode) {
      setRoundResult(computeRoundResult(tierPos, session.results, (session.stars ?? 0) >= tierPos + 1));
    } else if (session.mode) {
      setPracticeResult({
        mode: session.mode,
        correctCount: session.results.filter((result) => result.correct).length,
        totalQuestions: session.results.length,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.screen]);

  const startTier = () => {
    setRoundResult(null);
    setPracticeResult(null);
    session.startTier(TIER_SEQUENCE[tierPos]);
  };

  const retry = () => {
    setRoundResult(null);
    session.startTier(TIER_SEQUENCE[tierPos]);
  };

  const continueToNext = () => {
    if (!roundResult?.passed) return;
    setRoundResult(null);
    const nextPos = tierPos + 1;
    if (nextPos < TIER_SEQUENCE.length) {
      setTierPos(nextPos);
      session.startTier(TIER_SEQUENCE[nextPos]);
    } else {
      markPhaseSeen(topicStoryId(topic), "quiz");
      onFinished();
    }
  };

  const startWeakWords = () => {
    setPracticeResult(null);
    void session.startWeakWords?.();
  };

  const startDueReview = () => {
    setPracticeResult(null);
    session.startDueReview?.();
  };

  const returnToModes = () => {
    setRoundResult(null);
    setPracticeResult(null);
    session.returnToModes();
  };

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
    entries,
    tierPos,
    roundResult,
    practiceResult,
    mode: session.mode,
    retry,
    continueToNext,
    startTier,
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
    choose: session.choose,
    next: session.next,
    stars: session.stars ?? 0,
    weakEntries: session.weakEntries ?? [],
    interimReviewEntries: session.interimReviewEntries ?? [],
    dueWords: session.dueWords ?? [],
  };
}
