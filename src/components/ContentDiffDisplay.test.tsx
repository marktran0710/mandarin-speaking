import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ContentDiffDisplay from "./ContentDiffDisplay";

describe("ContentDiffDisplay", () => {
  it("highlights replacement text on both sides", () => {
    render(
      <ContentDiffDisplay
        target="abc"
        heard="axc"
        contentMatch={false}
        diff={[
          { type: "match", target: "a", heard: "a" },
          { type: "replace", target: "b", heard: "x" },
          { type: "match", target: "c", heard: "c" },
        ]}
      />,
    );

    expect(screen.getByText("b").tagName).toBe("STRONG");
    expect(screen.getByText("x").tagName).toBe("STRONG");
    expect(screen.getAllByText("a").every((node) => node.tagName === "SPAN")).toBe(true);
  });

  it("uses a neutral message when speech cannot be verified", () => {
    const { container } = render(
      <ContentDiffDisplay target="abc" heard={null} contentMatch={null} />,
    );

    expect(
      screen.getByText("We couldn't verify the words in this recording. Please record it again."),
    ).toBeInTheDocument();
    expect(container.querySelector("strong")).toBeNull();
  });
});
