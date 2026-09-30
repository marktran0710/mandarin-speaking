import { roundScore } from "../../../entities/vocabulary/progression";
import type { Student } from "../../../services/api/roster-help";
import type { VocabQuizAttempt } from "../../../services/api/quiz-analytics";

export const ROUND_DEFINITIONS = [
  { mode: "tier1", number: 1, dimension: "Meaning", label: "Round 1 · Meaning" },
  { mode: "tier2", number: 2, dimension: "Pinyin", label: "Round 2 · Pinyin" },
  { mode: "tier3", number: 3, dimension: "Context", label: "Round 3 · Context" },
] as const;

export type RoundMode = (typeof ROUND_DEFINITIONS)[number]["mode"];

export interface RoundScoreCell {
  score: number;
  correctCount: number;
  totalQuestions: number;
  completedAt: string;
  attemptId: string;
}

export interface LatestRoundAttempt extends RoundScoreCell {
  storyId: string;
  studentId: string;
  mode: RoundMode;
}

export interface RoundScoreRow {
  studentId: string;
  studentName: string;
  status: Student["status"];
  rounds: Record<RoundMode, RoundScoreCell | null>;
  completedRounds: number;
}

export interface RoundScoreStoryDescriptor {
  id: string;
  title: string;
}

export interface RoundScoreStoryOption extends RoundScoreStoryDescriptor {
  latestCompletedAt: string | null;
}

export interface RoundScoreSummary {
  rounds: Record<RoundMode, { average: number | null; completed: number }>;
  completedAll: number;
}

const ROUND_MODES = new Set<RoundMode>(ROUND_DEFINITIONS.map(({ mode }) => mode));
const studentCollator = new Intl.Collator(["zh-Hant", "en"], { numeric: true, sensitivity: "base" });

function isRoundMode(mode: VocabQuizAttempt["mode"]): mode is RoundMode {
  return typeof mode === "string" && ROUND_MODES.has(mode as RoundMode);
}

function timestamp(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}

function isLaterAttempt(candidate: Pick<VocabQuizAttempt, "id" | "completedAt">, current: Pick<VocabQuizAttempt, "id" | "completedAt">): boolean {
  const candidateTime = timestamp(candidate.completedAt);
  const currentTime = timestamp(current.completedAt);
  if (candidateTime !== currentTime) return candidateTime > currentTime;
  const dateOrder = candidate.completedAt.localeCompare(current.completedAt);
  return dateOrder === 0 ? candidate.id.localeCompare(current.id) > 0 : dateOrder > 0;
}

export function selectLatestRoundAttempts(students: Student[], attempts: VocabQuizAttempt[]): LatestRoundAttempt[] {
  const studentIds = new Set(students.filter((student) => !student.isTestAccount).map((student) => student.id));
  const latest = new Map<string, VocabQuizAttempt & { studentId: string; mode: RoundMode }>();

  for (const attempt of attempts) {
    if (!attempt.studentId || !studentIds.has(attempt.studentId)) continue;
    if (!attempt.storyId.trim() || !isRoundMode(attempt.mode)) continue;
    if (!Number.isFinite(attempt.totalQuestions) || attempt.totalQuestions <= 0) continue;
    if (!Number.isFinite(attempt.correctCount)) continue;

    const eligibleAttempt = attempt as VocabQuizAttempt & { studentId: string; mode: RoundMode };
    const key = `${attempt.storyId}\u0000${attempt.studentId}\u0000${attempt.mode}`;
    const current = latest.get(key);
    if (!current || isLaterAttempt(eligibleAttempt, current)) latest.set(key, eligibleAttempt);
  }

  return Array.from(latest.values(), (attempt) => ({
    storyId: attempt.storyId,
    studentId: attempt.studentId,
    mode: attempt.mode,
    score: roundScore(attempt.correctCount, attempt.totalQuestions),
    correctCount: attempt.correctCount,
    totalQuestions: attempt.totalQuestions,
    completedAt: attempt.completedAt,
    attemptId: attempt.id,
  }));
}

export function buildRoundScoreRows(
  students: Student[],
  attempts: LatestRoundAttempt[],
  storyId: string,
): RoundScoreRow[] {
  const attemptsByStudent = new Map<string, Partial<Record<RoundMode, RoundScoreCell>>>();
  for (const attempt of attempts) {
    if (attempt.storyId !== storyId) continue;
    const rounds = attemptsByStudent.get(attempt.studentId) ?? {};
    rounds[attempt.mode] = {
      score: attempt.score,
      correctCount: attempt.correctCount,
      totalQuestions: attempt.totalQuestions,
      completedAt: attempt.completedAt,
      attemptId: attempt.attemptId,
    };
    attemptsByStudent.set(attempt.studentId, rounds);
  }

  return students
    .filter((student) => !student.isTestAccount)
    .map((student) => {
      const attemptsForStudent = attemptsByStudent.get(student.id);
      const rounds = Object.fromEntries(
        ROUND_DEFINITIONS.map(({ mode }) => [mode, attemptsForStudent?.[mode] ?? null]),
      ) as Record<RoundMode, RoundScoreCell | null>;
      return {
        studentId: student.id,
        studentName: student.name,
        status: student.status,
        rounds,
        completedRounds: ROUND_DEFINITIONS.filter(({ mode }) => rounds[mode] !== null).length,
      };
    })
    .sort((left, right) => studentCollator.compare(left.studentName, right.studentName) || left.studentId.localeCompare(right.studentId));
}

export function buildRoundScoreStoryOptions(
  attempts: LatestRoundAttempt[],
  stories: RoundScoreStoryDescriptor[],
): RoundScoreStoryOption[] {
  const options = new Map<string, RoundScoreStoryOption>();
  for (const story of stories) {
    if (!story.id.trim()) continue;
    options.set(story.id, { id: story.id, title: story.title.trim() || story.id, latestCompletedAt: null });
  }
  for (const attempt of attempts) {
    const current = options.get(attempt.storyId) ?? {
      id: attempt.storyId,
      title: attempt.storyId,
      latestCompletedAt: null,
    };
    if (!current.latestCompletedAt || timestamp(attempt.completedAt) > timestamp(current.latestCompletedAt)) {
      current.latestCompletedAt = attempt.completedAt;
    }
    options.set(attempt.storyId, current);
  }

  return Array.from(options.values()).sort((left, right) => {
    const leftTime = timestamp(left.latestCompletedAt ?? "");
    const rightTime = timestamp(right.latestCompletedAt ?? "");
    if (leftTime !== rightTime) {
      if (Number.isFinite(leftTime) && Number.isFinite(rightTime)) return rightTime - leftTime;
      if (Number.isFinite(leftTime)) return -1;
      if (Number.isFinite(rightTime)) return 1;
    }
    if (left.latestCompletedAt && !right.latestCompletedAt) return -1;
    if (!left.latestCompletedAt && right.latestCompletedAt) return 1;
    return studentCollator.compare(left.title, right.title) || left.id.localeCompare(right.id);
  });
}

export function mostRecentRoundScoreStoryId(attempts: LatestRoundAttempt[]): string {
  let latest: LatestRoundAttempt | null = null;
  for (const attempt of attempts) {
    if (!latest || isLaterAttempt(
      { id: attempt.attemptId, completedAt: attempt.completedAt },
      { id: latest.attemptId, completedAt: latest.completedAt },
    )) latest = attempt;
  }
  return latest?.storyId ?? "";
}

export function summarizeRoundScores(rows: RoundScoreRow[]): RoundScoreSummary {
  const summary = Object.fromEntries(ROUND_DEFINITIONS.map(({ mode }) => {
    const scores = rows.flatMap((row) => row.rounds[mode]?.score ?? []);
    const average = scores.length > 0
      ? Math.round(scores.reduce((total, score) => total + score, 0) / scores.length)
      : null;
    return [mode, { average, completed: scores.length }];
  })) as RoundScoreSummary["rounds"];

  return {
    rounds: summary,
    completedAll: rows.filter((row) => row.completedRounds === ROUND_DEFINITIONS.length).length,
  };
}
