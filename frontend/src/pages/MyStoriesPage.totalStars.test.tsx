import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MyStoriesPage from "./MyStoriesPage";
import type { Topic } from "../components/content/TopicSelector";
import { recordLocalStars } from "../utils/quizTiers";

// Epic 0 baseline regression (BKT x SM-2 research-mode plan): locks in the
// CURRENT "Total stars" card and lesson-completion count on My Learning,
// which combine server quiz-attempt stars with local-storage stars via
// Math.max(local, server) per story - a different computation from
// StudentWorkspaceShell's sidebar rail (local-only, see
// StudentWorkspaceShell.totalStars.test.tsx), despite a source comment
// claiming they can never disagree. Not fixed here - out of Epic 0's scope,
// flagged to the user separately.

const listStorySubmissions = vi.fn();
const listVocabQuizAttempts = vi.fn();
const listAudioRecords = vi.fn();

vi.mock("../services/database", () => ({
  canUseDatabase: () => true,
  listAudioRecords: (...args: unknown[]) => listAudioRecords(...args),
  listStorySubmissions: (...args: unknown[]) => listStorySubmissions(...args),
  listVocabQuizAttempts: (...args: unknown[]) => listVocabQuizAttempts(...args),
}));

vi.mock("../utils/studentSession", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../utils/studentSession")>();
  return {
    ...actual,
    getStudentId: () => undefined, // forces the name-scoped 3-call path, not getStudentOverview
    getStudentName: () => "Test Student",
  };
});

function topic(id: string, lessonNumber: number, hasQuiz = true): Topic {
  return {
    id,
    name: id,
    description: "",
    skillFocus: "Speaking",
    images: ["/x.png"],
    vocabulary: hasQuiz ? { 0: ["市場"] } : {},
    vocabularyTranslation: hasQuiz ? { 0: ["market"] } : undefined,
    vocabAssessment: hasQuiz ? [{
      questionId: `${id}-easy`, wordId: `${id}-word`, targetWord: "撣", pinyin: "shìchǎng",
      pos: "N", simpleEnglishMeaning: "market", level: "easy", difficultyWeight: 1,
      questionType: "basic_meaning_mcq", answerFormat: "single_choice", prompt: "What does this mean?",
      options: ["market", "book", "door", "room"], correctAnswer: "market", acceptedAnswers: ["market"], explanation: "market",
    }] : undefined,
    lessonNumber,
  } as unknown as Topic;
}

function quizAttempt(storyId: string, mode: string, correctCount: number, totalQuestions: number) {
  return { storyId, mode, correctCount, totalQuestions };
}

describe("MyStoriesPage total stars + lesson completion (server + local stars combined)", () => {
  it("sums max(local, server) stars per topic and counts a lesson done only when every story finishes", async () => {
    // Lesson 1: story-a earns all 3 stars server-side and is submitted -> finished.
    // Lesson 2: story-b earns all 3 stars and is submitted -> finished; story-c earns 0 -> not finished.
    // So lesson 1 is complete (1/1), lesson 2 is not (1/2) -> lessonsDone = 1 of 2.
    listStorySubmissions.mockResolvedValue([
      { id: "sub-a", storyId: "story-a", studentName: "Test Student", submittedAt: "2026-01-01T00:00:00Z", reviewStatus: "pending" },
      { id: "sub-b", storyId: "story-b", studentName: "Test Student", submittedAt: "2026-01-02T00:00:00Z", reviewStatus: "pending" },
    ]);
    listVocabQuizAttempts.mockResolvedValue([
      quizAttempt("story-a", "tier1", 14, 20),
      quizAttempt("story-a", "tier2", 19, 22),
      quizAttempt("story-a", "tier3", 22, 25),
      quizAttempt("story-b", "tier1", 14, 20),
      quizAttempt("story-b", "tier2", 19, 22),
      quizAttempt("story-b", "tier3", 22, 25),
    ]);
    listAudioRecords.mockResolvedValue([]);

    render(
      <MyStoriesPage
        records={[]}
        publishedTopics={[
          topic("story-a", 1),
          topic("story-b", 2),
          topic("story-c", 2),
        ]}
      />,
    );

    await waitFor(() => expect(listStorySubmissions).toHaveBeenCalled());

    // 3 quiz-eligible topics x up to 3 stars each: a=3, b=3, c=0 -> 6 / 9.
    await waitFor(() => {
      const card = screen.getByText("Total stars").closest("div");
      expect(card).toHaveTextContent("6");
      expect(card).toHaveTextContent("9");
    });

    // Lessons complete: 1 of 2 (lesson 1 finished, lesson 2 has an unfinished story).
    await waitFor(() => {
      const card = screen.getByText("Lessons complete").closest("div");
      expect(card).toHaveTextContent("1");
      expect(card).toHaveTextContent("2");
    });
  });

  it("takes the higher of a story's local and server star count, not just server", async () => {
    listStorySubmissions.mockResolvedValue([]);
    listVocabQuizAttempts.mockResolvedValue([
      // Server only knows about 1 star (tier1 pass only).
      quizAttempt("story-a", "tier1", 14, 20),
    ]);
    listAudioRecords.mockResolvedValue([]);
    recordLocalStars("story-a", 3);

    render(<MyStoriesPage records={[]} publishedTopics={[topic("story-a", 1)]} />);

    await waitFor(() => expect(listStorySubmissions).toHaveBeenCalled());
    await waitFor(() => {
      const card = screen.getByText("Total stars").closest("div");
      // Server alone would say 1; local storage's 3 must win via Math.max.
      expect(card).toHaveTextContent("3");
    });
  });
});
