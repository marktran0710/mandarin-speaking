import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import ManagementApp from "./ManagementApp";

describe("ManagementApp route permissions", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows access denied when a teacher opens an admin-only area", async () => {
    localStorage.setItem(
      "teacherSession",
      JSON.stringify({ role: "teacher", name: "QA Teacher", signedInAt: new Date().toISOString() }),
    );

    render(<ManagementApp initialSection="accounts" />);

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(screen.getByText(/not available to the teacher role/i)).toBeInTheDocument();
  });

  it("keeps story materials admin-only", async () => {
    localStorage.setItem(
      "teacherSession",
      JSON.stringify({ role: "teacher", name: "QA Teacher", signedInAt: new Date().toISOString() }),
    );

    render(<ManagementApp initialSection="stories" />);

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(screen.getByText(/not available to the teacher role/i)).toBeInTheDocument();
  });
});
