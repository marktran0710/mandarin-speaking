import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StoryVocabQuiz from "./StoryVocabQuiz";
import * as database from "../../services/database";

// Epic 4, Task 4.3/4.8/4.9/4.10 end-to-end proof: an active research
// participant's practice round uses the server-selected word list (never
// the client's own accuracy-derived weakEntries), shows neutral "Practice"
// copy instead of "Weak words", and has manual one-word practice and Lesson
// Challenge switched off for the duration of the study.

const { getCachedResearchContext } = vi.hoisted(() => ({ getCachedResearchContext: vi.fn() }));
vi.mock("../../utils/researchContext", () => ({ getCachedResearchContext }));

const { postResearchPracticeSession, getResearchReviewSession } = vi.hoisted(() => ({
  postResearchPracticeSession: vi.fn(),
  getResearchReviewSession: vi.fn(async () => ({ wordIds: [] })),
}));
vi.mock("../../services/api/vocabulary-research", () => ({ postResearchPracticeSession, getResearchReviewSession }));

vi.mock("../../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/database")>();
  return {
    ...actual,
    canUseDatabase: vi.fn(() => true),
    getVocabQuizWeakWords: vi.fn(async () => {
      // Client-computed weak words the research selection must NOT use -
      // "二" would be picked here if the entry point fell back to the
      // ordinary client-side weakEntries flow instead of the server list.
      const result = ["二"] as database.VocabWeakWordsResult;
      Object.defineProperty(result, "priorityReview", {
        value: [{ wordId: undefined, word: "二", pLearned: 0.1, status: "NEEDS_PRACTICE", observationCount: 3, correctCount: 0, incorrectCount: 3 }],
      });
      return result;
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

describe("StoryVocabQuiz in an active research session", () => {
  it("shows a neutral Practice card instead of the accuracy-framed Weak words card", async () => {
    getCachedResearchContext.mockReturnValue({ active: true, coreCompletionPolicy: "research_coverage", practiceAvailable: true, reviewAvailable: false, probeAvailable: false });
    postResearchPracticeSession.mockResolvedValue({ wordIds: ["一"] });

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    expect(screen.getByRole("button", { name: /Practice/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Weak words/ })).not.toBeInTheDocument();
  });

  it("takes the practice round from the server's word list, not the client's own weakEntries", async () => {
    getCachedResearchContext.mockReturnValue({ active: true, coreCompletionPolicy: "research_coverage", practiceAvailable: true, reviewAvailable: false, probeAvailable: false });
    postResearchPracticeSession.mockResolvedValue({ wordIds: ["一"] });
    const user = userEvent.setup();

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(screen.getByRole("button", { name: /Practice/ }));

    // "一" (the server's pick), not "二" (what the client-side weak-word
    // mock above would have chosen).
    expect(await screen.findByRole("heading", { name: "一" })).toBeInTheDocument();
    await waitFor(() => expect(postResearchPracticeSession).toHaveBeenCalledTimes(1));
  });

  it("hides the Lesson Challenge card during an active research session even once the diagnostic is complete", async () => {
    getCachedResearchContext.mockReturnValue({ active: true, coreCompletionPolicy: "research_coverage", practiceAvailable: true, reviewAvailable: false, probeAvailable: false });
    const weakWords = [] as database.VocabWeakWordsResult;
    Object.defineProperty(weakWords, "diagnostic", { value: { unlocked: true, diagnosticComplete: true, requiredDiagnosticQuizzes: 3, completedDiagnosticQuizzes: 3 } });
    vi.mocked(database.getVocabQuizWeakWords).mockResolvedValueOnce(weakWords);

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    expect(screen.queryByRole("button", { name: /Lesson challenge/ })).not.toBeInTheDocument();
  });

  it("shows the Lesson Challenge card once the diagnostic is complete for a non-research student", async () => {
    getCachedResearchContext.mockReturnValue({ active: false, coreCompletionPolicy: "production_accuracy", practiceAvailable: false, reviewAvailable: false, probeAvailable: false });
    const weakWords = [] as database.VocabWeakWordsResult;
    Object.defineProperty(weakWords, "diagnostic", { value: { unlocked: true, diagnosticComplete: true, requiredDiagnosticQuizzes: 3, completedDiagnosticQuizzes: 3 } });
    vi.mocked(database.getVocabQuizWeakWords).mockResolvedValueOnce(weakWords);

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    expect(await screen.findByRole("button", { name: /Lesson challenge/ })).toBeInTheDocument();
  });

  it("shows the real Weak words card for a non-research student instead of Practice", async () => {
    getCachedResearchContext.mockReturnValue({ active: false, coreCompletionPolicy: "production_accuracy", practiceAvailable: false, reviewAvailable: false, probeAvailable: false });
    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="story-1" studentId="s1" />);
    await screen.findByRole("group", { name: "Quiz mode" });

    expect(await screen.findByRole("button", { name: /Weak words \(1\)/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Practice/ })).not.toBeInTheDocument();
    expect(postResearchPracticeSession).not.toHaveBeenCalled();
  });
});
