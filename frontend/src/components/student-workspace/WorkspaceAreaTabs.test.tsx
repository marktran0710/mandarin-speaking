import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import WorkspaceAreaTabs from "./WorkspaceAreaTabs";

const views = [
  { id: "practice" as const, icon: "image" as const, label: { zh: "課程", pinyin: "Kèchéng", en: "Practice" } },
  { id: "progress" as const, icon: "chart" as const, label: { zh: "我的學習", pinyin: "Wǒ de xuéxí", en: "Progress" } },
];

describe("WorkspaceAreaTabs", () => {
  it("moves between tabs with arrow keys and preserves roving tab focus", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<WorkspaceAreaTabs views={views} activeView="practice" onChange={onChange} />);

    const practice = screen.getByRole("tab", { name: /Practice/ });
    practice.focus();
    await user.keyboard("{ArrowRight}");

    expect(onChange).toHaveBeenCalledWith("progress");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: /Progress/ }));
  });
});
