import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Topic } from "../components/TopicSelector";
import MyStoriesPage, { topicWasStarted } from "./MyStoriesPage";

vi.mock("../services/database", () => ({
  canUseDatabase: () => false,
  listAudioRecords: vi.fn(),
  listStorySubmissions: vi.fn(),
  listVocabQuizAttempts: vi.fn(),
}));

const topic = (id: string, storyId = id) =>
  ({ id, sourceStory: { id: storyId } }) as unknown as Pick<
    Topic,
    "id" | "sourceStory"
  >;

describe("topicWasStarted", () => {
  it("does not include a teacher-published story with no learner activity", () => {
    expect(topicWasStarted(topic("lesson-6"), new Set(["lesson-5"]))).toBe(false);
  });

  it("accepts recordings or submissions stored under the teacher story id", () => {
    expect(topicWasStarted(topic("wallet-medium", "wallet"), new Set(["wallet"]))).toBe(true);
  });

  it("accepts quiz activity stored under a tier-suffixed topic id", () => {
    expect(topicWasStarted(topic("wallet", "wallet"), new Set(["wallet-hard"]))).toBe(true);
  });
});

describe("MyStoriesPage student history states", () => {
  it("shows an honest empty history and lets the student return to practice", () => {
    const onBrowsePractice = vi.fn();
    render(
      <MyStoriesPage
        records={[]}
        publishedTopics={[{
          id: "park-story",
          name: "At the park",
          description: "A park scene",
          skillFocus: "Speaking",
          images: ["/park.png"],
          vocabulary: { 0: ["公園"] },
          lessonNumber: 1,
        }]}
        onBrowsePractice={onBrowsePractice}
      />,
    );

    expect(screen.getByRole("heading", { name: /My learning/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /By lesson/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Total stars")).toBeInTheDocument();
    expect(screen.getByText("Tone accuracy (avg)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /By story/ }));
    expect(screen.getByText("No stories started yet. Start one from the lesson list and it will appear here.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /By lesson/ }));
    fireEvent.click(screen.getByRole("button", { name: /Practice/ }));
    expect(onBrowsePractice).toHaveBeenCalledTimes(1);
  });

  it("counts a local audio record as started and exposes it in the story tab", () => {
    render(
      <MyStoriesPage
        records={[{
          id: "record-1",
          timestamp: "2026-08-17T00:00:00.000Z",
          duration: 4,
          transcription: "我在公園。",
          model: "ctwhisper",
          topicId: "park-story",
        }]}
        publishedTopics={[{
          id: "park-story",
          name: "At the park",
          description: "A park scene",
          skillFocus: "Speaking",
          images: ["/park.png"],
          vocabulary: { 0: ["公園"] },
        }]}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: /By story/ }));
    expect(screen.getByText("At the park")).toBeInTheDocument();
    expect(screen.getByText("In progress")).toBeInTheDocument();
  });
});
