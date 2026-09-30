import { describe, expect, it } from "vitest";
import { createStudentRoundChartConfig, formatStudentRoundTooltip } from "./StudentRoundChart";
import type { StudentLessonRow } from "./model";

const lesson: StudentLessonRow = {
  storyId: "lesson-1",
  title: "Greetings",
  completedRounds: 2,
  latestCompletedAt: "2026-09-02T08:00:00Z",
  rounds: {
    tier1: { score: 75, correctCount: 3, totalQuestions: 4, totalTimeMs: 8000, completedAt: "2026-09-01T08:00:00Z", attemptId: "a1" },
    tier2: null,
    tier3: { score: 50, correctCount: 2, totalQuestions: 4, totalTimeMs: null, completedAt: "2026-09-02T08:00:00Z", attemptId: "a3" },
  },
  responseTime: { secondsPerQuestion: 2, totalQuestions: 4, completedRounds: 1 },
  classRounds: {
    tier1: { average: 60, completed: 5 },
    tier2: { average: null, completed: 0 },
    tier3: { average: 40, completed: 1 },
  },
};

describe("student round chart configuration", () => {
  it("compares the student with the class average per round and adds a response-time line", () => {
    const config = createStudentRoundChartConfig("An", lesson, true);

    expect(config.data.labels).toEqual(["Round 1 · Meaning", "Round 2 · Pinyin", "Round 3 · Context"]);
    expect(config.data.datasets.map((dataset) => dataset.label)).toEqual([
      "An",
      "Class average",
      "Response time / question",
    ]);
    expect(config.data.datasets.map((dataset) => dataset.type)).toEqual(["bar", "bar", "line"]);
    // Missing rounds and unavailable times stay null so they are never drawn as zero.
    expect(config.data.datasets.map((dataset) => dataset.data)).toEqual([
      [75, null, 50],
      [60, null, 40],
      [2, null, null],
    ]);
    expect(config.options?.animation).toBe(false);
  });

  it("fixes the accuracy scale to 0–100 and puts seconds on a separate right axis", () => {
    const config = createStudentRoundChartConfig("An", lesson);

    expect(config.options?.scales?.score).toMatchObject({ min: 0, max: 100, beginAtZero: true, position: "left" });
    expect(config.options?.scales?.responseTime).toMatchObject({ min: 0, beginAtZero: true, position: "right" });
  });

  it("describes each point in the tooltip, including missing rounds", () => {
    expect(formatStudentRoundTooltip("An", lesson, 0, 0)).toContain("An: 75% · 3/4 · 2s/question");
    expect(formatStudentRoundTooltip("An", lesson, 0, 1)).toBe("An: Not completed");
    expect(formatStudentRoundTooltip("An", lesson, 0, 2)).toContain("An: 50% · 2/4 · time unavailable");
    expect(formatStudentRoundTooltip("An", lesson, 1, 0)).toBe("Class average: 60% · 5 students");
    expect(formatStudentRoundTooltip("An", lesson, 1, 1)).toBe("Class average: No completed students");
    expect(formatStudentRoundTooltip("An", lesson, 1, 2)).toBe("Class average: 40% · 1 student");
    expect(formatStudentRoundTooltip("An", lesson, 2, 0)).toBe("Response time / question: 2s");
    expect(formatStudentRoundTooltip("An", lesson, 2, 1)).toBe("Response time / question: Not available");
  });
});
