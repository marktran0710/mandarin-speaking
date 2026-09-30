import { describe, expect, it } from "vitest";
import type { Student } from "../../../services/api/roster-help";
import type { VocabQuizAttempt } from "../../../services/api/quiz-analytics";
import {
  buildRoundScoreRows,
  buildRoundScoreStoryOptions,
  mostRecentRoundScoreStoryId,
  selectLatestRoundAttempts,
  summarizeRoundScores,
} from "./model";

const students: Student[] = [
  { id: "s1", name: "An", status: "active", createdAt: "2026-01-01" },
  { id: "s2", name: "Binh", status: "inactive", createdAt: "2026-01-02" },
  { id: "test", name: "Synthetic", status: "active", createdAt: "2026-01-03", isTestAccount: true },
];

function attempt(overrides: Partial<VocabQuizAttempt> = {}): VocabQuizAttempt {
  return {
    id: "a1",
    storyId: "lesson-1",
    studentId: "s1",
    studentName: "An",
    mode: "tier1",
    completedAt: "2026-09-01T08:00:00Z",
    totalQuestions: 4,
    correctCount: 3,
    totalTimeMs: 1000,
    questionResults: [],
    ...overrides,
  };
}

describe("round score model", () => {
  it("uses the latest completed attempt instead of the best score", () => {
    const selected = selectLatestRoundAttempts(students, [
      attempt({ id: "best", correctCount: 4, completedAt: "2026-09-01T08:00:00Z" }),
      attempt({ id: "latest", correctCount: 1, completedAt: "2026-09-02T08:00:00Z" }),
    ]);

    expect(selected).toHaveLength(1);
    expect(selected[0]).toMatchObject({ attemptId: "latest", score: 25, correctCount: 1 });
  });

  it("ignores non-round, empty, legacy, unknown, and test-account attempts", () => {
    const selected = selectLatestRoundAttempts(students, [
      attempt({ id: "speed", mode: "speed" }),
      attempt({ id: "empty", totalQuestions: 0 }),
      attempt({ id: "legacy", studentId: undefined, studentName: "An" }),
      attempt({ id: "unknown", studentId: "missing" }),
      attempt({ id: "test", studentId: "test" }),
      attempt({ id: "valid", mode: "tier2", correctCount: 0 }),
    ]);

    expect(selected).toEqual([expect.objectContaining({ attemptId: "valid", mode: "tier2", score: 0 })]);
  });

  it("keeps missing rounds null while preserving a true zero score", () => {
    const latest = selectLatestRoundAttempts(students, [attempt({ mode: "tier2", correctCount: 0 })]);
    const rows = buildRoundScoreRows(students, latest, "lesson-1");

    expect(rows).toHaveLength(2);
    expect(rows[0].rounds.tier1).toBeNull();
    expect(rows[0].rounds.tier2?.score).toBe(0);
    expect(rows[0].rounds.tier3).toBeNull();
    expect(rows[1].completedRounds).toBe(0);
  });

  it("builds lesson options from stories and attempt IDs, defaulting to the latest lesson", () => {
    const latest = selectLatestRoundAttempts(students, [
      attempt({ id: "older", storyId: "lesson-1" }),
      attempt({ id: "newer", storyId: "legacy-lesson", mode: "tier2", completedAt: "2026-09-03T08:00:00Z" }),
    ]);
    const options = buildRoundScoreStoryOptions(latest, [
      { id: "lesson-1", title: "Greetings" },
      { id: "lesson-2", title: "Family" },
    ]);

    expect(options.map(({ id, title }) => ({ id, title }))).toEqual([
      { id: "legacy-lesson", title: "legacy-lesson" },
      { id: "lesson-1", title: "Greetings" },
      { id: "lesson-2", title: "Family" },
    ]);
    expect(mostRecentRoundScoreStoryId(latest)).toBe("legacy-lesson");
  });

  it("averages only completed rounds and counts full completion", () => {
    const latest = selectLatestRoundAttempts(students, [
      attempt({ id: "s1-r1", mode: "tier1", correctCount: 4 }),
      attempt({ id: "s1-r2", mode: "tier2", correctCount: 2 }),
      attempt({ id: "s1-r3", mode: "tier3", correctCount: 3 }),
      attempt({ id: "s2-r1", studentId: "s2", studentName: "Binh", mode: "tier1", correctCount: 2 }),
    ]);
    const summary = summarizeRoundScores(buildRoundScoreRows(students, latest, "lesson-1"));

    expect(summary.rounds.tier1).toEqual({ average: 75, completed: 2 });
    expect(summary.rounds.tier2).toEqual({ average: 50, completed: 1 });
    expect(summary.rounds.tier3).toEqual({ average: 75, completed: 1 });
    expect(summary.completedAll).toBe(1);
  });
});
