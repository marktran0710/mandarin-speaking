import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Topic } from "@entities/topic";
import StudyPage, { selectStudyHeroTopic } from "./StudyPage";
function topic(id: string, order: number): Topic {
  return {
    id,
    name: id,
    description: "",
    skillFocus: "conversation",
    images: [],
    vocabulary: {},
    lessonNumber: 1,
    lessonSubOrder: order,
  };
}
describe("Study hero selection", () => {
  it("chooses the first active story, then the first available story", () => {
    const topics = [topic("one", 1), topic("two", 2), topic("three", 3)];
    expect(
      selectStudyHeroTopic(topics, {
        one: { status: "completed" },
        two: { status: "in-progress" },
        three: { status: "not-started" },
      }),
    ).toBe(topics[1]);
    expect(
      selectStudyHeroTopic(topics, {
        one: { status: "completed" },
        two: { status: "completed" },
        three: { status: "not-started" },
      }),
    ).toBe(topics[2]);
  });

  it("shows a completed summary when no topic is available", () => {
    const topics = [topic("one", 1)];
    render(
      <StudyPage
        topics={topics}
        statusByStoryId={{ one: { status: "completed" } }}
        onOpenTopic={() => undefined}
      />,
    );
    expect(screen.getByText(/課程完成/)).toBeInTheDocument();
    expect(screen.getByText("你已完成所有課程")).toBeInTheDocument();
  });
});
