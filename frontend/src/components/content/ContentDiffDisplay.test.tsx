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

  it("renders the same target/heard shape (no shorter layout) when content matched", () => {
    // Regression guard: this case used to not render at all, which meant
    // the results card changed height between a correct attempt and a
    // wrong/unverified one.
    const { container } = render(
      <ContentDiffDisplay target="abc" heard="abc" contentMatch={true} />,
    );

    expect(screen.getByText("Matches the script.", { exact: false })).toBeInTheDocument();
    expect(container.querySelectorAll(".content-diff-line")).toHaveLength(2);
    expect(container.querySelector("strong")).toBeNull();
  });

  it("shows the target character when ASR used a pinyin-equivalent character", () => {
    const { container } = render(
      <ContentDiffDisplay
        target="友美妳這個週末要做什麼"
        heard="友美你這個週末要做什麼"
        contentMatch={true}
        diff={[
          { type: "match", target: "友美妳這個週末要做什麼", heard: "友美你這個週末要做什麼" },
        ]}
      />,
    );

    const heardLine = container.querySelectorAll(".content-diff-line")[1];
    expect(heardLine.textContent).toContain("友美妳這個週末要做什麼");
    expect(heardLine.textContent).not.toContain("友美你這個週末要做什麼");
  });

  it("keeps the same two-line-plus-status structure across matched, mismatched, and unverified", () => {
    const cases = [
      { contentMatch: true, heard: "abc" },
      { contentMatch: false, heard: "axc" },
      { contentMatch: null, heard: null },
    ] as const;

    const lineCounts = cases.map(({ contentMatch, heard }) => {
      const { container, unmount } = render(
        <ContentDiffDisplay target="abc" heard={heard} contentMatch={contentMatch} />,
      );
      const count = container.querySelectorAll(".content-diff-line, .content-diff-hint").length;
      unmount();
      return count;
    });

    expect(lineCounts).toEqual([3, 3, 3]);
  });
});
