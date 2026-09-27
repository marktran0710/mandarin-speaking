import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import HomePage from "./HomePage";

describe("HomePage student entry", () => {
  it("communicates the three-step learning loop and routes Start Learning to student login", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    render(<HomePage onNavigate={onNavigate} />);

    expect(screen.getByRole("heading", { name: /慢慢中文/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /從發音到應用/ })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "使用方式" })).toBeInTheDocument();
    expect(screen.getByText("看圖片")).toBeInTheDocument();
    expect(screen.getByText("說故事")).toBeInTheDocument();
    expect(screen.getByText("看回饋")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "開始學習" }));
    expect(onNavigate).toHaveBeenCalledWith("student-login");
  });
});
