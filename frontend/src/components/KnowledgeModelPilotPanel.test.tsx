import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import KnowledgeModelPilotPanel from "./KnowledgeModelPilotPanel";
import type { KnowledgeAnalyticsResponse } from "../services/database";

const { getKnowledgeModelAnalytics } = vi.hoisted(() => ({
  getKnowledgeModelAnalytics: vi.fn(),
}));

vi.mock("../services/database", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../services/database")>()),
  canUseDatabase: vi.fn(() => true),
  getKnowledgeModelAnalytics,
}));

const readyData: KnowledgeAnalyticsResponse = {
  model: "compare",
  modelVersion: "knowledge-pilot-v1",
  scope: { studentId: null, storyId: null, level: null },
  dataQuality: {
    totalAttempts: 12, totalResponses: 24, eligibleResponses: 24,
    legacyConceptResponses: 2, skippedResponses: 0, duplicateResponses: 0,
    attemptsWithoutId: 0, invalidTimestampAttempts: 0, skillCount: 4,
  },
  models: {
    pfa: {
      model: "pfa", modelVersion: "knowledge-pilot-v1", masteryInterpretation: "predicted_correct_probability",
      scope: { studentId: null, storyId: null, level: null },
      dataQuality: { totalAttempts: 12, totalResponses: 24, eligibleResponses: 24, legacyConceptResponses: 2, skippedResponses: 0, duplicateResponses: 0, attemptsWithoutId: 0, invalidTimestampAttempts: 0, skillCount: 4 },
      students: [{ studentId: "s1", studentName: "Ava", skills: [{ conceptId: "學習", mastery: .42, predictedCorrect: .42, exposures: 3, successes: 1, failures: 2, lastSeenAt: null, confidence: "medium" }] }],
      evaluation: { status: "ready", responseCount: 24, predictionCount: 12, positiveCount: 8, negativeCount: 4, logLoss: .41, brierScore: .16, calibrationError: .08, auc: .7 },
    },
    bkt: {
      model: "bkt", modelVersion: "knowledge-pilot-v1", masteryInterpretation: "latent_mastery_probability",
      scope: { studentId: null, storyId: null, level: null },
      dataQuality: { totalAttempts: 12, totalResponses: 24, eligibleResponses: 24, legacyConceptResponses: 2, skippedResponses: 0, duplicateResponses: 0, attemptsWithoutId: 0, invalidTimestampAttempts: 0, skillCount: 4 },
      students: [],
      evaluation: { status: "ready", responseCount: 24, predictionCount: 12, positiveCount: 8, negativeCount: 4, logLoss: .5, brierScore: .2, calibrationError: .1, auc: .65 },
    },
  },
  recommendedModel: "pfa",
};

describe("KnowledgeModelPilotPanel", () => {
  beforeEach(() => {
    getKnowledgeModelAnalytics.mockReset();
  });

  it("renders the comparison and current recommendation", async () => {
    getKnowledgeModelAnalytics.mockResolvedValue(readyData);
    render(<KnowledgeModelPilotPanel />);
    expect(screen.getByText("Calculating model comparison…")).toBeInTheDocument();
    expect(await screen.findByText("PFA", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByText("BKT", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByText("Current recommendation:")).toBeInTheDocument();
    expect(screen.getByText("Ava")).toBeInTheDocument();
  });

  it("shows an error state when the admin analytics request fails", async () => {
    getKnowledgeModelAnalytics.mockRejectedValue(new Error("Analytics unavailable"));
    render(<KnowledgeModelPilotPanel />);
    await waitFor(() => expect(screen.getByText("Analytics unavailable")).toBeInTheDocument());
  });

  it("renders an insufficient-data comparison without a skill table", async () => {
    getKnowledgeModelAnalytics.mockResolvedValue({
      ...readyData,
      recommendedModel: null,
      models: {
        pfa: {
          ...readyData.models.pfa,
          students: [],
          evaluation: { ...readyData.models.pfa.evaluation, status: "insufficient_data", predictionCount: 2 },
        },
        bkt: {
          ...readyData.models.bkt,
          students: [],
          evaluation: { ...readyData.models.bkt.evaluation, status: "insufficient_data", predictionCount: 2 },
        },
      },
    });
    render(<KnowledgeModelPilotPanel />);
    expect(await screen.findAllByText("Insufficient data")).toHaveLength(2);
    expect(screen.getByText("No winner yet")).toBeInTheDocument();
    expect(screen.queryByText("Lowest current PFA predicted correctness")).not.toBeInTheDocument();
  });
});
