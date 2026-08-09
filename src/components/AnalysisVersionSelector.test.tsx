import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AnalysisVersionSelector from "./AnalysisVersionSelector";

describe("AnalysisVersionSelector", () => {
  it("keeps Stable V1 selected and disables unavailable V2", () => {
    render(<AnalysisVersionSelector value="stable_v1" onChange={vi.fn()} experimentalAvailable={false} />);
    expect(screen.getByRole("button", { name: /Stable V1/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Experimental V2/ })).toBeDisabled();
  });

  it("allows switching to V2 when the health check is ready", () => {
    const onChange = vi.fn();
    render(<AnalysisVersionSelector value="stable_v1" onChange={onChange} experimentalAvailable />);
    fireEvent.click(screen.getByRole("button", { name: /Experimental V2/ }));
    expect(onChange).toHaveBeenCalledWith("phoneme_tone_v2");
  });
});
