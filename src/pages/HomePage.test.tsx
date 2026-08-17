import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import HomePage from "./HomePage";

describe("HomePage student entry", () => {
  it("communicates the three-step learning loop and routes Start Learning to student login", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    render(<HomePage onNavigate={onNavigate} />);

    expect(screen.getByRole("heading", { name: /Mandarin, little by little/ })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "How it works" })).toBeInTheDocument();
    expect(screen.getByText("Look")).toBeInTheDocument();
    expect(screen.getByText("Speak")).toBeInTheDocument();
    expect(screen.getByText("Improve")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Start Learning/ }));
    expect(onNavigate).toHaveBeenCalledWith("student-login");
  });
});

