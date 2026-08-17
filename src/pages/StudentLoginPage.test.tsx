import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import StudentLoginPage from "./StudentLoginPage";

describe("StudentLoginPage behavior", () => {
  it("shows a validation message without credentials", async () => {
    const user = userEvent.setup();
    render(<StudentLoginPage onLogin={vi.fn()} onBack={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /Enter Student Mode/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("Please enter a name and password.");
  });

  it("rejects a wrong offline password and accepts the shared demo password", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn();
    render(<StudentLoginPage onLogin={onLogin} onBack={vi.fn()} />);

    await user.type(screen.getByLabelText(/Student name/), "Minh");
    await user.type(screen.getByLabelText(/Password/), "wrong");
    await user.click(screen.getByRole("button", { name: /Enter Student Mode/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("Wrong password");
    expect(onLogin).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText(/Password/));
    await user.type(screen.getByLabelText(/Password/), "123456");
    await user.click(screen.getByRole("button", { name: /Enter Student Mode/ }));
    expect(onLogin).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem("studentSession")).toContain("Minh");
  });
});
