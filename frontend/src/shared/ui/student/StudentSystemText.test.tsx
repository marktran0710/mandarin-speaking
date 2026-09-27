import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StudentSystemText from "./StudentSystemText";

describe("StudentSystemText", () => {
  it("shows Chinese UI copy and keeps English out of the primary label by default", () => {
    render(<StudentSystemText k="useIt" />);
    expect(screen.getByText("運用")).toBeInTheDocument();
    expect(screen.queryByText("Use it", { selector: ".sa-system-text__en" })).not.toBeInTheDocument();
    expect(screen.getByRole("tooltip")).toHaveTextContent("Yùnyòng");
  });

  it("supports keyboard focus and touch opening", () => {
    render(<StudentSystemText k="progress" />);
    const text = screen.getByText("進度").closest(".sa-system-text") as HTMLElement;
    expect(text).toHaveAttribute("tabindex", "0");
    fireEvent.focus(text);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Jìndù");
    fireEvent.pointerDown(text, { pointerType: "touch" });
    expect(text).toHaveAttribute("data-touch-open", "true");
  });

  it("keeps the English meaning beside pinyin when the catalog provides one", () => {
    render(<StudentSystemText k="progress" />);
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toHaveTextContent("Jìndù");
    expect(tooltip).toHaveTextContent("Progress");
  });

  it("does not add an extra tab stop inside a control", () => {
    render(<button type="button"><StudentSystemText k="start" withinControl /></button>);
    expect(screen.getByRole("button")).toBeInTheDocument();
    expect(screen.getByText("開始").closest(".sa-system-text")).not.toHaveAttribute("tabindex");
  });

  it("keeps control copy available without adding a tab stop", () => {
    render(<button type="button"><StudentSystemText k="useIt" withinControl /></button>);
    const text = screen.getByText("運用").closest(".sa-system-text");
    expect(text).toHaveClass("is-within-control");
    expect(text?.querySelector('[role="tooltip"]')).toBeInTheDocument();
  });

  it("can show the English gloss inline only when explicitly requested", () => {
    render(<StudentSystemText k="start" english="supporting" />);
    expect(screen.getByText("Start", { selector: ".sa-system-text__en" })).toBeVisible();
  });
});
