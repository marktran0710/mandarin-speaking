import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StudentWorkspaceShell from "./StudentWorkspaceShell";

// Epic 0 baseline regression (BKT x SM-2 research-mode plan): locks in the
// CURRENT totalStars/maxStars computation the sidebar rail derives from
// storyTopics + loadLocalStars, before any research-mode work touches
// progression. See MyStoriesPage.totalStars.test.tsx for the sibling
// "Total stars" card computation, which reads server stars too and is NOT
// identical to this one despite a comment claiming they can never disagree -
// flagged as a real discrepancy, not fixed here (out of Epic 0's scope).

vi.mock("../../pages/CreateStoryPage", () => ({ default: () => <section>practice view</section> }));
vi.mock("../../pages/MyStoriesPage", () => ({ default: () => <section>progress view</section> }));

vi.mock("./StudentModeFrame", () => ({
  STUDENT_WORKSPACE_VIEWS: [{ id: "practice", label: { zh: "課程", en: "Practice" } }],
  default: ({ children, totalStars, maxStars }: { children: React.ReactNode; totalStars: number; maxStars: number }) => (
    <main>
      <span data-testid="total-stars">{totalStars}</span>
      <span data-testid="max-stars">{maxStars}</span>
      {children}
    </main>
  ),
}));

const localStarsByTopic: Record<string, number> = {};
vi.mock("../../utils/quizTiers", () => ({
  loadLocalStars: vi.fn((topicId: string) => localStarsByTopic[topicId] ?? 0),
}));

const quizTopicIds = new Set<string>();
vi.mock("../../utils/topicQuiz", () => ({
  topicHasQuiz: vi.fn((topic: { id: string }) => quizTopicIds.has(topic.id)),
}));

vi.mock("../../utils/studentSession", () => ({ getStudentName: vi.fn(() => "Test Student") }));

const baseProps = {
  view: "practice" as const,
  onViewChange: vi.fn(),
  onAddRecord: vi.fn(),
  initialTopicId: undefined,
  initialImageIndex: undefined,
  initialStartAtQuiz: false,
  initialTargetKey: undefined,
  helpRequests: [],
  onRaiseHand: vi.fn(),
  audioRecords: [],
  onSessionActiveChange: vi.fn(),
  onLogout: vi.fn(),
  isInPracticeSession: false,
};

describe("StudentWorkspaceShell total stars (sidebar rail)", () => {
  afterEach(() => {
    quizTopicIds.clear();
    for (const key of Object.keys(localStarsByTopic)) delete localStarsByTopic[key];
  });

  it("sums local stars only across quiz-eligible topics, 3 stars per topic max possible", () => {
    quizTopicIds.add("story-a");
    quizTopicIds.add("story-b");
    localStarsByTopic["story-a"] = 2;
    localStarsByTopic["story-b"] = 3;

    render(
      <StudentWorkspaceShell
        {...baseProps}
        storyTopics={[
          { id: "story-a" } as never,
          { id: "story-b" } as never,
          { id: "story-c-no-quiz" } as never,
        ]}
      />,
    );

    expect(screen.getByTestId("total-stars")).toHaveTextContent("5");
    // maxStars only counts the two quiz-eligible topics (3 each), not the third.
    expect(screen.getByTestId("max-stars")).toHaveTextContent("6");
  });

  it("ignores server-known stars entirely - only reads local storage", () => {
    // This is the current, real behavior: unlike MyStoriesPage's "Total
    // stars" card (which takes max(local, server)), the sidebar rail here
    // never sees server star data at all. A student who earned stars on
    // another device but hasn't triggered a local write would see 0 here.
    quizTopicIds.add("story-a");
    localStarsByTopic["story-a"] = 0;

    render(<StudentWorkspaceShell {...baseProps} storyTopics={[{ id: "story-a" } as never]} />);

    expect(screen.getByTestId("total-stars")).toHaveTextContent("0");
    expect(screen.getByTestId("max-stars")).toHaveTextContent("3");
  });

  it("is 0/0 with no quiz-eligible topics", () => {
    render(<StudentWorkspaceShell {...baseProps} storyTopics={[{ id: "no-quiz" } as never]} />);

    expect(screen.getByTestId("total-stars")).toHaveTextContent("0");
    expect(screen.getByTestId("max-stars")).toHaveTextContent("0");
  });
});
