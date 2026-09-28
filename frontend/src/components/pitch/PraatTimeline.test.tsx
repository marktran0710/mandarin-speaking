import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PraatTimeline from "./PraatTimeline";

const pitchContour: Array<[number, number]> = [[0.1, 110], [0.5, 130], [0.9, 100]];

describe("PraatTimeline model voice line", () => {
  it("draws the model voice line with its legend when an overlay lines up", () => {
    const { container } = render(
      <PraatTimeline
        pitchContour={pitchContour}
        modelOverlay={{ status: "ok", segments: [{ wordIndex: 0, points: [[0.1, 120], [0.9, 105]] }] }}
      />,
    );
    expect(screen.getByText("model voice")).toBeInTheDocument();
    expect(screen.queryByText("target shape")).not.toBeInTheDocument();
    // Student line + one model segment.
    expect(container.querySelectorAll("path[fill='none']").length).toBe(2);
  });

  it("explains a missing model voice instead of drawing a stand-in target", () => {
    const { container } = render(<PraatTimeline pitchContour={pitchContour} modelOverlay={{ status: "missing" }} />);
    expect(screen.getByText("No model voice for this sentence yet")).toBeInTheDocument();
    expect(screen.queryByText("model voice")).not.toBeInTheDocument();
    expect(container.querySelectorAll("path[fill='none']").length).toBe(1);
  });

  it("hides the model voice when the learner said a different sentence", () => {
    render(<PraatTimeline pitchContour={pitchContour} modelOverlay={{ status: "mismatch" }} />);
    expect(screen.getByText("You said a different sentence, so the model voice is hidden")).toBeInTheDocument();
  });
});
