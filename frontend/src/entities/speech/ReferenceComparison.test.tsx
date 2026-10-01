import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PronunciationReferenceComparison } from "@shared/api/pronunciation";
import ReferenceComparison from "./ReferenceComparison";

vi.mock("../../components/pitch/LibrosaPitchChart", () => ({
  default: () => <div role="img" aria-label="老師與學生音高比較" />,
}));

const comparison: PronunciationReferenceComparison = {
  status: "scored", backend: "librosa", evidence_quality: "full",
  measurements: { mfcc_similarity: .8, pitch_similarity: .9, timing_similarity: .7 },
  contours: { reference: [[0, 0], [1, 2]], student: [[0, 0], [1, 1]] },
};

describe("learner reference comparison", () => {
  it("shows the aligned chart and labels similarity separately from accuracy", async () => {
    render(<ReferenceComparison comparison={comparison} />);
    expect(await screen.findByRole("img", { name: "老師與學生音高比較" })).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.getByText("90%")).toBeInTheDocument();
    expect(screen.getByText(/不代表發音正確率/)).toBeInTheDocument();
  });

  it("retains sound and timing similarity when paired pitch is unavailable", () => {
    render(<ReferenceComparison comparison={{
      ...comparison,
      evidence_quality: "degraded",
      measurements: { ...comparison.measurements, pitch_similarity: null },
      contours: { reference: [[0, null]], student: [[0, null]] },
    }} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText(/這次音高資料不足/)).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("explains an unavailable comparison without inventing percentages", () => {
    render(<ReferenceComparison comparison={{
      status: "unavailable", backend: "librosa", reason: "librosa_not_installed",
      measurements: {}, contours: { reference: [], student: [] },
    }} />);
    expect(screen.getByText("這次暫無可用的示範音比較。")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });
});
