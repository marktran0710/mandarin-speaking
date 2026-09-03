import { render, screen } from "@testing-library/react";
import StorySessionSidebar from "./StorySessionSidebar";

describe("StorySessionSidebar scene sequence", () => {
  it("locks scene 5-2 until scene 5-1 has a result", () => {
    render(
      <StorySessionSidebar
        topicName="Story 5"
        summaryStatus="locked"
        journeyStops={[
          { key: "5-1", status: "current", label: "Scene 5-1" },
          { key: "5-2", status: "upcoming", label: "Scene 5-2" },
          { key: "5-3", status: "upcoming", label: "Scene 5-3" },
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: /Scene 5-1/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Scene 5-2/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Scene 5-3/ })).toBeDisabled();
  });

  it("opens only the next scene after the previous scene is done", () => {
    render(
      <StorySessionSidebar
        topicName="Story 5"
        summaryStatus="locked"
        journeyStops={[
          { key: "5-1", status: "done", label: "Scene 5-1" },
          { key: "5-2", status: "current", label: "Scene 5-2" },
          { key: "5-3", status: "upcoming", label: "Scene 5-3" },
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: /Scene 5-1/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Scene 5-2/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Scene 5-3/ })).toBeDisabled();
  });
});
