import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TopicSelector from "./TopicSelector";
import type { Topic } from "./topic-selector/types";

const listStorySubmissions = vi.fn();
const getVocabQuizReviewQueue = vi.fn().mockResolvedValue({ queue: [] });

vi.mock("../services/database", () => ({
  canUseDatabase: () => true,
  createCustomStory: vi.fn(),
  getVocabQuizReviewQueue: (...args: unknown[]) => getVocabQuizReviewQueue(...args),
  listCustomStories: vi.fn(),
  listStorySubmissions: (...args: unknown[]) => listStorySubmissions(...args),
}));

vi.mock("../utils/teacherStories", () => ({
  loadCustomStories: () => [],
  loadPublishedTeacherTopics: () => [],
  saveCustomStories: vi.fn(),
  storyToTopic: vi.fn(),
}));

function topic(id: string, order: number): Topic {
  return {
    id,
    name: `Story ${order}`,
    description: "",
    skillFocus: "Speaking",
    images: [`/${id}.png`],
    vocabulary: { 0: ["你好"] },
    lessonNumber: 1,
    lessonSubOrder: order,
  };
}

describe("TopicSelector submission hydration", () => {
  it("refreshes lesson progress when a deferred server submission is merged", async () => {
    localStorage.setItem(
      "studentSession",
      JSON.stringify({ role: "student", name: "Ada", id: "student-1" }),
    );
    let resolveSubmissions!: (value: unknown[]) => void;
    listStorySubmissions.mockReturnValue(
      new Promise((resolve) => {
        resolveSubmissions = resolve;
      }),
    );

    render(
      <TopicSelector
        publishedTopics={[topic("first", 1), topic("second", 2)]}
        onTopicSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /0\/2.*stories/ })).toBeInTheDocument();

    resolveSubmissions([
      {
        storyId: "teacher-first",
        studentId: "student-1",
        studentName: "Ada",
        scenes: [{ baseStoryId: "first" }],
      },
    ]);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /1\/2.*stories/ })).toBeInTheDocument(),
    );
  });
});
