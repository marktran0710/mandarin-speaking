import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AdminBktVerificationPage from "./AdminBktVerificationPage";
import { getBktVerificationBootstrap, getBktVerificationTrace } from "../../services/api/bkt-verification";

vi.mock("../../services/api/bkt-verification", () => ({
  getBktVerificationBootstrap: vi.fn(),
  getBktVerificationTrace: vi.fn(),
}));

const model = {
  version: "format-aware-bkt-v2",
  parameterFingerprint: "fingerprint",
  goldenFixtureVersion: "format-aware-bkt-v2",
  contractStatus: "MATCH" as const,
  parameters: { pL0: 0.2, pT: 0.15, mcqGuess: 0.2, mcqSlip: 0.1, typedGuess: 0.05, typedSlip: 0.15, masteryThreshold: 0.95, minimumObservations: 3 },
};

const step = {
  step: 1,
  prior: 0.2,
  observation: "Correct" as const,
  correct: true,
  questionType: "basic_meaning_mcq",
  guess: 0.2,
  slip: 0.1,
  posterior: 0.5294117647,
  learningTransition: 0.15,
  resultingMastery: 0.6,
};

const trace = {
  student: { studentId: "SIM001", name: "SIM001", isTestAccount: true },
  words: [{ wordId: "word-1", word: "征", meaning: "to conquer", lessonId: "lesson-5", pLearned: 0.2, observationCount: 0, status: "UNASSESSED", reviewStatus: "NOT_ASSESSED" }],
  presets: [{ id: "unseen-word", label: "Unseen word", wordId: "word-1" }],
  selectedWordId: "word-1",
  model,
  trace: {
    word: { wordId: "word-1", word: "征", meaning: "to conquer", lessonId: "lesson-5", pLearned: 0.2, observationCount: 0, status: "UNASSESSED", reviewStatus: "NOT_ASSESSED" },
    evidence: [],
    evidenceCount: 0,
    provenance: "NONE",
    syntheticTestData: true,
    coldStart: { source: "Global BKT prior" as const, pL0: 0.2 },
    expectedTrace: [],
    actualTrace: [],
    comparison: { observationCount: { expected: 0, actual: 0 }, pLearned: { expected: 0.2, actual: 0.2 }, status: { expected: "UNASSESSED", actual: "UNASSESSED" } },
    verification: "PASS" as const,
    reviewStatus: "NOT_ASSESSED",
  },
};

const bootstrap = {
  model,
  golden: {
    contractStatus: "MATCH" as const,
    fixtureVersion: "format-aware-bkt-v2",
    targetParameterFingerprint: "fingerprint",
    checks: [{ id: "one", scenario: "One MCQ correct", input: [{ correct: true, questionType: "basic_meaning_mcq" }], expected: { pLearned: 0.6, observationCount: 1, status: "UNASSESSED", trace: [step] }, actual: { pLearned: 0.6, observationCount: 1, status: "UNASSESSED", trace: [step] }, result: "PASS" as const, tolerance: 1e-9 }],
    summary: { passed: 1, total: 1 },
  },
  students: [{ studentId: "SIM001", name: "SIM001", status: "active", isTestAccount: true }],
};

describe("AdminBktVerificationPage", () => {
  beforeEach(() => {
    vi.mocked(getBktVerificationBootstrap).mockResolvedValue(bootstrap);
    vi.mocked(getBktVerificationTrace).mockResolvedValue(trace);
  });

  it("renders the read-only model contract, golden check, and unseen-word trace", async () => {
    render(<AdminBktVerificationPage />);

    expect(await screen.findByRole("heading", { name: "BKT Verification", level: 2 })).toBeInTheDocument();
    expect(screen.getAllByText("format-aware-bkt-v2").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Golden BKT Checks" })).toBeInTheDocument();
    expect(await screen.findByText("Synthetic test data")).toBeInTheDocument();
    expect(screen.getAllByText("Evidence").length).toBeGreaterThan(0);
    expect(screen.getAllByText("NOT_ASSESSED").length).toBeGreaterThan(0);
  });

  it("expands a golden scenario and exposes its step trace", async () => {
    render(<AdminBktVerificationPage />);

    await screen.findByRole("heading", { name: "Golden BKT Checks" });
    fireEvent.click(screen.getByRole("button", { name: "Hide trace" }));
    expect(screen.queryByRole("heading", { name: "One MCQ correct" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show trace" }));
    expect(screen.getByRole("heading", { name: "One MCQ correct" })).toBeInTheDocument();
    expect(screen.getByText("Expected reference calculation")).toBeInTheDocument();
  });

  it("reloads the live trace when a quick preset is selected", async () => {
    render(<AdminBktVerificationPage />);
    await screen.findByRole("heading", { name: "Live Student Trace" });
    fireEvent.click(screen.getByRole("button", { name: "Unseen word" }));
    await waitFor(() => expect(getBktVerificationTrace).toHaveBeenCalledWith("SIM001", "word-1"));
  });

  it("requests candidate metadata and the matching candidate trace", async () => {
    render(<AdminBktVerificationPage modelVersion="synthetic-candidate" />);
    await screen.findByRole("heading", { name: "Live Student Trace" });
    expect(getBktVerificationBootstrap).toHaveBeenCalledWith("synthetic-candidate");
    await waitFor(() => expect(getBktVerificationTrace).toHaveBeenCalledWith("SIM001", expect.anything(), "synthetic-candidate"));
  });
});
