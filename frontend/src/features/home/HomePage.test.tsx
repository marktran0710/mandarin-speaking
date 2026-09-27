import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import HomePage from "./HomePage";

describe("HomePage student entry", () => {
  it("keeps the home entry focused and routes Start Learning to student login", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    render(<HomePage onNavigate={onNavigate} />);

    expect(screen.getByRole("heading", { name: /慢慢中文/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /從發音到應用/ })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "使用方式" })).not.toBeInTheDocument();
    expect(screen.queryByText("看圖片")).not.toBeInTheDocument();
    expect(screen.queryByText("說故事")).not.toBeInTheDocument();
    expect(screen.queryByText("看回饋")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "開始學習" }));
    expect(onNavigate).toHaveBeenCalledWith("student-login");
  });
});
