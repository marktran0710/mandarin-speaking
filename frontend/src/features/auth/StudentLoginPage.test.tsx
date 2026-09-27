import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import StudentLoginPage from "./StudentLoginPage";
import { currentRole } from "../../utils/session";

describe("StudentLoginPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("creates a student session from the dedicated login form", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "student-42",
            name: "Student 42",
            createdAt: "2026-08-22T00:00:00.000Z",
            status: "active",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    render(<StudentLoginPage onLogin={onLogin} />);
    await user.type(screen.getByPlaceholderText("打上你的名字"), "Student 42");
    await user.type(screen.getByPlaceholderText("輸入教師提供的密碼"), "123456");
    await user.click(screen.getByRole("button", { name: "進入學生模式" }));

    expect(onLogin).toHaveBeenCalledOnce();
    expect(currentRole("student")).toBe("student");
    expect(JSON.parse(localStorage.getItem("studentSession") ?? "{}")).toMatchObject({
      id: "student-42",
      name: "Student 42",
      role: "student",
    });

    vi.unstubAllGlobals();
  });
});
