import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ManagementShell from "./ManagementShell";

describe("ManagementShell", () => {
  it("uses accessible SVG icons for navigation and keeps drawer focus contained", async () => {
    render(
      <ManagementShell role="teacher" activeView="overview" onSelectView={vi.fn()} onLogout={vi.fn()}>
        <p>Dashboard</p>
      </ManagementShell>,
    );

    expect(document.querySelectorAll(".management-nav-icon svg").length).toBeGreaterThan(0);

    const menu = screen.getByRole("button", { name: "Open menu" });
    menu.focus();
    fireEvent.click(menu);
    await waitFor(() => expect(screen.getByRole("button", { name: /Overview/ })).toHaveFocus());
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Open menu" })).toHaveFocus());
  });
});
