import { describe, expect, it } from "vitest";
import type { Student, VocabQuizAttempt } from "../services/database";
import { buildStudentAssessments } from "./studentAssessment";

const NOW = new Date("2026-07-30T12:00:00Z");
const student: Student = { id: "student-1", name: "Mai", createdAt: "2026-07-30T08:00:00Z" };

function attempt(overrides: Partial<VocabQuizAttempt> = {}): VocabQuizAttempt {
  return {
    id: crypto.randomUUID(),
    storyId: "unknown-story",
    studentId: student.id,
    studentName: student.name,
    mode: "tier1",
    completedAt: "2026-07-30T09:00:00Z",
    totalQuestions: 10,
    correctCount: 8,
    totalTimeMs: 10_000,
    questionResults: [],
    ...overrides,
  };
}

describe("buildStudentAssessments watchlist", () => {
  it("flags low accuracy across a student's latest five attempts", () => {
    const assessment = buildStudentAssessments(
      [student],
      [attempt({ correctCount: 5 })],
      [],
      [],
      NOW,
    )[0];

    expect(assessment.watchlistReasons).toContain("Low accuracy");
  });

  it("reports the actual inactive day count", () => {
    const assessment = buildStudentAssessments(
      [{ ...student, createdAt: "2026-07-20T12:00:00Z" }],
      [],
      [],
      [],
      NOW,
    )[0];

    expect(assessment.watchlistReasons).toContain("Inactive 10d");
  });

  it("flags three unsuccessful tier attempts on the same story", () => {
    const assessment = buildStudentAssessments(
      [student],
      [attempt({ id: "a" }), attempt({ id: "b" }), attempt({ id: "c" })],
      [],
      [],
      NOW,
    )[0];

    expect(assessment.watchlistReasons.some((reason) => reason.startsWith("Stuck on "))).toBe(true);
  });

  it("does not put an active, successful student on the watchlist", () => {
    const assessment = buildStudentAssessments(
      [student],
      [attempt({ mode: "tier2", correctCount: 18 })],
      [],
      [],
      NOW,
    )[0];

    expect(assessment.watchlistReasons).toEqual([]);
  });
});
