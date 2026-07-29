import { describe, expect, it } from "vitest";
import type { Topic } from "../components/TopicSelector";
import { topicWasStarted } from "./MyStoriesPage";

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
