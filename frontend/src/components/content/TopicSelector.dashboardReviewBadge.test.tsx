import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import TopicSelector from "./TopicSelector";
import type { Topic } from "./topic-selector/types";

const topic: Topic = {
  id: "quiz-entry-story",
  name: "A story with a vocabulary quiz",
  description: "",
  skillFocus: "Speaking",
  images: ["/scene.png"],
  vocabulary: { 0: ["好"] },
  vocabularyTranslation: { 0: ["good"] },
  suggestedAnswers: { 0: "好。" },
};

const getVocabQuizReviewQueue = vi.fn();

vi.mock("../../services/database", () => ({
  canUseDatabase: () => true,
  createCustomStory: vi.fn(),
  // Resolves with the same published story so the component's existing
  // "refresh from backend" effect (unrelated to this feature) reconstructs
  // the same topic list instead of wiping it to empty.
  listCustomStories: vi.fn().mockResolvedValue([{ id: "quiz-entry-story", published: true }]),
  listStorySubmissions: vi.fn().mockResolvedValue([]),
  getVocabQuizReviewQueue: (...args: unknown[]) => getVocabQuizReviewQueue(...args),
}));

vi.mock("../../utils/teacherStories", () => ({
  loadPublishedTeacherTopics: () => [topic],
  loadCustomStories: () => [],
  saveCustomStories: vi.fn(),
  storyHasTierContent: () => false,
  storyToTopic: () => topic,
  loadSubmittedLevels: () => ({}),
}));

vi.mock("../../utils/lessonGroups", () => ({
  groupTopicsByLesson: (topics: Topic[]) => [{ lessonNumber: 1, topics }],
  isLessonGroupUnlocked: () => true,
  isStoryUnlockedInLesson: () => true,
  isStoryFinished: () => false,
  lessonCompletion: (group: { topics: Topic[] }) => ({ done: 0, total: group.topics.length }),
  lessonTitle: () => ({ zh: "Lesson", en: "Lesson" }),
}));

vi.mock("./journey/JourneyPath", () => ({
  default: ({ stops }: { stops: Array<{ key: string | number; label: ReactNode; expanded?: ReactNode }> }) => (
    <div>{stops.map((stop) => <div key={stop.key}>{stop.label}{stop.expanded}</div>)}</div>
  ),
}));

function signInAsStudent(id: string) {
  localStorage.setItem(
    "studentSession",
    JSON.stringify({ role: "student", name: "Ada", id, signedInAt: "2026-01-01T00:00:00.000Z" }),
  );
}

describe("TopicSelector dashboard — pending review nudge", () => {
  beforeEach(() => {
    localStorage.clear();
    getVocabQuizReviewQueue.mockReset();
  });

  it("shows a quiet badge on the continue card when the current lesson has weak/due words waiting", async () => {
    signInAsStudent("student-1");
    getVocabQuizReviewQueue.mockResolvedValue({
      queue: [
        { wordId: "w1", word: "附近", reviewReason: "weak" },
        { wordId: "w2", word: "方便", reviewReason: "due" },
      ],
    });

    render(<TopicSelector onTopicSelect={vi.fn()} />);

    expect(await screen.findByRole("status", { name: "2 words to review" })).toBeInTheDocument();
    expect(getVocabQuizReviewQueue).toHaveBeenCalledWith(topic.id, "student-1", { includeAllWeak: true });
    // It rides along the existing continue card — no new click target, no
    // separate forced screen.
    expect(screen.getByRole("button", { name: /Continue story/ })).toBeInTheDocument();
  });

  it("shows no badge when nothing is weak or due", async () => {
    signInAsStudent("student-1");
    getVocabQuizReviewQueue.mockResolvedValue({ queue: [] });

    render(<TopicSelector onTopicSelect={vi.fn()} />);

    await waitFor(() => expect(getVocabQuizReviewQueue).toHaveBeenCalled());
    expect(screen.queryByRole("status", { name: /words to review/ })).not.toBeInTheDocument();
  });

  it("shows no badge and skips the fetch when signed out", async () => {
    render(<TopicSelector onTopicSelect={vi.fn()} />);

    await Promise.resolve();
    expect(getVocabQuizReviewQueue).not.toHaveBeenCalled();
    expect(screen.queryByRole("status", { name: /words to review/ })).not.toBeInTheDocument();
  });

  it("fails silently (no badge, no crash) when the review-queue request errors", async () => {
    signInAsStudent("student-1");
    getVocabQuizReviewQueue.mockRejectedValue(new Error("offline"));

    render(<TopicSelector onTopicSelect={vi.fn()} />);

    await waitFor(() => expect(getVocabQuizReviewQueue).toHaveBeenCalled());
    expect(screen.queryByRole("status", { name: /words to review/ })).not.toBeInTheDocument();
  });
});
