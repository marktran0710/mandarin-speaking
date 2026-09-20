import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StudentSidebar from "./StudentSidebar";

const views = [
  { id: "practice" as const, icon: "image" as const, label: { zh: "課程", en: "Practice" } },
  { id: "progress" as const, icon: "chart" as const, label: { zh: "我的學習", en: "Progress" } },
];

function setMobileViewport(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation(() => ({
      matches,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  });
}

describe("StudentSidebar mobile drawer", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps the closed drawer inert, traps focus while open, and restores the toggle focus", async () => {
    setMobileViewport(true);
    const user = userEvent.setup();
    render(<StudentSidebar views={views} activeView="practice" onChange={vi.fn()} studentName="Ada" onLogout={vi.fn()} totalStars={0} maxStars={0} />);

    const drawer = screen.getByRole("complementary", { hidden: true });
    const toggle = screen.getByRole("button", { name: "Open menu" });
    expect(drawer).toHaveAttribute("aria-hidden", "true");
    expect(drawer).toHaveAttribute("inert");

    await user.click(toggle);
    const activeItem = screen.getByRole("button", { name: /課程.*Practice/ });
    expect(activeItem).toHaveFocus();

    screen.getByRole("button", { name: /Log out/ }).focus();
    await user.tab();
    expect(activeItem).toHaveFocus();

    fireEvent.keyDown(activeItem, { key: "Escape" });
    expect(toggle).toHaveFocus();
    expect(drawer).toHaveAttribute("aria-hidden", "true");
  });

  it("does not mislabel a standalone tool as Lessons", () => {
    setMobileViewport(false);
    render(
      <StudentSidebar
        views={views}
        activeView={null}
        onChange={vi.fn()}
        studentName="Ada"
        onLogout={vi.fn()}
        totalStars={0}
        maxStars={0}
      />,
    );

    expect(screen.getByRole("button", { name: /課程Practice/ })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: /我的學習Progress/ })).not.toHaveAttribute("aria-current");
  });
});

describe("StudentSidebar placement test entry", () => {
  // The mobile-drawer suite above overrides window.matchMedia and never
  // restores it (vi.restoreAllMocks() doesn't undo Object.defineProperty) —
  // without resetting to desktop here, the rail renders aria-hidden and
  // every getByRole lookup below fails to find it.
  beforeEach(() => setMobileViewport(false));

  it("is absent without a handler, and calls it when present", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <StudentSidebar views={views} activeView="practice" onChange={vi.fn()} studentName="Ada" onLogout={vi.fn()} totalStars={0} maxStars={0} />,
    );
    expect(screen.queryByText("Placement test")).not.toBeInTheDocument();

    const onOpenPlacementTest = vi.fn();
    rerender(
      <StudentSidebar
        views={views}
        activeView="practice"
        onChange={vi.fn()}
        studentName="Ada"
        onLogout={vi.fn()}
        totalStars={0}
        maxStars={0}
        onOpenPlacementTest={onOpenPlacementTest}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Placement test/ }));
    expect(onOpenPlacementTest).toHaveBeenCalledTimes(1);
  });

  it("highlights the placement test item instead of whichever view id it happens to share, when active", () => {
    render(
      <StudentSidebar
        views={views}
        activeView="practice"
        onChange={vi.fn()}
        studentName="Ada"
        onLogout={vi.fn()}
        totalStars={0}
        maxStars={0}
        onOpenPlacementTest={vi.fn()}
        placementTestActive
      />,
    );
    expect(screen.getByRole("button", { name: /Placement test/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: /課程.*Practice/ })).not.toHaveAttribute("aria-current");
  });
});
