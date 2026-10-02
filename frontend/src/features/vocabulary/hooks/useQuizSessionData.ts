import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import {
  loadLocalStars,
  starsFromAttempts,
  type QuizTier,
  type VocabQuizEntry,
} from "@entities/vocabulary";
import {
  canUseDatabase,
  getVocabQuizReviewQueue,
  getVocabQuizWeakWords,
  getVocabularyProgression,
  listVocabQuizAttempts,
  type ReviewQueueItem,
  type VocabPriorityReviewWord,
} from "../../../services/database";
import { getStudentScopeKey } from "../../../utils/studentSession";
import { syncServerVocabularyProgress } from "../../../utils/serverVocabularyProgress";
import {
  buildLessonVocabularyProgress,
  loadLessonProgressSnapshot,
  type LessonVocabularyProgress,
} from "../model/lesson-vocab-progress";
import { weakWordsResultFromPriorityReview, type VocabPriorityReviewResponse, type VocabQuizAttempt, type VocabWeakWordsResult } from "../../../services/api/quiz-analytics";
import { createMeasurementEvent, recordMeasurementEvent, type MeasurementEventName } from "../../../utils/measurement";

type QuizSessionDataProps = {
  entries: VocabQuizEntry[];
  storyId?: string;
  baseStoryId?: string;
  vocabularyVersion?: number;
  studentId?: string;
  studentName?: string;
  quizIdRef: RefObject<string | null>;
};

export function useQuizSessionData({
  entries,
  storyId,
  baseStoryId,
  vocabularyVersion,
  studentId,
  studentName,
  quizIdRef,
}: QuizSessionDataProps) {
  const canonicalStoryId = baseStoryId ?? storyId;
  const [stars, setStars] = useState<0 | QuizTier>(() => (
    canonicalStoryId && !(studentId && canUseDatabase()) ? loadLocalStars(canonicalStoryId) : 0
  ));
  const [serverProgression, setServerProgression] = useState<import("../../../services/api/quiz-analytics").VocabularyProgression | null>(null);
  const studentScope = studentId || studentName || getStudentScopeKey();
  const [attempts, setAttempts] = useState<VocabQuizAttempt[]>(() => (
    storyId ? loadLessonProgressSnapshot(studentScope, baseStoryId ?? storyId, vocabularyVersion).attempts ?? [] : []
  ));
  const recordLessonEvent = (name: MeasurementEventName, properties: Record<string, string | number | boolean | null> = {}) => {
    if (!storyId) return;
    recordMeasurementEvent(createMeasurementEvent(name, {
      studentId,
      topicId: baseStoryId ?? storyId,
      attemptId: quizIdRef.current,
      properties,
    }));
  };

  useEffect(() => {
    recordLessonEvent("lesson_started", { totalWords: entries.length });
    // This is a session-level event; quiz answer events are emitted below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storyId, baseStoryId]);

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
    const loadAuthoritativeProgress = async () => {
      // The attempts list and the validated progression are independent
      // reads, so start both now instead of chaining them (one round trip
      // saved on every quiz open). Progression is only ever used when the
      // attempts read succeeds, exactly as before.
      type Progression = import("../../../services/api/quiz-analytics").VocabularyProgression;
      const progressionRequest: Promise<Progression | null> = studentId && canonicalStoryId
        ? getVocabularyProgression(canonicalStoryId, studentId).catch(() => null)
        : Promise.resolve(null);
      let serverAttempts: VocabQuizAttempt[];
      try {
        serverAttempts = await listVocabQuizAttempts(canonicalStoryId, { studentId, studentName });
      } catch {
        // A signed-in student's cached stars cannot open a gate whose
        // validated server evidence is unavailable.
        if (!cancelled) setStarsReady(true);
        return;
      }

      // Missing server attempts may have been deliberately reset/deleted.
      // Read the current server history; never restore a local mirror by POST.

      let derived: 0 | QuizTier;
      let progression: import("../../../services/api/quiz-analytics").VocabularyProgression | null = null;
      if (studentId && canonicalStoryId) {
        progression = await progressionRequest;
        // Authenticated progression needs the validated response ledger.
        // A raw attempt's client-side score cannot replace that read, so a
        // failed progression read leaves the stars at 0.
        derived = progression ? progression.quizStars : 0;
      } else {
        const progressAttempts = hasApprovedMaterial
          ? serverAttempts.filter((attempt) => Boolean(attempt.questionResults?.length && attempt.questionResults.every((result) => result.bktValidationStatus === "APPROVED")))
          : serverAttempts;
        derived = starsFromAttempts(progressAttempts);
      }

      if (!cancelled) {
        if (progression) syncServerVocabularyProgress(progression);
        setServerProgression(progression);
        setStars(derived);
        setAttempts(serverAttempts);
      }
    };
    loadAuthoritativeProgress().finally(() => { if (!cancelled) setStarsReady(true); });
    return () => { cancelled = true; };
  }, [canonicalStoryId, hasApprovedMaterial, storyId, studentId, studentName, studentScope]);

  const [priorityReviewWords, setPriorityReviewWords] = useState<VocabPriorityReviewWord[]>([]);
  // Legacy flat weak-word list — a fallback for payloads that return only word
  // strings (older data / the compatibility endpoint) without ranked
  // priorityReview objects.
  const [weakWords, setWeakWords] = useState<string[]>([]);
  const [strongWords, setStrongWords] = useState<VocabPriorityReviewWord[]>([]);
  const [masteryWords, setMasteryWords] = useState<VocabPriorityReviewWord[]>([]);
  const [diagnosticComplete, setDiagnosticComplete] = useState<boolean | undefined>(undefined);
  const [roundPresence, setRoundPresence] = useState<VocabPriorityReviewResponse["roundPresence"]>(undefined);
  // Spaced-repetition maintenance reviews: words the SM-2 schedule says are due
  // today (may include words that are already strong). Kept apart from weak words so
  // the UI can label "ôn tập duy trì" separately from "từ cần luyện".
  const [dueWords, setDueWords] = useState<ReviewQueueItem[]>([]);
  const [weakWordsReady, setWeakWordsReady] = useState(false);
  const applyWeakWords = useCallback((words: VocabWeakWordsResult) => {
    setPriorityReviewWords(words.priorityReview ?? []);
    setWeakWords(Array.isArray(words) ? [...words] : []);
    setMasteryWords(words.mastery ?? []);
    setStrongWords((words.mastery ?? []).filter((word) => word.vocabularyState?.review.status === "STRONG" || word.status === "STRONG"));
    const serverDiagnostic = words.diagnostic?.diagnosticComplete
      ?? (words.diagnostic?.diagnostic?.status === "COMPLETE" ? true : words.diagnostic?.diagnostic?.status === "INCOMPLETE" ? false : undefined);
    setDiagnosticComplete(serverDiagnostic);
    setRoundPresence(words.diagnostic?.roundPresence);
  }, []);
  // The weak-word card and the due-review list used to be two requests that
  // each replayed the student's whole BKT history on the server. The
  // review-queue payload contains the weak-words payload plus `queue`, so one
  // read feeds both weak-word practice and scheduled maintenance.
  const reviewRequestRef = useRef<Promise<void> | null>(null);
  const readReview = useCallback((): Promise<void> => {
    const request = (async () => {
      // Weak Words is a story-wide summary, so the API must receive the
      // source story id and aggregate into one learner list.
      const source = baseStoryId ?? storyId;
      if (!source) return;
      if (!studentId) {
        applyWeakWords(await getVocabQuizWeakWords(source, { studentId, studentName }));
        setDueWords([]);
        return;
      }
      const queue = await getVocabQuizReviewQueue(source, studentId, { includeAllWeak: true });
      applyWeakWords(weakWordsResultFromPriorityReview(queue));
      setDueWords((queue.queue ?? []).filter((item) => item.reviewReason === "due"));
    })().finally(() => { if (reviewRequestRef.current === request) reviewRequestRef.current = null; });
    reviewRequestRef.current = request;
    return request;
  }, [storyId, baseStoryId, studentId, studentName, applyWeakWords]);
  // Refresh after a saved answer. A read already in flight may have started
  // before that answer was saved, so wait for it and then read again rather
  // than trusting it; calls made in the same tick share that one follow-up.
  const followUpRef = useRef<Promise<void> | null>(null);
  const refreshReview = useCallback((): Promise<void> => {
    if (!storyId || !canUseDatabase()) return Promise.resolve();
    if (!reviewRequestRef.current) return readReview();
    if (followUpRef.current) return followUpRef.current;
    const followUp = reviewRequestRef.current
      .catch(() => undefined)
      .then(() => readReview())
      .finally(() => { if (followUpRef.current === followUp) followUpRef.current = null; });
    followUpRef.current = followUp;
    return followUp;
  }, [storyId, readReview]);
  useEffect(() => {
    if (!storyId || !canUseDatabase()) {
      setWeakWordsReady(true);
      return;
    }
    let cancelled = false;
    refreshReview()
      .catch(() => { /* the always-visible card falls back to its empty state */ setDueWords([]); })
      .finally(() => { if (!cancelled) setWeakWordsReady(true); });
    return () => { cancelled = true; };
  }, [storyId, refreshReview]);

  const sessionReady = starsReady && weakWordsReady;
  const lessonProgress: LessonVocabularyProgress = useMemo(() => buildLessonVocabularyProgress({
    lessonId: baseStoryId ?? storyId ?? "lesson",
    entries,
    attempts,
    mastery: masteryWords,
    priorityReviewWords,
    diagnosticComplete: diagnosticComplete === true,
    roundPresence,
    studentScope,
    vocabularyVersion,
  }), [attempts, baseStoryId, diagnosticComplete, entries, masteryWords, priorityReviewWords, roundPresence, storyId, studentScope, vocabularyVersion]);


  return {
    stars,
    serverProgression,
    setStars,
    attempts,
    setAttempts,
    recordLessonEvent,
    priorityReviewWords,
    weakWords,
    masteryWords,
    strongWords,
    diagnosticComplete,
    roundPresence,
    dueWords,
    sessionReady,
    lessonProgress,
    refreshReview,
    studentScope,
  };
}
