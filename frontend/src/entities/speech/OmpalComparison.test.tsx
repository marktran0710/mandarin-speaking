import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PronunciationEvaluation } from "@shared/api/pronunciation";
import OmpalComparison from "./OmpalComparison";

const result = {
  ompal_comparison: { status: "scored", source: "ompal_api", scores: { accuracy: 4.5, fluency: 4.4, prosody: 4.3 }, model_version: "v2" },
} as PronunciationEvaluation;

describe("OMPAL comparison", () => {
  it("shows only the OMPAL speaking scores", () => {
    render(<OmpalComparison result={result} />);
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("4.50 / 5");
    expect(rows[3]).toHaveTextContent("4.30 / 5");
    expect(screen.getByText(/OMPAL provides the speaking score/)).toBeInTheDocument();
  });
  it("keeps an unavailable comparison separate", () => {
    render(<OmpalComparison result={{ ...result, ompal_comparison: { status: "unavailable", source: "ompal_api", reason: "timeout" } }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Praat visualisation and AI feedback remain available");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
  it("does not add a panel to legacy records", () => {
    const { container } = render(<OmpalComparison result={{ ...result, ompal_comparison: undefined }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
