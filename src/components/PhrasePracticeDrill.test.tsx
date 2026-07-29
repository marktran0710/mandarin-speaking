import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PhrasePracticeDrill from "./PhrasePracticeDrill";

describe("PhrasePracticeDrill", () => {
  it("shows one target phrase and explains the pitch comparison bilingually", () => {
    render(<PhrasePracticeDrill phrase="你這個週末" onPass={() => undefined} />);

    expect(screen.getByLabelText("Practice phrase 你這個週末")).toBeInTheDocument();
    expect(
      screen.getByText("Say this part on its own. Each word should match its target pitch shape."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Record this part/ }),
    ).toBeInTheDocument();
  });
});
