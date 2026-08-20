import type { AudioRecord } from "../pages/MyStoriesPage";
import type { StorySubmission, Student, VocabQuizAttempt } from "../services/database";
import { computeWordMissStats, getTopicLabel, type WordMissStats } from "./myStoriesUtils";
import { attemptEarnsStar, starsByStory, type QuizTier } from "./quizTiers";

const DAY_MS = 24 * 60 * 60 * 1000;

export interface StudentAssessment {
  studentId: string;
  studentName: string;
  quiz: {
    attemptCount: number;
    accuracyPct: number | null;
    starsByStory: Record<string, 0 | QuizTier>;
    tierAttemptStoryIds: string[];
    topMissedWords: WordMissStats[];
  };
  speaking: {
    recordingCount: number;
    avgFluencyScore: number | null;
    avgToneAccuracy: number | null;
    avgAiFeedbackScore: number | null;
  };
  activity: {
    lastActivityAt: string | null;
    inactiveDays: number | null;
  };
  watchlistReasons: string[];
}

function timestamp(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

function average(values: number[]): number | null {
  if (values.length === 0) return null;
  return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
}

function activitySummary(
  student: Student,
  attempts: VocabQuizAttempt[],
  recordings: AudioRecord[],
  submissions: StorySubmission[],
  now: Date,
) {
  const datedActivity = [
    ...attempts.map((attempt) => attempt.completedAt),
    ...recordings.map((recording) => recording.timestamp),
    ...submissions.map((submission) => submission.submittedAt),
  ]
    .map((value) => ({ value, time: timestamp(value) }))
    .filter((value): value is { value: string; time: number } => value.time !== null)
    .sort((a, b) => b.time - a.time);

  const lastActivityAt = datedActivity[0]?.value ?? null;
  // A student with no activity is measured from when they joined the roster;
  // this avoids calling a brand-new student inactive while still surfacing a
  // long-idle roster entry.
  const baseline = datedActivity[0]?.time ?? timestamp(student.createdAt);
  const inactiveDays = baseline === null
    ? null
    : Math.max(0, Math.floor((now.getTime() - baseline) / DAY_MS));

  return { lastActivityAt, inactiveDays };
}

/** Builds the roster-linked assessment view used by the student analytics
 * tab. Legacy rows without a stable student id are intentionally excluded:
 * names are free-typed and cannot safely be attributed after the fact. */
export function buildStudentAssessments(
  students: Student[],
  quizAttempts: VocabQuizAttempt[],
  audioRecords: AudioRecord[],
  storySubmissions: StorySubmission[] = [],
  now = new Date(),
): StudentAssessment[] {
  return students.map((student) => {
    const attempts = quizAttempts.filter((attempt) => attempt.studentId === student.id);
    const recordings = audioRecords.filter((recording) => recording.studentId === student.id);
    const submissions = storySubmissions.filter((submission) => submission.studentId === student.id);
    const totalQuestions = attempts.reduce((sum, attempt) => sum + attempt.totalQuestions, 0);
    const correctCount = attempts.reduce((sum, attempt) => sum + attempt.correctCount, 0);
    const stars = starsByStory(attempts);
    const tierAttemptStoryIds = Array.from(new Set(
      attempts
        .filter((attempt) => attempt.mode === "tier1" || attempt.mode === "tier2" || attempt.mode === "tier3")
        .map((attempt) => attempt.storyId),
    )).sort();
    const activity = activitySummary(student, attempts, recordings, submissions, now);
    const watchlistReasons: string[] = [];
    const lastFiveAttempts = [...attempts]
      .sort((a, b) => (timestamp(b.completedAt) ?? 0) - (timestamp(a.completedAt) ?? 0))
      .slice(0, 5);
    const lastFiveQuestions = lastFiveAttempts.reduce((sum, attempt) => sum + attempt.totalQuestions, 0);
    const lastFiveCorrect = lastFiveAttempts.reduce((sum, attempt) => sum + attempt.correctCount, 0);

    if (lastFiveQuestions > 0 && (lastFiveCorrect / lastFiveQuestions) * 100 < 60) {
      watchlistReasons.push("Low accuracy");
    }
    if (activity.inactiveDays !== null && activity.inactiveDays >= 7) {
      watchlistReasons.push(`Inactive ${activity.inactiveDays}d`);
    }
    for (const storyId of tierAttemptStoryIds) {
      const storyAttempts = attempts.filter((attempt) => attempt.storyId === storyId);
      const tierAttempts = storyAttempts.filter(
        (attempt) => attempt.mode === "tier1" || attempt.mode === "tier2" || attempt.mode === "tier3",
      );
      const earnedTierTwo = storyAttempts.some(
        (attempt) => attemptEarnsStar(attempt.mode, attempt.correctCount) === 2,
      );
      if (tierAttempts.length >= 3 && !earnedTierTwo) {
        watchlistReasons.push(`Stuck on ${getTopicLabel(storyId)}`);
      }
    }

    const metricRecords = recordings.filter((recording) => recording.praatMetrics);
    const aiScores = metricRecords.flatMap((recording) =>
      ["fluency", "grammar", "vocabulary"]
        .map((category) => recording.praatMetrics?.ai_feedback?.[category]?.score)
        .filter((score): score is number => typeof score === "number"),
    );

    return {
      studentId: student.id,
      studentName: student.name,
      quiz: {
        attemptCount: attempts.length,
        accuracyPct: totalQuestions > 0 ? Math.round((correctCount / totalQuestions) * 100) : null,
        starsByStory: stars,
        tierAttemptStoryIds,
        topMissedWords: computeWordMissStats(attempts).slice(0, 5),
      },
      speaking: {
        recordingCount: recordings.length,
        avgFluencyScore: average(
          metricRecords
            .map((recording) => recording.praatMetrics?.fluency_score)
            .filter((score): score is number => typeof score === "number"),
        ),
        avgToneAccuracy: average(
          metricRecords
            .map((recording) => recording.praatMetrics?.tone_accuracy)
            .filter((score): score is number => typeof score === "number"),
        ),
        avgAiFeedbackScore: average(aiScores),
      },
      activity,
      watchlistReasons,
    };
  });
}
