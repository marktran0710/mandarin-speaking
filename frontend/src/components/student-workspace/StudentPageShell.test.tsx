import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StudentPageShell from "./StudentPageShell";

describe("StudentPageShell", () => {
  it("exposes one canonical template contract for each student page", () => {
    render(
      <StudentPageShell template="dashboard" pageId="my-learning" data-testid="dashboard-shell">
        <p>Progress content</p>
      </StudentPageShell>,
    );

    const shell = screen.getByTestId("dashboard-shell");
    expect(shell).toHaveClass("student-page-shell", "student-page-shell--dashboard");
    expect(shell).toHaveAttribute("data-student-template", "dashboard");
    expect(shell).toHaveAttribute("data-student-page", "my-learning");
  });

  it("creates the shared student page boundary without a competing landmark", () => {
    render(
      <StudentPageShell variant="quiz" data-testid="student-page-shell">
        <p>Placement content</p>
      </StudentPageShell>,
    );

    const shell = screen.getByTestId("student-page-shell");
    expect(shell).toHaveClass("student-page-shell", "student-page-shell--quiz");
    expect(shell).not.toHaveAttribute("role");
    expect(screen.getByText("Placement content")).toBeInTheDocument();
  });

  it("exposes semantic layout ownership and a stable page identity", () => {
    render(
      <StudentPageShell layout="stage" pageId="story-practice" data-testid="stage-shell">
        <p>Story practice content</p>
      </StudentPageShell>,
    );

    const shell = screen.getByTestId("stage-shell");
    expect(shell).toHaveClass("student-page-shell", "student-page-shell--stage");
    expect(shell).toHaveAttribute("data-student-page", "story-practice");
    expect(shell).not.toHaveAttribute("role");
    expect(screen.getByText("Story practice content").parentElement)
      .toHaveClass("student-page-shell__rail");
  });
});
