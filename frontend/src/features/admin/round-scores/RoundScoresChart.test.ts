import { describe, expect, it } from "vitest";
import { createRoundScoresChartConfig, formatRoundScoreTooltip } from "./RoundScoresChart";
import type { RoundScoreRow } from "./model";

const rows: RoundScoreRow[] = [{
  studentId: "s1",
  studentName: "An",
  status: "active",
  completedRounds: 2,
  rounds: {
    tier1: { score: 75, correctCount: 3, totalQuestions: 4, totalTimeMs: 8000, completedAt: "2026-09-01T08:00:00Z", attemptId: "a1" },
    tier2: null,
    tier3: { score: 50, correctCount: 2, totalQuestions: 4, totalTimeMs: 4000, completedAt: "2026-09-02T08:00:00Z", attemptId: "a3" },
  },
}];

describe("round scores chart configuration", () => {
  it("builds three score columns plus a response-time line", () => {
    const config = createRoundScoresChartConfig(rows, true);

    expect(config.options?.indexAxis).toBe("x");
    expect(config.data.datasets.map((dataset) => dataset.label)).toEqual([
      "Round 1 · Meaning",
      "Round 2 · Pinyin",
      "Round 3 · Context",
      "Avg response time / question",
    ]);
    expect(config.data.datasets.map((dataset) => dataset.data)).toEqual([[75], [null], [50], [1.5]]);
    expect(config.data.datasets.map((dataset) => dataset.type)).toEqual(["bar", "bar", "bar", "line"]);
    expect(config.options?.animation).toBe(false);
  });

  it("fixes the accuracy scale to 0–100 and exposes rich tooltip detail", () => {
    const config = createRoundScoresChartConfig(rows);
    const scoreScale = config.options?.scales?.score;
    const responseTimeScale = config.options?.scales?.responseTime;

    expect(scoreScale).toMatchObject({ min: 0, max: 100, beginAtZero: true, position: "left" });
    expect(responseTimeScale).toMatchObject({ min: 0, beginAtZero: true, position: "right" });
    expect(formatRoundScoreTooltip(rows, 0, 0)).toContain("75% · 3/4 · 2s/question");
    expect(formatRoundScoreTooltip(rows, 1, 0)).toBe("Round 2 · Pinyin: Not completed");
    expect(formatRoundScoreTooltip(rows, 3, 0)).toBe("Avg response time / question: 1.5s · 8 questions · 2 rounds");
  });
});
