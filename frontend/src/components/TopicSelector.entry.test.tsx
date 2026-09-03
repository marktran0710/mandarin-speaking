import { fireEvent, render, screen } from "@testing-library/react";
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

vi.mock("../services/database", () => ({
  canUseDatabase: () => false,
  createCustomStory: vi.fn(),
  listCustomStories: vi.fn(),
  listStorySubmissions: vi.fn(),
}));

vi.mock("../utils/teacherStories", () => ({
  loadPublishedTeacherTopics: () => [topic],
  loadCustomStories: () => [],
  saveCustomStories: vi.fn(),
  storyHasTierContent: () => false,
  storyToTopic: vi.fn(),
  loadSubmittedLevels: () => ({}),
}));

vi.mock("../utils/lessonGroups", () => ({
  groupTopicsByLesson: (topics: Topic[]) => [{ lessonNumber: 1, topics }],
  isLessonGroupUnlocked: () => true,
  isStoryUnlockedInLesson: () => true,
  isStoryFinished: () => false,
  lessonCompletion: (group: { topics: Topic[] }) => ({ done: 0, total: group.topics.length }),
  lessonTitle: () => ({ zh: "Lesson", en: "Lesson" }),
}));

vi.mock("./journey/JourneyPath", () => ({
  default: ({ stops }: { stops: Array<{ key: string | number; label: ReactNode; expanded?: ReactNode; onClick?: () => void; disabled?: boolean; ariaExpanded?: boolean }> }) => (
    <div>
      {stops.map((stop) => (
        <div key={stop.key}>
          <button type="button" disabled={stop.disabled} aria-expanded={stop.ariaExpanded} onClick={stop.onClick}>{stop.label}</button>
          {stop.expanded}
        </div>
      ))}
    </div>
  ),
}));

describe("TopicSelector entry action", () => {
  beforeEach(() => localStorage.clear());

  it("opens a quiz-capable story at the activity chooser", () => {
    const onTopicSelect = vi.fn();
    render(<TopicSelector onTopicSelect={onTopicSelect} />);

    fireEvent.click(screen.getByRole("button", { name: /Lesson.*Lesson/ }));
    fireEvent.click(screen.getByRole("button", { name: /Choose an activity/ }));

    expect(onTopicSelect).toHaveBeenCalledWith(topic);
  });
});
