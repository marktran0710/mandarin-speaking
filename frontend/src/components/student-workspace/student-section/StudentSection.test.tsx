import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  StudentSection,
  StudentSectionBody,
  StudentSectionFooter,
  StudentSectionHeader,
} from "./StudentSection";

describe("StudentSection", () => {
  it("connects a visible section heading to its semantic section", () => {
    render(
      <StudentSection variant="surface" aria-labelledby="progress-heading">
        <StudentSectionHeader headingId="progress-heading" title="Overall progress" />
        <StudentSectionBody layout="grid">Metrics</StudentSectionBody>
      </StudentSection>,
    );

    const section = screen.getByRole("region", { name: "Overall progress" });
    expect(section).toHaveClass("student-section", "student-section--surface");
    expect(screen.getByRole("heading", { name: "Overall progress", level: 2 })).toHaveAttribute(
      "id",
      "progress-heading",
    );
    expect(screen.getByText("Metrics")).toHaveClass("student-section__body--grid");
  });

  it("supports an aria label, optional action and aligned footer", () => {
    render(
      <StudentSection variant="task" aria-label="Placement question">
        <StudentSectionHeader title="Question" action={<button>Help</button>} />
        <StudentSectionBody layout="task">Prompt</StudentSectionBody>
        <StudentSectionFooter align="center">
          <button>Next</button>
        </StudentSectionFooter>
      </StudentSection>,
    );

    expect(screen.getByRole("region", { name: "Placement question" })).toHaveClass(
      "student-section--task",
    );
    expect(screen.getByRole("button", { name: "Help" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" }).parentElement).toHaveClass(
      "student-section__footer--center",
    );
  });
});

