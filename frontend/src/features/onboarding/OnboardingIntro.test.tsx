import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const scope = vi.hoisted(() => ({ key: "student-1" }));
vi.mock("../../utils/studentSession", () => ({ getStudentScopeKey: () => scope.key }));

import OnboardingIntro from "./OnboardingIntro";
import { hasSeenOnboarding, markOnboardingSeen } from "./onboardingFlag";

const heading = () => screen.getByRole("heading", { level: 1 });

describe("OnboardingIntro", () => {
  beforeEach(() => {
    localStorage.clear();
    scope.key = "student-1";
  });

  it("opens on the welcome step with no way back", () => {
    render(<OnboardingIntro onStartPlacement={vi.fn()} />);
    expect(heading()).toHaveTextContent("歡迎來到慢慢中文");
    expect(screen.getByText("1 / 4")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "上一步" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "開始入門測驗" })).not.toBeInTheDocument();
  });

  it("walks through the four steps and back again", async () => {
    const user = userEvent.setup();
    render(<OnboardingIntro onStartPlacement={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "下一步" }));
    expect(heading()).toHaveTextContent("每一課怎麼學");
    await user.click(screen.getByRole("button", { name: "下一步" }));
    expect(heading()).toHaveTextContent("星星和發音分數");
    await user.click(screen.getByRole("button", { name: "上一步" }));
    expect(heading()).toHaveTextContent("每一課怎麼學");
    await user.click(screen.getByRole("button", { name: "下一步" }));
    await user.click(screen.getByRole("button", { name: "下一步" }));

    expect(heading()).toHaveTextContent("先做入門測驗");
    expect(screen.getByText("4 / 4")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下一步" })).not.toBeInTheDocument();
  });

  it("starts the placement test from the last step and remembers the intro was seen", async () => {
    const user = userEvent.setup();
    const onStartPlacement = vi.fn();
    render(<OnboardingIntro onStartPlacement={onStartPlacement} />);
    for (let step = 0; step < 3; step += 1) await user.click(screen.getByRole("button", { name: "下一步" }));

    expect(hasSeenOnboarding()).toBe(false);
    await user.click(screen.getByRole("button", { name: "開始入門測驗" }));

    expect(onStartPlacement).toHaveBeenCalledOnce();
    expect(hasSeenOnboarding()).toBe(true);
  });
});

describe("onboarding flag", () => {
  beforeEach(() => {
    localStorage.clear();
    scope.key = "student-1";
  });

  it("is remembered per student, not per browser", () => {
    expect(hasSeenOnboarding()).toBe(false);
    markOnboardingSeen();
    expect(hasSeenOnboarding()).toBe(true);
    scope.key = "student-2";
    expect(hasSeenOnboarding()).toBe(false);
  });

  it("treats unavailable storage as not seen instead of throwing", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(hasSeenOnboarding()).toBe(false);
    vi.restoreAllMocks();
  });
});
