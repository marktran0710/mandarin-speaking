import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StoryVocabQuiz from "./StoryVocabQuiz";
import * as database from "../../services/database";

// Epic 5, Task 5.7/5.8/5.9 end-to-end proof: an active research
// participant's "Review today" round uses the server's due-word list
// (never production's SM-2 due-words queue), shows neutral copy with no
// "SM-2"/"adaptive"/"yoked" label, and only appears when the server
// actually has something due.

const { getCachedResearchContext } = vi.hoisted(() => ({ getCachedResearchContext: vi.fn() }));
vi.mock("../../utils/researchContext", () => ({ getCachedResearchContext }));

const { postResearchPracticeSession, getResearchReviewSession } = vi.hoisted(() => ({
  postResearchPracticeSession: vi.fn(async () => ({ wordIds: [] })),
  getResearchReviewSession: vi.fn(),
}));
vi.mock("../../services/api/vocabulary-research", () => ({ postResearchPracticeSession, getResearchReviewSession }));

vi.mock("../../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/database")>();
  return {
    ...actual,
    canUseDatabase: vi.fn(() => true),
    getVocabQuizWeakWords: vi.fn(async () => [] as database.VocabWeakWordsResult),
    getVocabQuizReviewQueue: vi.fn(async () => {
      // Production's own due-words queue the research flow must NOT use -
      // "三" would be picked here if the review entry point fell back to
      // the client-side production queue instead of the server list.
      const queue = [{ word: "三", wordId: undefined, reviewReason: "due" as const }];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return { queue, words: [], mastery: [] } as any;
    }),
    listVocabQuizAttempts: vi.fn(async () => []),
    recordVocabQuizResponse: vi.fn(async () => undefined),
  };
});

const entries = [
  { word: "一", translation: "one" },
  { word: "二", translation: "two" },
  { word: "三", translation: "three" },
];

afterEach(() => {
  vi.clearAllMocks();
});

describe("StoryVocabQuiz review-today in an active research session", () => {
  it("shows a neutral Review today card sized from the server's due list", async () => {
    getCachedResearchContext.mockReturnValue({ active: true, coreCompletionPolicy: "research_coverage", practiceAvailable: true, reviewAvailable: true, probeAvailable: false });
    getResearchReviewSession.mockResolvedValue({ wordIds: ["一"] });

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    const card = await screen.findByRole("button", { name: /Review today \(1\)/ });
    expect(card).toBeInTheDocument();
    expect(card).not.toHaveTextContent("SM-2");
    expect(card).not.toHaveTextContent("adaptive");
    expect(card).not.toHaveTextContent("yoked");
  });

  it("takes the review round from the server's due list, not production's SM-2 queue", async () => {
    getCachedResearchContext.mockReturnValue({ active: true, coreCompletionPolicy: "research_coverage", practiceAvailable: true, reviewAvailable: true, probeAvailable: false });
    getResearchReviewSession.mockResolvedValue({ wordIds: ["一"] });
    const user = userEvent.setup();

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    const card = await screen.findByRole("button", { name: /Review today \(1\)/ });
    await user.click(card);

    // "一" (the server's research due word), not "三" (what production's
    // getVocabQuizReviewQueue mock above would have chosen).
    expect(await screen.findByRole("heading", { name: "一" })).toBeInTheDocument();
    expect(database.getVocabQuizReviewQueue).not.toHaveBeenCalled();
  });

  it("hides the review card entirely when the server has nothing due", async () => {
    getCachedResearchContext.mockReturnValue({ active: true, coreCompletionPolicy: "research_coverage", practiceAvailable: true, reviewAvailable: true, probeAvailable: false });
    getResearchReviewSession.mockResolvedValue({ wordIds: [] });

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });
    await waitFor(() => expect(getResearchReviewSession).toHaveBeenCalled());

    expect(screen.queryByRole("button", { name: /Review today/ })).not.toBeInTheDocument();
  });

  it("uses production's own due-words queue for a non-research student", async () => {
    getCachedResearchContext.mockReturnValue({ active: false, coreCompletionPolicy: "production_accuracy", practiceAvailable: false, reviewAvailable: false, probeAvailable: false });

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });
    await waitFor(() => expect(database.getVocabQuizReviewQueue).toHaveBeenCalled());

    expect(await screen.findByRole("button", { name: /Due for review \(1\)/ })).toBeInTheDocument();
    expect(getResearchReviewSession).not.toHaveBeenCalled();
  });
});
