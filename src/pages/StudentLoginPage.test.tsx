import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import StudentLoginPage from "./StudentLoginPage";

describe("StudentLoginPage behavior", () => {
  it("shows a validation message without credentials", async () => {
    const user = userEvent.setup();
    render(<StudentLoginPage onLogin={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /Enter Student Mode/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("Please enter a name and password.");
  });

  it("rejects a wrong password and accepts a provisioned student account", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(new Response("{}", { status: 401 }))
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({ id: "student-1", name: "Minh", createdAt: "now" }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        ),
    );
    render(<StudentLoginPage onLogin={onLogin} />);

    await user.type(screen.getByLabelText(/Student name/), "Minh");
    await user.type(screen.getByLabelText(/Password/), "wrong");
    await user.click(screen.getByRole("button", { name: /Enter Student Mode/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("Wrong password");
    expect(onLogin).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText(/Password/));
    await user.type(screen.getByLabelText(/Password/), "correct-password");
    await user.click(screen.getByRole("button", { name: /Enter Student Mode/ }));
    expect(onLogin).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem("studentSession")).toContain("Minh");
  });
});
