import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JourneyPath from "./JourneyPath";

describe("JourneyPath", () => {
  it("renders one stop per entry, in order, as a list", () => {
    render(
      <JourneyPath
        stops={[
          { key: 0, status: "done", label: "Scene 1" },
          { key: 1, status: "current", label: "Scene 2" },
          { key: 2, status: "upcoming", label: "Scene 3" },
        ]}
      />,
    );

    const list = screen.getByRole("list", { name: "Practice journey" });
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Scene 1");
    expect(items[1]).toHaveTextContent("Scene 2");
    expect(items[2]).toHaveTextContent("Scene 3");
    expect(list).toContainElement(items[0]);
  });

  it("applies a status-specific class to each stop so done/current/upcoming look distinct", () => {
    render(
      <JourneyPath
        stops={[
          { key: 0, status: "done", label: "Scene 1" },
          { key: 1, status: "current", label: "Scene 2" },
          { key: 2, status: "upcoming", label: "Scene 3" },
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: /Scene 1/ }).className).toContain(
      "journey-stop-done",
    );
    expect(screen.getByRole("button", { name: /Scene 2/ }).className).toContain(
      "journey-stop-current",
    );
    expect(screen.getByRole("button", { name: /Scene 3/ }).className).toContain(
      "journey-stop-upcoming",
    );
  });

  it("shows a star badge only on done stops", () => {
    render(
      <JourneyPath
        stops={[
          { key: 0, status: "done", label: "Scene 1" },
          { key: 1, status: "current", label: "Scene 2" },
        ]}
      />,
    );

    const stops = screen.getAllByRole("button");
    expect(stops[0].textContent).toContain("★");
    expect(stops[1].textContent).not.toContain("★");
  });

  it("does not render a connector before the first stop, but does before later ones", () => {
    const { container } = render(
      <JourneyPath
        stops={[
          { key: 0, status: "done", label: "Scene 1" },
          { key: 1, status: "current", label: "Scene 2" },
          { key: 2, status: "upcoming", label: "Scene 3" },
        ]}
      />,
    );

    expect(container.querySelectorAll(".journey-connector")).toHaveLength(2);
  });

  it("calls onClick with the right stop and respects disabled", async () => {
    const user = userEvent.setup();
    const onClickScene2 = vi.fn();
    render(
      <JourneyPath
        stops={[
          { key: 0, status: "done", label: "Scene 1", disabled: true, onClick: vi.fn() },
          { key: 1, status: "current", label: "Scene 2", onClick: onClickScene2 },
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: /Scene 1/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Scene 2/ }));
    expect(onClickScene2).toHaveBeenCalledTimes(1);
  });

  it("shows a badge when provided (e.g. attempt count) alongside the label", () => {
    render(
      <JourneyPath
        stops={[{ key: 0, status: "upcoming", label: "Scene 1", badge: "2×" }]}
      />,
    );

    expect(screen.getByRole("button", { name: /Scene 1/ })).toHaveTextContent("2×");
  });
});
