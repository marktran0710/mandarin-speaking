import { describe, expect, it } from "vitest";
import { createRoundScoresChartConfig, formatRoundScoreTooltip } from "./RoundScoresChart";
import type { RoundScoreRow } from "./model";

const rows: RoundScoreRow[] = [{
  studentId: "s1",
  studentName: "An",
  status: "active",
  completedRounds: 2,
  rounds: {
    tier1: { score: 75, correctCount: 3, totalQuestions: 4, completedAt: "2026-09-01T08:00:00Z", attemptId: "a1" },
    tier2: null,
    tier3: { score: 50, correctCount: 2, totalQuestions: 4, completedAt: "2026-09-02T08:00:00Z", attemptId: "a3" },
  },
}];

describe("round scores chart configuration", () => {
  it("builds three vertical datasets and preserves a missing round as null", () => {
    const config = createRoundScoresChartConfig(rows, true);

    expect(config.options?.indexAxis).toBe("x");
    expect(config.data.datasets.map((dataset) => dataset.label)).toEqual([
      "Round 1 · Meaning",
      "Round 2 · Pinyin",
      "Round 3 · Context",
    ]);
    expect(config.data.datasets.map((dataset) => dataset.data)).toEqual([[75], [null], [50]]);
    expect(config.options?.animation).toBe(false);
  });

  it("fixes the accuracy scale to 0–100 and exposes rich tooltip detail", () => {
    const config = createRoundScoresChartConfig(rows);
    const yScale = config.options?.scales?.y;

    expect(yScale).toMatchObject({ min: 0, max: 100, beginAtZero: true });
    expect(formatRoundScoreTooltip(rows, 0, 0)).toContain("75% · 3/4");
    expect(formatRoundScoreTooltip(rows, 1, 0)).toBe("Round 2 · Pinyin: Not completed");
  });
});
