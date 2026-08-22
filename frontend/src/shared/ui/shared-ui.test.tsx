import { fireEvent, render, screen } from "@testing-library/react";
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

  it("closes an open modal with Escape", () => {
    const onClose = vi.fn();
    render(<Modal open title="Confirm" onClose={onClose}>Body</Modal>);

    fireEvent.keyDown(document, { key: "Escape" });
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
