import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminAlgorithmVerifierPage from "./AdminAlgorithmVerifierPage";
import AdminBktVerificationPage from "./AdminBktVerificationPage";
import { getAlgorithmVerifierBootstrap, runBktVerification, runSm2Verification } from "../../services/api/algorithm-verifier";

vi.mock("./AdminBktVerificationPage", () => ({
  default: vi.fn(() => <section aria-label="Live BKT panel" />),
}));

vi.mock("../../services/api/algorithm-verifier", () => ({
  getAlgorithmVerifierBootstrap: vi.fn(),
  runBktVerification: vi.fn(),
  runSm2Verification: vi.fn(),
}));

const verifierBootstrap = {
  model: {}, golden: { summary: { passed: 7, total: 7 } }, contractStatus: "PASS", sm2: {},
  baselineSuites: { bkt: "PASS", sm2: "PASS" } as const,
  integration: { enabled: false, studentId: "verifier", runId: "run", fixture: null, fixtureError: null },
};

beforeEach(() => {
  vi.mocked(getAlgorithmVerifierBootstrap).mockReset().mockResolvedValue(verifierBootstrap);
  vi.mocked(runSm2Verification).mockReset();
  vi.mocked(runBktVerification).mockReset();
  vi.mocked(AdminBktVerificationPage).mockClear();
});

describe("BKT preset inputs", () => {
  it("selects a stored candidate for parameters, Recovery and live traces without activation", async () => {
    const modelVersion = "bkt-synthetic-candidate-demo";
    vi.mocked(getAlgorithmVerifierBootstrap).mockResolvedValueOnce({ ...verifierBootstrap, candidates: [{
      modelVersion, evidenceOrigin: "synthetic", promotable: false, fitStatus: "completed",
      parameters: { prior: 0.261835, learn: 0.13131, guess: 0.25752, slip: 0.089203, guess_typed: 0.045928, slip_typed: 0.152189 },
      counts: { records: 4480, students: 40, concepts: 28 }, metrics: { production: { log_loss: 0.614583 }, candidate: { log_loss: 0.604577 } },
      gates: { evidence: true }, impact: null,
    }] });
    const user = userEvent.setup();
    render(<AdminAlgorithmVerifierPage />);
    await user.selectOptions(await screen.findByRole("combobox", { name: "BKT model" }), modelVersion);
    expect(screen.getByRole("spinbutton", { name: "Previous P(L)" })).toHaveValue(0.261835);
    expect(screen.getByRole("spinbutton", { name: "P(T)" })).toHaveValue(0.13131);
    expect(screen.getByRole("region", { name: "BKT parameter selection" })).toHaveTextContent("0.045928");
    expect(vi.mocked(AdminBktVerificationPage).mock.calls.at(-1)?.[0].modelVersion).toBe(modelVersion);
    vi.mocked(runBktVerification).mockResolvedValue({ result: "PASS" });
    await user.click(screen.getByRole("button", { name: "Recovery" }));
    await user.click(screen.getByRole("button", { name: "Run BKT update" }));
    expect(runBktVerification).toHaveBeenCalledWith(expect.objectContaining({ modelVersion, prior: 0.261835, guess: 0.25752, learnRate: 0.13131 }));
    await user.selectOptions(screen.getByRole("combobox", { name: "BKT model" }), "");
    expect(screen.getByRole("spinbutton", { name: "Previous P(L)" })).toHaveValue(0.2);
    expect(screen.queryByLabelText("Selected BKT sequence")).not.toBeInTheDocument();
  });

  it("replaces typed wrong and custom inputs immediately with a complete MCQ sequence", async () => {
    const user = userEvent.setup();
    render(<AdminAlgorithmVerifierPage />);
    await user.click(await screen.findByRole("button", { name: "Typed wrong" }));
    fireEvent.change(screen.getByRole("spinbutton", { name: "Previous P(L)" }), { target: { value: "0.8" } });
    fireEvent.change(screen.getByRole("spinbutton", { name: "P(T)" }), { target: { value: "0.3" } });
    await user.click(screen.getByRole("button", { name: "3 MCQ successes" }));

    expect(screen.getByRole("combobox", { name: "Format" })).toHaveValue("mcq");
    expect(screen.getByRole("combobox", { name: "Answer" })).toHaveValue("correct");
    expect(screen.getByRole("spinbutton", { name: "Previous P(L)" })).toHaveValue(0.2);
    expect(screen.getByRole("spinbutton", { name: "P(T)" })).toHaveValue(0.15);
    expect(screen.getByRole("spinbutton", { name: "Guess" })).toHaveValue(0.2);
    expect(screen.getByRole("spinbutton", { name: "Slip" })).toHaveValue(0.1);
    expect(screen.getByRole("button", { name: "3 MCQ successes" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Selected BKT sequence")).toHaveTextContent("MCQ correct → MCQ correct → MCQ correct");
    expect(runBktVerification).not.toHaveBeenCalled();

    vi.mocked(runBktVerification).mockResolvedValue({ result: "PASS" });
    await user.click(screen.getByRole("button", { name: "Run BKT update" }));
    expect(runBktVerification).toHaveBeenCalledWith(expect.objectContaining({
      prior: 0.2, questionFormat: "mcq", correct: true, guess: 0.2, slip: 0.1,
      observations: Array.from({ length: 3 }, () => ({ correct: true, questionFormat: "mcq" })),
    }));
  });

  it("loads typed sequence defaults from production and removes the sequence for a single answer", async () => {
    vi.mocked(getAlgorithmVerifierBootstrap).mockResolvedValueOnce({
      ...verifierBootstrap,
      model: { parameters: { P_L0_initial_mastery: { value: 0.25 }, P_T_learn_rate: { value: 0.12 }, P_G_guess_typed: { value: 0.06 }, P_S_slip_typed: { value: 0.16 } } },
    });
    const user = userEvent.setup();
    render(<AdminAlgorithmVerifierPage />);
    await user.click(await screen.findByRole("button", { name: "3 typed successes" }));
    expect(screen.getByRole("combobox", { name: "Format" })).toHaveValue("typed");
    expect(screen.getByRole("combobox", { name: "Answer" })).toHaveValue("correct");
    expect(screen.getByRole("spinbutton", { name: "Guess" })).toHaveValue(0.06);
    expect(screen.getByRole("spinbutton", { name: "Slip" })).toHaveValue(0.16);
    expect(screen.getByRole("spinbutton", { name: "Previous P(L)" })).toHaveValue(0.25);
    expect(screen.getByRole("spinbutton", { name: "P(T)" })).toHaveValue(0.12);
    expect(screen.getByLabelText("Selected BKT sequence")).toHaveTextContent("Typed correct → Typed correct → Typed correct");

    await user.click(screen.getByRole("button", { name: "Typed wrong" }));
    expect(screen.queryByLabelText("Selected BKT sequence")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "3 typed successes" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("combobox", { name: "Answer" })).toHaveValue("wrong");
    vi.mocked(runBktVerification).mockResolvedValue({ result: "FAIL" });
    await user.click(screen.getByRole("button", { name: "Run BKT update" }));
    expect(runBktVerification).toHaveBeenCalledWith({ prior: 0.25, questionFormat: "typed", correct: false, learnRate: 0.12, guess: 0.06, slip: 0.16 });
  });

  it("leaves live traces untouched by calculator edits and still refreshes them on request", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<AdminAlgorithmVerifierPage refreshKey={0} />);
    await screen.findByRole("region", { name: "Live BKT panel" });
    const renders = vi.mocked(AdminBktVerificationPage).mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Recovery" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Format" }), "typed");
    expect(screen.queryByLabelText("Selected BKT sequence")).not.toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "Guess" })).toHaveValue(0.05);
    expect(screen.getByRole("spinbutton", { name: "Slip" })).toHaveValue(0.15);
    expect(AdminBktVerificationPage).toHaveBeenCalledTimes(renders);
    rerender(<AdminAlgorithmVerifierPage refreshKey={1} />);
    expect(AdminBktVerificationPage).toHaveBeenCalledTimes(renders + 1);
  });
});

describe.each(["bkt", "sm2"] as const)("%s pending calculation", (tab) => {
  it.each(["result", "error"])("ignores an outdated %s when a preset changes", async (settlement) => {
    let resolve!: (result: Record<string, unknown>) => void;
    let reject!: (reason: Error) => void;
    const calculate = tab === "bkt" ? runBktVerification : runSm2Verification;
    vi.mocked(calculate).mockReturnValueOnce(new Promise((done, fail) => { resolve = done; reject = fail; }));
    const user = userEvent.setup();
    render(<AdminAlgorithmVerifierPage initialTab={tab} />);
    await user.click(await screen.findByRole("button", { name: tab === "bkt" ? "Run BKT update" : "Calculate review result" }));
    const preset = tab === "bkt" ? "Typed wrong" : "Failed due review";
    await user.click(screen.getByRole("button", { name: preset }));
    expect(screen.getByRole("button", { name: preset })).toHaveAttribute("aria-pressed", "true");
    if (tab === "bkt") expect(screen.getByRole("combobox", { name: "Answer" })).toHaveValue("wrong");
    else expect(screen.getByRole("spinbutton", { name: "Review quality (0-5)" })).toHaveValue(2);
    expect(calculate).toHaveBeenCalledTimes(1);
    await act(async () => {
      if (settlement === "result") resolve({ result: "FAIL", formula: { observation: "Outdated calculation" } });
      else reject(new Error("Outdated calculation"));
    });
    expect(screen.queryByText("FAIL")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getAllByText("NOT RUN")).toHaveLength(3);
  });

  it("clears an existing result after manually editing the inputs", async () => {
    const calculate = tab === "bkt" ? runBktVerification : runSm2Verification;
    vi.mocked(calculate).mockResolvedValue({ result: "FAIL" });
    const user = userEvent.setup();
    render(<AdminAlgorithmVerifierPage initialTab={tab} />);
    await user.click(await screen.findByRole("button", { name: tab === "bkt" ? "Run BKT update" : "Calculate review result" }));
    await screen.findAllByText("FAIL");
    fireEvent.change(screen.getByRole("spinbutton", { name: tab === "bkt" ? "Guess" : "Ease before review" }), { target: { value: tab === "bkt" ? "0.3" : "2.8" } });
    expect(screen.queryByText("FAIL")).not.toBeInTheDocument();
  });
});

describe("SM-2 production lifecycle presets", () => {
  it("switches from enrollment to the first due review using the enrolled state", async () => {
    const user = userEvent.setup();
    render(<AdminAlgorithmVerifierPage initialTab="sm2" />);
    await user.click(await screen.findByRole("button", { name: "Enroll STRONG word (create first schedule)" }));
    expect(screen.getByRole("combobox", { name: "Operation" })).toHaveValue("enroll");
    expect(screen.getByRole("spinbutton", { name: "Review quality (0-5)" })).toBeDisabled();
    expect(screen.getByText(/no answer is graded and no quality is used/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "1st correct review after enrollment" }));
    expect(screen.getByRole("combobox", { name: "Operation" })).toHaveValue("review");
    expect(screen.getByRole("spinbutton", { name: "Repetitions before review" })).toHaveValue(1);
    expect(screen.getByRole("spinbutton", { name: "Interval before review (scheduling days)" })).toHaveValue(1);
    expect(screen.getByRole("spinbutton", { name: "Review quality (0-5)" })).toBeEnabled();
    vi.mocked(runSm2Verification).mockResolvedValue({
      inputs: { operation: "review", repetitions: 1, intervalDays: 1, ease: 2.5, quality: 4, now: "2026-08-02T00:00:00Z" },
      production: { repetitions: 2, intervalDays: 6, ease: 2.5, nextDue: "2026-08-08T00:00:00Z" },
      reference: { repetitions: 2, intervalDays: 6, ease: 2.5, nextDue: "2026-08-08T00:00:00Z" },
      result: "PASS", rawInterval: null,
    });
    await user.click(screen.getByRole("button", { name: "Calculate review result" }));
    await waitFor(() => expect(runSm2Verification).toHaveBeenCalledWith(expect.objectContaining({ operation: "review", repetitions: 1, intervalDays: 1, ease: 2.5, quality: 4 })));
    const output = await screen.findByRole("region", { name: "SM-2 result after operation" });
    expect(within(output).getByRole("heading", { name: "After review: next schedule" })).toBeInTheDocument();
    expect(within(output).getByText(/Before review: rep=1, interval=1/)).toBeInTheDocument();
    expect(within(output).getAllByText("6 scheduling days")).toHaveLength(2);
    expect(within(output).getByText(/T0 \+ 7D \(6D after the review\)/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "2nd correct review after enrollment" }));
    expect(screen.queryByRole("region", { name: "SM-2 result after operation" })).not.toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "Repetitions before review" })).toHaveValue(2);
    expect(screen.getByRole("spinbutton", { name: "Interval before review (scheduling days)" })).toHaveValue(6);
  });

  it("keeps third maintenance review and relearning after failure distinct", async () => {
    const user = userEvent.setup();
    render(<AdminAlgorithmVerifierPage initialTab="sm2" />);
    await user.click(await screen.findByRole("button", { name: "3rd correct review after enrollment" }));
    expect(screen.getByRole("spinbutton", { name: "Repetitions before review" })).toHaveValue(3);
    expect(screen.getByRole("spinbutton", { name: "Interval before review (scheduling days)" })).toHaveValue(15);
    await user.click(screen.getByRole("button", { name: "Correct review after failure (rep 0)" }));
    expect(screen.getByRole("spinbutton", { name: "Repetitions before review" })).toHaveValue(0);
    expect(screen.getByRole("spinbutton", { name: "Interval before review (scheduling days)" })).toHaveValue(1);
    expect(screen.getByRole("spinbutton", { name: "Ease before review" })).toHaveValue(2.18);
  });
});
