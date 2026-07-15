import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import MiniContourChart from "./MiniContourChart";

/** Parse every y coordinate out of an SVG path's "M x y L x y …" string. */
function pathYs(d: string): number[] {
  return (d.match(/[ML] [\d.]+ ([\d.]+)/g) ?? []).map((seg) =>
    Number(seg.split(" ")[2]),
  );
}

describe("MiniContourChart normalized mode", () => {
  const flatUser = Array.from({ length: 20 }, () => 0.5);
  const fallingTarget = Array.from(
    { length: 20 },
    (_, i) => 0.85 - (i / 19) * 0.5,
  );

  it("draws a flat attempt as a flat midline while the target keeps its swing (fixed scale)", () => {
    const { container } = render(
      <MiniContourChart
        actual={[]}
        userCurve={flatUser}
        targetCurve={fallingTarget}
      />,
    );
    const [targetPath, userPath] = Array.from(
      container.querySelectorAll("path"),
    ).map((p) => p.getAttribute("d")!);

    const userYs = pathYs(userPath);
    const targetYs = pathYs(targetPath);
    // The old raw-Hz overlay rescaled the target into the student's own
    // range, so a flat attempt squashed the target flat too and the chart
    // claimed a match the score denied. On the fixed normalized scale the
    // flat attempt stays flat and the target keeps its full movement.
    expect(Math.max(...userYs) - Math.min(...userYs)).toBeLessThan(2);
    expect(Math.max(...targetYs) - Math.min(...targetYs)).toBeGreaterThan(20);
  });

  it("draws near-identical paths when the user matches the target shape", () => {
    const { container } = render(
      <MiniContourChart
        actual={[]}
        userCurve={fallingTarget}
        targetCurve={fallingTarget}
      />,
    );
    const [targetPath, userPath] = Array.from(
      container.querySelectorAll("path"),
    ).map((p) => p.getAttribute("d")!);
    expect(userPath).toBe(targetPath);
  });

  it("falls back to the raw-Hz mode when no normalized curves are given", () => {
    const { container } = render(
      <MiniContourChart
        actual={[
          [0, 200],
          [0.5, 260],
        ]}
      />,
    );
    expect(container.querySelectorAll("path")).toHaveLength(1);
  });
});
