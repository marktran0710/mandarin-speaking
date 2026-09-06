import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StudentModeFrame from "./StudentModeFrame";

describe("StudentModeFrame", () => {
  it("provides one main landmark with a first-focusable skip link", () => {
    render(
      <StudentModeFrame activeView="practice" onChange={vi.fn()} studentName="Ada" onLogout={vi.fn()} totalStars={0} maxStars={0} ariaLabel="Learning workspace">
        <p>Practice content</p>
      </StudentModeFrame>,
    );

    const skipLink = screen.getByRole("link", { name: "Skip to learning content" });
    expect(document.querySelector("a, button, input, select, textarea, [tabindex]")).toBe(skipLink);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("main", { name: "Learning workspace" })).toHaveAttribute("id", "student-workspace-panel");
  });
});
