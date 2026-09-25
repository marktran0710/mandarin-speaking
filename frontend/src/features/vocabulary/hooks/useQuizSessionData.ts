import { useCallback, useEffect, useMemo, useState, type RefObject } from "react";
import {
  loadLocalStars,
  recordLocalStars,
  starsFromAttempts,
  type QuizTier,
  type VocabQuizEntry,
} from "@entities/vocabulary";
import {
  canUseDatabase,
  getVocabQuizReviewQueue,
  getVocabQuizWeakWords,
  createVocabQuizAttempt,
  getVocabularyProgression,
  listVocabQuizAttempts,
  type ReviewQueueItem,
  type VocabPriorityReviewWord,
} from "../../../services/database";
import { getStudentScopeKey } from "../../../utils/studentSession";
import { getResearchReviewSession } from "../../../services/api/vocabulary-research";
import { getCachedResearchContext } from "../../../utils/researchContext";
import {
  buildLessonVocabularyProgress,
  loadLessonProgressSnapshot,
  type LessonVocabularyProgress,
} from "../model/lesson-vocab-progress";
import type { VocabPriorityReviewResponse, VocabQuizAttempt } from "../../../services/api/quiz-analytics";
import { createMeasurementEvent, recordMeasurementEvent, type MeasurementEventName } from "../../../utils/measurement";

type QuizSessionDataProps = {
  entries: VocabQuizEntry[];
  storyId?: string;
  baseStoryId?: string;
  studentId?: string;
  studentName?: string;
  quizIdRef: RefObject<string | null>;
};

export function useQuizSessionData({
  entries,
  storyId,
  baseStoryId,
  studentId,
  studentName,
  quizIdRef,
}: QuizSessionDataProps) {
  const canonicalStoryId = baseStoryId ?? storyId;
  const [stars, setStars] = useState<0 | QuizTier>(() => canonicalStoryId ? loadLocalStars(canonicalStoryId) : 0);
  const [serverProgression, setServerProgression] = useState<import("../../../services/api/quiz-analytics").VocabularyProgression | null>(null);
  const studentScope = studentId || studentName || getStudentScopeKey();
  const [attempts, setAttempts] = useState<VocabQuizAttempt[]>(() => (
    storyId ? loadLessonProgressSnapshot(studentScope, baseStoryId ?? storyId).attempts ?? [] : []
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
      let serverAttempts: VocabQuizAttempt[];
      try {
        serverAttempts = await listVocabQuizAttempts(canonicalStoryId, { studentId, studentName });
      } catch {
        // The server could not be read: localStorage is the deliberately
        // limited offline fallback. It is never merged after a successful
        // server read unless the attempt is first validated by POST.
        if (!cancelled) setStarsReady(true);
        return;
      }

      // Migrate completed rounds left in the old local mirror. A POST is the
      // validation boundary; a local record is not considered authoritative
      // merely because it has a passing client-side score.
      const serverIds = new Set(serverAttempts.map((attempt) => attempt.id));
      const localAttempts = loadLessonProgressSnapshot(studentScope, canonicalStoryId ?? storyId).attempts ?? [];
      const pending = localAttempts.filter((attempt) => !serverIds.has(attempt.id));
      if (pending.length > 0) {
        const synced = await Promise.allSettled(pending.map((attempt) => createVocabQuizAttempt({
          ...attempt,
          storyId: canonicalStoryId ?? attempt.storyId,
          baseStoryId: canonicalStoryId ?? attempt.baseStoryId,
          studentId,
        })));
        if (synced.some((result) => result.status === "fulfilled")) {
          try {
            serverAttempts = await listVocabQuizAttempts(canonicalStoryId, { studentId, studentName });
          } catch {
            // Keep the original successful read as the source of truth if the
            // refresh after migration is unavailable.
          }
        }
      }

      let derived: 0 | QuizTier;
      let progression: import("../../../services/api/quiz-analytics").VocabularyProgression | null = null;
      if (studentId && canonicalStoryId) {
        try {
          progression = await getVocabularyProgression(canonicalStoryId, studentId);
          derived = progression.quizStars;
        } catch {
          const progressAttempts = hasApprovedMaterial
            ? serverAttempts.filter((attempt) => Boolean(attempt.questionResults?.length && attempt.questionResults.every((result) => result.bktValidationStatus === "APPROVED")))
            : serverAttempts;
          derived = starsFromAttempts(progressAttempts);
        }
      } else {
        const progressAttempts = hasApprovedMaterial
          ? serverAttempts.filter((attempt) => Boolean(attempt.questionResults?.length && attempt.questionResults.every((result) => result.bktValidationStatus === "APPROVED")))
          : serverAttempts;
        derived = starsFromAttempts(progressAttempts);
      }

      if (!cancelled) {
        if (derived !== 0 && canonicalStoryId) recordLocalStars(canonicalStoryId, derived);
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
  const refreshWeakWords = useCallback(async () => {
    if (!storyId || !canUseDatabase()) return;
    // Weak Words is a story-wide summary, so the API must receive the source
    // story id and aggregate into one learner list.
    const words = await getVocabQuizWeakWords(baseStoryId ?? storyId, { studentId, studentName });
    setPriorityReviewWords(words.priorityReview ?? []);
    setWeakWords(Array.isArray(words) ? [...words] : []);
    setMasteryWords(words.mastery ?? []);
    setStrongWords((words.mastery ?? []).filter((word) => word.vocabularyState?.review.status === "STRONG" || word.status === "STRONG"));
    const serverDiagnostic = words.diagnostic?.diagnosticComplete
      ?? (words.diagnostic?.diagnostic?.status === "COMPLETE" ? true : words.diagnostic?.diagnostic?.status === "INCOMPLETE" ? false : undefined);
    setDiagnosticComplete(serverDiagnostic);
    setRoundPresence(words.diagnostic?.roundPresence);
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

  // Due-review words (SM-2 schedule) load independently of the weak-word
  // readiness gate — a slow or failed queue fetch must never delay the mode
  // screen. Best-effort: empty on any error.
  const refreshDueWords = useCallback(async () => {
    // An active research participant's due words come from the separate
    // research retention schedule (see researchDueWordIds below), never
    // this production SM-2 queue.
    if (!storyId || !studentId || !canUseDatabase() || getCachedResearchContext().active) {
      setDueWords([]);
      return;
    }
    const queue = await getVocabQuizReviewQueue(baseStoryId ?? storyId, studentId, { includeAllWeak: true });
    setDueWords((queue.queue ?? []).filter((item) => item.reviewReason === "due"));
  }, [storyId, baseStoryId, studentId]);
  useEffect(() => {
    let cancelled = false;
    refreshDueWords().catch(() => { if (!cancelled) setDueWords([]); });
    return () => { cancelled = true; };
  }, [refreshDueWords]);

  // Epic 5: a research participant's due words come from the separate
  // research retention schedule, never production's SM-2 queue above. The
  // review-session endpoint is read-only, so prefetching it just to size
  // the "Review today" card (unlike the practice-session endpoint, which
  // writes a treatment-BKT snapshot and is deliberately NOT prefetched) is
  // safe.
  const [researchDueWordIds, setResearchDueWordIds] = useState<string[]>([]);
  useEffect(() => {
    if (!getCachedResearchContext().active) { setResearchDueWordIds([]); return; }
    let cancelled = false;
    getResearchReviewSession()
      .then((session) => { if (!cancelled) setResearchDueWordIds(session.wordIds); })
      .catch(() => { if (!cancelled) setResearchDueWordIds([]); });
    return () => { cancelled = true; };
  }, [storyId]);
  const researchDueEntries = useMemo(() => {
    const byWordId = new Map(entries.map((entry) => [entry.wordId ?? entry.word, entry]));
    return researchDueWordIds.map((wordId) => byWordId.get(wordId)).filter((entry): entry is VocabQuizEntry => Boolean(entry));
  }, [entries, researchDueWordIds]);

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
  }), [attempts, baseStoryId, diagnosticComplete, entries, masteryWords, priorityReviewWords, roundPresence, storyId, studentScope]);


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
    researchDueEntries,
    sessionReady,
    lessonProgress,
    refreshWeakWords,
    refreshDueWords,
    studentScope,
  };
}
