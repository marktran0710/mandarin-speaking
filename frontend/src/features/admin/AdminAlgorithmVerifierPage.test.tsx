import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminAlgorithmVerifierPage from "./AdminAlgorithmVerifierPage";
import { getAlgorithmVerifierBootstrap, runSm2Verification } from "../../services/api/algorithm-verifier";

vi.mock("../../services/api/algorithm-verifier", () => ({
  getAlgorithmVerifierBootstrap: vi.fn(),
  runSm2Verification: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(getAlgorithmVerifierBootstrap).mockReset().mockResolvedValue({
    model: {}, golden: { summary: { passed: 7, total: 7 } }, contractStatus: "PASS", sm2: {},
    baselineSuites: { bkt: "PASS", sm2: "PASS" },
    integration: { enabled: false, studentId: "verifier", runId: "run", fixture: null, fixtureError: null },
  });
  vi.mocked(runSm2Verification).mockReset();
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
