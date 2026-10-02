import { render, screen } from "@testing-library/react";
import AdminBktDebugPage from "./AdminBktDebugPage";
import { getBktVerificationBootstrap } from "../../services/api/bkt-verification";
import { injectBktDebugResponses } from "../../services/api/bkt-debug";

vi.mock("../../services/api/stories-submissions", () => ({ listCustomStories: vi.fn().mockResolvedValue([]) }));
vi.mock("../../services/api/bkt-verification", () => ({ getBktVerificationBootstrap: vi.fn() }));
vi.mock("../../services/api/bkt-debug", () => ({ injectBktDebugResponses: vi.fn() }));

it("labels the active synthetic fit without injecting any debug evidence", async () => {
  vi.mocked(getBktVerificationBootstrap).mockResolvedValue({ model: { fitProvenance: { modelVersion: "bkt-synthetic-active", evidenceOrigin: "SYNTHETIC" as const, synthetic: true, label: "Simulation fit only; not human pilot calibration." } } } as Awaited<ReturnType<typeof getBktVerificationBootstrap>>);
  render(<AdminBktDebugPage students={[]} />);
  expect(await screen.findByText("SYNTHETIC FIT")).toBeInTheDocument();
  expect(screen.getByLabelText("Active BKT fit")).toHaveTextContent("not human pilot calibration");
  expect(injectBktDebugResponses).not.toHaveBeenCalled();
});

it("reports unknown fit provenance when the metadata request fails", async () => {
  vi.mocked(getBktVerificationBootstrap).mockRejectedValue(new Error("unavailable"));
  render(<AdminBktDebugPage students={[]} />);
  expect(await screen.findByText("FIT PROVENANCE UNKNOWN")).toBeInTheDocument();
  expect(screen.getByLabelText("Active BKT fit")).toHaveTextContent("do not treat as human pilot calibration");
});
