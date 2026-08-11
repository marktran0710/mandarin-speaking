import { describe, expect, it } from "vitest";
import { createMeasurementEvent, summarizeMeasurements } from "./measurement";

describe("measurement contract", () => {
  it("creates a versioned append-only event", () => {
    const event = createMeasurementEvent("analysis_completed", {
      studentId: "s1",
      properties: { toneAccuracy: 84, passed: true },
    });
    expect(event.schemaVersion).toBe("learning-events.v1");
    expect(event.name).toBe("analysis_completed");
    expect(event.properties.passed).toBe(true);
    expect(event.eventId).toBeTruthy();
  });

  it("does not count unjudged recordings as pronunciation failures", () => {
    const summary = summarizeMeasurements([
      { praatMetrics: { tone_accuracy: 90, fluency_score: 80, pronunciation_mastery: { passed: true, status: "passed" } } },
      { praatMetrics: { tone_accuracy: 0, fluency_score: 0, pronunciation_mastery: { passed: false, status: "not_judged" }, feedback_quality: { status: "retry" } } },
    ]);
    expect(summary.passRate).toBe(50);
    expect(summary.notEnoughEvidenceRate).toBe(50);
  });
});
