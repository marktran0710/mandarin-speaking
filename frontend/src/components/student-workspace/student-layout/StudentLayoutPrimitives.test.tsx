import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  StudentActionBar,
  StudentGrid,
  StudentPageBody,
  StudentRow,
  StudentStack,
} from "./StudentLayoutPrimitives";

describe("StudentLayoutPrimitives", () => {
  it("exposes one page body contract and preserves the hierarchy primitives", () => {
    render(
      <StudentPageBody variant="flow" data-testid="page-body">
        <StudentStack density="section">
          <StudentGrid columns={3} data-testid="grid">
            <StudentRow data-testid="row">Row</StudentRow>
          </StudentGrid>
          <StudentActionBar align="between">Actions</StudentActionBar>
        </StudentStack>
      </StudentPageBody>,
    );

    expect(screen.getByTestId("page-body")).toHaveAttribute("data-student-body", "flow");
    expect(screen.getByTestId("grid")).toHaveClass("student-grid--3");
    expect(screen.getByTestId("row")).toHaveClass("student-row");
    expect(screen.getByText("Actions")).toHaveClass("student-action-bar--between");
  });
});
