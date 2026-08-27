import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DataTable from "./DataTable";
import Modal from "./Modal";
import Tabs from "./Tabs";

describe("shared UI primitives", () => {
  it("moves focus and selection with arrow keys", () => {
    const onChange = vi.fn();
    render(
      <Tabs
        ariaLabel="Areas"
        value="one"
        onChange={onChange}
        items={[{ id: "one", label: "One" }, { id: "two", label: "Two" }]}
      />,
    );

    fireEvent.keyDown(screen.getByRole("tab", { name: "One" }), { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith("two");
    expect(screen.getByRole("tab", { name: "Two" })).toHaveFocus();
  });

  it("traps focus, locks body scroll, and restores focus when closed", async () => {
    const onClose = vi.fn();
    render(<button type="button">Open modal</button>);
    const trigger = screen.getByRole("button", { name: "Open modal" });
    trigger.focus();
    const view = render(<Modal open title="Confirm" onClose={onClose}><button type="button">Action</button></Modal>);

    await waitFor(() => expect(screen.getByRole("button", { name: "Close" })).toHaveFocus());
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(screen.getByRole("button", { name: "Action" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    view.rerender(<Modal open={false} title="Confirm" onClose={onClose}>Body</Modal>);
    expect(document.body.style.overflow).toBe("");
    expect(trigger).toHaveFocus();
  });

  it("closes only when the backdrop itself is clicked", () => {
    const onClose = vi.fn();
    render(<Modal open title="Confirm" onClose={onClose}>Body</Modal>);
    const backdrop = document.querySelector(".ui-modal-backdrop");
    expect(backdrop).not.toBeNull();
    fireEvent.mouseDown(backdrop!);
    fireEvent.mouseDown(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders the empty state instead of an empty table", () => {
    render(
      <DataTable
        columns={[{ key: "name", header: "Name", render: (row: { name: string }) => row.name }]}
        rows={[]}
        rowKey={(row) => row.name}
        empty={<p>No learners yet</p>}
      />,
    );

    expect(screen.getByText("No learners yet")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
