import { useCallback, useEffect, useRef, useState } from "react";
import { canUseDatabase } from "@shared/api/client";
import {
  answerVocabReviewSessionQuestion,
  deferVocabReviewSession,
  getVocabQuizReviewQueue,
  startOrResumeVocabReviewSession,
  type ReviewQueueItem,
  type VocabReviewSession,
  type VocabReviewSessionAnswerResult,
  VocabReviewSessionError,
} from "../../../services/api/quiz-analytics";

type PendingAnswer = {
  sessionId: string;
  slotId: string;
  selectedAnswer: string;
  responseTimeMs: number;
};

export function useCombinedReviewSession(studentId?: string) {
  const [session, setSession] = useState<VocabReviewSession | null>(null);
  const [lastResult, setLastResult] = useState<VocabReviewSessionAnswerResult | null>(null);
  const [weakCount, setWeakCount] = useState(0);
  const [dueCount, setDueCount] = useState(0);
  const [queueReady, setQueueReady] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const pendingAnswerRef = useRef<PendingAnswer | null>(null);

  const refreshQueue = useCallback(async () => {
    setQueueReady(false);
    if (!studentId || !canUseDatabase()) {
      setWeakCount(0);
      setDueCount(0);
      setQueueReady(true);
      return;
    }
    try {
      const queue = await getVocabQuizReviewQueue(undefined, studentId, {
        includeAllWeak: true,
        scope: "all_learned",
      });
      setWeakCount(queue.queue.filter((item: ReviewQueueItem) => item.reviewReason === "weak").length);
      setDueCount(queue.queue.filter((item: ReviewQueueItem) => item.reviewReason === "due").length);
    } catch {
      // The optional review path stays unavailable until its authoritative
      // queue can be read; it never falls back to client-selected questions.
      setWeakCount(0);
      setDueCount(0);
    } finally {
      setQueueReady(true);
    }
  }, [studentId]);

  useEffect(() => { void refreshQueue(); }, [refreshQueue]);

  const start = useCallback(async () => {
    if (!studentId || !canUseDatabase()) return null;
    setIsStarting(true);
    setError(null);
    setLastResult(null);
    pendingAnswerRef.current = null;
    try {
      const response = await startOrResumeVocabReviewSession(studentId);
      setSession(response.session);
      return response.session;
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error("Could not start review."));
      return null;
    } finally {
      setIsStarting(false);
    }
  }, [studentId]);

  const sendPendingAnswer = useCallback(async () => {
    const pending = pendingAnswerRef.current;
    if (!studentId || !pending) return false;
    setIsSubmitting(true);
    setError(null);
    try {
      const response = await answerVocabReviewSessionQuestion(studentId, pending.sessionId, {
        slotId: pending.slotId,
        selectedAnswer: pending.selectedAnswer,
        responseTimeMs: pending.responseTimeMs,
      });
      setSession(response.session);
      setLastResult(response.result);
      setDueCount((count) => Math.max(0, count - Number(response.result.reviewReason === "due")));
      setWeakCount((count) => Math.max(0, count - Number(response.result.reviewReason === "weak")));
      pendingAnswerRef.current = null;
      if (response.session.status === "completed") void refreshQueue();
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error("Could not save this review answer."));
      return false;
    } finally {
      setIsSubmitting(false);
    }
  }, [studentId, refreshQueue]);

  const submit = useCallback(async (selectedAnswer: string, responseTimeMs: number) => {
    const question = session?.currentQuestion;
    if (!session || !question || pendingAnswerRef.current || lastResult) return false;
    pendingAnswerRef.current = {
      sessionId: session.sessionId,
      slotId: question.slotId,
      selectedAnswer,
      responseTimeMs,
    };
    return sendPendingAnswer();
  }, [lastResult, sendPendingAnswer, session]);

  const retrySave = useCallback(() => sendPendingAnswer(), [sendPendingAnswer]);

  const continueAfterFeedback = useCallback(() => {
    setLastResult(null);
    setError(null);
  }, []);

  const defer = useCallback(async () => {
    if (!studentId || !session) return false;
    setError(null);
    try {
      await deferVocabReviewSession(studentId, session.sessionId);
      setSession(null);
      setLastResult(null);
      pendingAnswerRef.current = null;
      await refreshQueue();
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error("Could not end this review session."));
      return false;
    }
  }, [refreshQueue, session, studentId]);

  const discardStaleSession = useCallback(async () => {
    const closed = await defer();
    if (closed) await refreshQueue();
    return closed;
  }, [defer, refreshQueue]);

  const clearError = useCallback(() => setError(null), []);

  return {
    session,
    question: session?.currentQuestion ?? null,
    lastResult,
    weakCount,
    dueCount,
    availableCount: weakCount + dueCount,
    queueReady,
    isStarting,
    isSubmitting,
    error,
    stale: error instanceof VocabReviewSessionError && error.code === "STALE_VOCABULARY",
    start,
    submit,
    retrySave,
    continueAfterFeedback,
    defer,
    discardStaleSession,
    clearError,
    refreshQueue,
  };
}
