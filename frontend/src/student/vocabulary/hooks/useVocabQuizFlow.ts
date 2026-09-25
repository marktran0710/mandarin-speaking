import { useEffect, useMemo, useState } from "react";
import type { Topic } from "../../../components/content/topic-selector/types";
import { topicQuizEntries } from "../../../utils/topicQuiz";
import { useQuizSession } from "./useQuizSession";
import { getStudentId, getStudentName } from "../../../utils/studentSession";
import { topicStoryId } from "../../../utils/lessonGroups";
import { markPhaseSeen } from "../../studyProgressFlags";
import { computeRoundResult, TIER_SEQUENCE, type RoundResult } from "../model/tierRounds";

interface UseVocabQuizFlowArgs {
  topic: Topic;
  onFinished: () => void;
}

export type VocabQuizFlowView = "loading" | "quiz" | "round-result";

/**
 * Owns the tier1->tier2->tier3 sequencing on top of the raw useQuizSession
 * state machine: each tier must actually be passed (a real star earned) to
 * advance — failing one surfaces a round-result view with a retry action
 * instead of silently continuing. onFinished() is reachable only once
 * tier3's star is confirmed, restoring the gate practiceUnlocked()/
 * PRACTICE_UNLOCK_STARS already enforce everywhere else in the app.
 */
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

  useEffect(() => {
    if (session.screen === "mode-select") {
      session.startTier(TIER_SEQUENCE[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.screen]);

  // Every tier's summary stops here now instead of auto-advancing — passed
  // reflects whatever useQuizSession's own finish()/attemptEarnsStar just
  // decided (session.stars is updated in the same batch as screen), never
  // re-derived independently.
  useEffect(() => {
    if (session.screen !== "summary") return;
    const passed = session.stars >= tierPos + 1;
    setRoundResult(computeRoundResult(tierPos, session.results, passed));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.screen]);

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

  const view: VocabQuizFlowView = roundResult
    ? "round-result"
    : session.screen === "quiz" && session.question
      ? "quiz"
      : "loading";

  return {
    view,
    entries,
    tierPos,
    roundResult,
    retry,
    continueToNext,
    question: session.question,
    index: session.index,
    questionLimit: session.questionLimit,
    selected: session.selected,
    results: session.results,
    choose: session.choose,
    next: session.next,
  };
}
