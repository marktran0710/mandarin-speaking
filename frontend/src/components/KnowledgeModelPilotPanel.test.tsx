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
  modelVersion: "knowledge-pilot-v2",
  scope: { studentId: null, storyId: null, level: null },
  dataQuality: {
    totalAttempts: 12, totalResponses: 24, eligibleResponses: 24,
    legacyConceptResponses: 2, skippedResponses: 0, duplicateResponses: 0,
    attemptsWithoutId: 0, invalidTimestampAttempts: 0, skillCount: 4, studentCount: 10, conceptCount: 10,
  },
  models: {
    pfa: {
      model: "pfa", modelVersion: "knowledge-pilot-v2", implementation: "restricted_pooled_baseline", masteryInterpretation: "predicted_correct_probability",
      scope: { studentId: null, storyId: null, level: null },
      dataQuality: { totalAttempts: 12, totalResponses: 24, eligibleResponses: 24, legacyConceptResponses: 2, skippedResponses: 0, duplicateResponses: 0, attemptsWithoutId: 0, invalidTimestampAttempts: 0, skillCount: 4, studentCount: 10, conceptCount: 10 },
      students: [{ studentId: "s1", studentName: "Ava", skills: [{ conceptId: "學習", mastery: .42, predictedCorrect: .42, exposures: 3, successes: 1, failures: 2, lastSeenAt: null, evidenceDepth: "medium" }] }],
      evaluation: { status: "evidence_ready", responseCount: 200, predictionCount: 100, positiveCount: 50, negativeCount: 50, logLoss: .41, brierScore: .16, calibrationError: .08, auc: .7, evidenceChecks: [], fitDiagnostics: { status: "success", optimizer: "test", message: "ok", iterations: 1, objective: .41, finite: true } },
    },
    bkt: {
      model: "bkt", modelVersion: "knowledge-pilot-v2", implementation: "pooled_bkt_pilot", masteryInterpretation: "latent_mastery_probability",
      scope: { studentId: null, storyId: null, level: null },
      dataQuality: { totalAttempts: 12, totalResponses: 24, eligibleResponses: 24, legacyConceptResponses: 2, skippedResponses: 0, duplicateResponses: 0, attemptsWithoutId: 0, invalidTimestampAttempts: 0, skillCount: 4, studentCount: 10, conceptCount: 10 },
      students: [],
      evaluation: { status: "evidence_ready", responseCount: 200, predictionCount: 100, positiveCount: 50, negativeCount: 50, logLoss: .5, brierScore: .2, calibrationError: .1, auc: .65, evidenceChecks: [], fitDiagnostics: { status: "success", optimizer: "test", message: "ok", iterations: 1, objective: .5, finite: true } },
    },
  },
  lowerLossSignal: "pfa",
};

describe("KnowledgeModelPilotPanel", () => {
  beforeEach(() => {
    getKnowledgeModelAnalytics.mockReset();
  });

  it("renders the comparison and exploratory lower-loss signal", async () => {
    getKnowledgeModelAnalytics.mockResolvedValue(readyData);
    render(<KnowledgeModelPilotPanel />);
    expect(screen.getByText("Calculating model comparison…")).toBeInTheDocument();
    expect(await screen.findByText("PFA", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByText("BKT", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByText("Exploratory lower-loss signal:")).toBeInTheDocument();
    expect(screen.getByText("PFA has lower held-out log loss")).toBeInTheDocument();
    expect(screen.getByText("Ava")).toBeInTheDocument();
    expect(screen.getByText("Papers & formulas used in this pilot")).toBeInTheDocument();
    expect(screen.getByText(/p\(correct\) = σ\(β₀ \+ βs·successes/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Pavlik, Cen & Koedinger \(2009\)/ })).toHaveAttribute("href", "https://doi.org/10.3233/978-1-60750-028-5-531");
    expect(screen.getByRole("link", { name: /Corbett & Anderson \(1994\)/ })).toHaveAttribute("href", "https://doi.org/10.1007/BF01099821");
  });

  it("shows an error state when the admin analytics request fails", async () => {
    getKnowledgeModelAnalytics.mockRejectedValue(new Error("Analytics unavailable"));
    render(<KnowledgeModelPilotPanel />);
    await waitFor(() => expect(screen.getByText("Analytics unavailable")).toBeInTheDocument());
  });

  it("renders an evidence-limited comparison without a skill table", async () => {
    getKnowledgeModelAnalytics.mockResolvedValue({
      ...readyData,
      lowerLossSignal: "no_material_difference",
      models: {
        pfa: {
          ...readyData.models.pfa,
          students: [],
          evaluation: { ...readyData.models.pfa.evaluation, status: "insufficient_evidence", predictionCount: 2, evidenceChecks: [{ name: "evaluation_predictions", actual: 2, minimum: 100, passed: false }] },
        },
        bkt: {
          ...readyData.models.bkt,
          students: [],
          evaluation: { ...readyData.models.bkt.evaluation, status: "insufficient_evidence", predictionCount: 2, evidenceChecks: [{ name: "evaluation_predictions", actual: 2, minimum: 100, passed: false }] },
        },
      },
    });
    render(<KnowledgeModelPilotPanel />);
    expect(await screen.findAllByText("More evidence needed")).toHaveLength(2);
    expect(screen.getByText("No material difference")).toBeInTheDocument();
    expect(screen.getAllByText(/Evidence still needed: evaluation predictions 2\/100/)).toHaveLength(2);
    expect(screen.queryByText("Lowest current PFA predicted correctness")).not.toBeInTheDocument();
  });
});
