import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StudentModeFrame from "./StudentModeFrame";
import StudentPageShell from "./StudentPageShell";

describe("StudentModeFrame", () => {
  it("provides one main landmark with a first-focusable skip link", () => {
    render(
      <StudentModeFrame activeView="practice" onChange={vi.fn()} studentName="Ada" onLogout={vi.fn()} totalStars={0} maxStars={0} ariaLabel="Learning workspace">
        <StudentPageShell template="catalogue" pageId="lessons">
          <p>Practice content</p>
        </StudentPageShell>
      </StudentModeFrame>,
    );

    const skipLink = screen.getByRole("link", { name: "Skip to learning content" });
    expect(document.querySelector("a, button, input, select, textarea, [tabindex]")).toBe(skipLink);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    const panel = screen.getByRole("main", { name: "Learning workspace" });
    expect(panel).toHaveAttribute("id", "student-workspace-panel");
    expect(panel.querySelectorAll(":scope > .student-page-shell")).toHaveLength(1);
    expect(panel.querySelector(":scope > .student-page-shell")).toHaveAttribute("data-student-page", "lessons");
  });
});
