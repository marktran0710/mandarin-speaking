import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import HomePage from "./HomePage";

describe("HomePage student entry", () => {
  it("keeps the home entry focused and routes Start Learning to student login", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    const { container } = render(<HomePage onNavigate={onNavigate} />);

    expect(container.firstElementChild).toHaveAttribute("lang", "zh-Hant");
    expect(screen.getByRole("heading", { name: /慢慢中文/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /從發音到應用/ })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "使用方式" })).not.toBeInTheDocument();
    expect(screen.queryByText("看圖片")).not.toBeInTheDocument();
    expect(screen.queryByText("說故事")).not.toBeInTheDocument();
    expect(screen.queryByText("看回饋")).not.toBeInTheDocument();

    const sceneImages = [...container.querySelectorAll<HTMLImageElement>(".story-preview-image")];
    expect(sceneImages).toHaveLength(4);
    expect(sceneImages.map((image) => [image.width, image.height])).toEqual([
      [357, 280],
      [397, 316],
      [395, 354],
      [1448, 1086],
    ]);
    sceneImages.forEach((image) => expect(image).toHaveAttribute("decoding", "async"));
    expect(sceneImages[0]).toHaveAttribute("fetchpriority", "high");
    sceneImages.slice(1).forEach((image) => expect(image).not.toHaveAttribute("fetchpriority"));

    await user.click(screen.getByRole("button", { name: "開始學習" }));
    expect(onNavigate).toHaveBeenCalledWith("student-login");
  });
});
