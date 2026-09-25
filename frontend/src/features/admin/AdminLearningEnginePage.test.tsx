import { render, screen, waitFor } from "@testing-library/react";
import AdminLearningEnginePage from "./AdminLearningEnginePage";
import { getLearningEngineMetadata } from "../../services/api/learning-engine";

vi.mock("../../services/api/learning-engine", () => ({
  getLearningEngineMetadata: vi.fn(),
}));

const mockMetadata = {
  bkt: {
    name: "Bayesian Knowledge Tracing",
    version: "format-aware-bkt-v2",
    provenance: "STANDARD_ALGORITHM",
    purpose: "Estimate per-word vocabulary mastery.",
    parameters: {
      P_L0_initial_mastery: { value: 0.2, provenance: "ENGINEERING_DEFAULT" },
      mastery_threshold: { value: 0.95, provenance: "ENGINEERING_DEFAULT" },
    },
    parameterStatus: "provisional",
    calibrationStatus: "Needs pilot/human-rater calibration.",
    pipeline: ["Client response", "BKT posterior update"],
    reference: { citation: "Corbett & Anderson (1995)", doi: "10.1007/BF01099821", note: "Equations follow standard BKT." },
  },
  retention: {
    name: "Modified SM-2",
    version: "modified-sm2-v1",
    provenance: "MODIFIED_STANDARD_ALGORITHM",
    purpose: "Schedule retention review.",
    parameters: {
      initial_ease: { value: 2.5, provenance: "STANDARD_ALGORITHM" },
      minimum_ease: { value: 1.3, provenance: "STANDARD_ALGORITHM" },
    },
    parameterStatus: "provisional",
    calibrationStatus: "Uses standard SM-2 constants; the q=4/q=2 mapping is unvalidated.",
    easeFormula: "EF' = EF + (0.1 - (5-q)*(0.08+(5-q)*0.02))",
    intervalSequence: "1 day, then 6 days, then round(prev*ease)",
    conceptualSeparation: "BKT asks how well learned; SRS asks when to review again.",
    reference: { citation: "Wozniak (1990)", note: "Modified SM-2, not the original algorithm unchanged." },
  },
  voice: {
    pipeline: ["Audio upload", "Recording quality control", "ASR transcription"],
    acousticEngine: {
      technology: "Praat via python-parselmouth",
      purpose: "F0/pitch extraction",
      provenance: "PUBLISHED_METHOD",
      reference: { citation: "Boersma (1993)", note: "Supports acoustic extraction only, not the tone scoring formulas." },
    },
    toneScoring: { provenance: "PROJECT_HEURISTIC", note: "Deterministic contour scoring, not a published formula." },
    qualityGate: { reasons: ["recording_too_short", "signal_too_quiet"], principle: "Poor evidence is not bad pronunciation." },
    thresholds: {
      SYLLABLE_PASS_THRESHOLD: { value: 58, purpose: "The only threshold gating progression.", controlsProgression: true, provenance: "ENGINEERING_DEFAULT" },
      TONE_CONFIRM_THRESHOLD: { value: 50, purpose: "Diagnostic-only confirm bar.", controlsProgression: false, provenance: "ENGINEERING_DEFAULT" },
    },
    asrProviders: [{ provider: "groq", role: "cloud ASR", configured: true }],
    feedbackProviders: {
      defaultProvider: "local",
      providers: [{ provider: "local", role: "offline coaching", configured: true }],
      fallbackBehavior: "Falls back to local on failure.",
    },
    calibrationStatus: "Needs human-rater calibration.",
  },
};

describe("AdminLearningEnginePage", () => {
  it("renders the BKT, retention and voice sections from live backend metadata", async () => {
    vi.mocked(getLearningEngineMetadata).mockResolvedValue(mockMetadata);
    render(<AdminLearningEnginePage />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Bayesian Knowledge Tracing" })).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Modified SM-2" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Voice Feedback Engine" })).toBeInTheDocument();
  });

  it("marks provisional/unvalidated parameters as needing calibration, not as validated", async () => {
    vi.mocked(getLearningEngineMetadata).mockResolvedValue(mockMetadata);
    render(<AdminLearningEnginePage />);

    await waitFor(() => expect(screen.getByText(/Needs pilot\/human-rater calibration/)).toBeInTheDocument());
    expect(screen.getByText(/Needs human-rater calibration/)).toBeInTheDocument();
  });

  it("distinguishes a progression-gating threshold from a diagnostic-only one", async () => {
    vi.mocked(getLearningEngineMetadata).mockResolvedValue(mockMetadata);
    render(<AdminLearningEnginePage />);

    const gatingRow = (await screen.findByText("SYLLABLE_PASS_THRESHOLD")).closest("tr");
    expect(gatingRow).not.toBeNull();
    expect(gatingRow!.textContent).toContain("Yes");

    const diagnosticRow = screen.getByText("TONE_CONFIRM_THRESHOLD").closest("tr");
    expect(diagnosticRow).not.toBeNull();
    expect(diagnosticRow!.textContent).toContain("diagnostic only");
  });

  it("never renders anything resembling an API key", async () => {
    vi.mocked(getLearningEngineMetadata).mockResolvedValue(mockMetadata);
    const { container } = render(<AdminLearningEnginePage />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Bayesian Knowledge Tracing" })).toBeInTheDocument());
    expect(container.textContent).not.toMatch(/sk-|gsk_|AIza/);
  });

  it("shows an error message when the metadata fetch fails", async () => {
    vi.mocked(getLearningEngineMetadata).mockRejectedValue(new Error("Could not load Learning Engine metadata."));
    render(<AdminLearningEnginePage />);

    await waitFor(() => expect(screen.getByText("Could not load Learning Engine metadata.")).toBeInTheDocument());
  });
});
