import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CreateStoryPage, { CREATE_STORY_HISTORY_KEY } from "./CreateStoryPage";

const topic = {
  id: "tea-story",
  name: "Afternoon tea",
  description: "A short tea conversation",
  skillFocus: "Speaking",
  images: ["/tea.png"],
  vocabulary: { 0: ["下午茶"] },
  lessonNumber: 1,
};

vi.mock("../components/TopicSelector", () => ({
  default: ({ onTopicSelect }: { onTopicSelect: (selectedTopic: typeof topic) => void }) => (
    <button
      type="button"
      data-testid="topic-open"
      onClick={() => onTopicSelect(topic)}
    >
      Open topic
    </button>
  ),
}));

vi.mock("../components/story-recorder/StoryRecorder", () => ({
  default: ({ onExit, topic: selectedTopic }: { onExit?: () => void; topic: typeof topic }) => (
    <button
      type="button"
      data-testid="story-back"
      aria-label="Back to previous page"
      onClick={onExit}
    >
      Back from {selectedTopic.name}
    </button>
  ),
}));

describe("CreateStoryPage back navigation", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("uses the in-app history entry and returns to the previous screen", () => {
    const pushState = vi.spyOn(window.history, "pushState");
    const historyBack = vi
      .spyOn(window.history, "back")
      .mockImplementation(() => {
        window.history.replaceState(listState, "", window.location.href);
        act(() => window.dispatchEvent(new PopStateEvent("popstate", { state: listState })));
      });

    render(
      <CreateStoryPage
        onAddRecord={vi.fn()}
        publishedTopics={[topic]}
      />,
    );
    const listState = window.history.state;

    fireEvent.click(screen.getByTestId("topic-open"));
    expect(screen.getByTestId("story-back")).toBeInTheDocument();
    expect(window.history.state[CREATE_STORY_HISTORY_KEY]).toMatchObject({
      topicId: topic.id,
      imageIndex: 0,
      startAtQuiz: false,
    });
    expect(pushState).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByTestId("story-back"));

    expect(historyBack).toHaveBeenCalledOnce();
    expect(screen.getByTestId("topic-open")).toBeInTheDocument();
  });

  it("restores the selected story when browser Forward replays its saved entry", () => {
    render(<CreateStoryPage onAddRecord={vi.fn()} publishedTopics={[topic]} />);
    const listState = window.history.state;

    fireEvent.click(screen.getByTestId("topic-open"));
    const storyState = window.history.state;

    act(() => window.dispatchEvent(new PopStateEvent("popstate", { state: listState })));
    expect(screen.getByTestId("topic-open")).toBeInTheDocument();

    act(() => window.dispatchEvent(new PopStateEvent("popstate", { state: storyState })));
    expect(screen.getByRole("button", { name: "Back to previous page" })).toBeInTheDocument();
  });

  it("returns an activity launched from another workspace layout to that layout", () => {
    const historyBack = vi
      .spyOn(window.history, "back")
      .mockImplementation(() => undefined);
    window.history.replaceState(
      {
        mandarinPractice: { kind: "activity-entry", topicId: topic.id },
      },
      "",
      "/",
    );

    render(
      <CreateStoryPage
        onAddRecord={vi.fn()}
        publishedTopics={[topic]}
        initialTopicId={topic.id}
      />,
    );

    fireEvent.click(screen.getByTestId("story-back"));

    expect(historyBack).toHaveBeenCalledOnce();
  });
});
