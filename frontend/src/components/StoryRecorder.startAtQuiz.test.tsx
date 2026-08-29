import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StoryRecorder from "./StoryRecorder";
import { topicWithQuizVocab } from "./StoryRecorder.test.helpers";

// A student who already earned all three stars on a story's quiz used to
// get silently redirected straight to speaking practice even after
// explicitly clicking "Start Vocabulary Quiz" — a background check for
// "already passed" forced the view away without checking whether the
// student had asked to see the quiz on purpose. Fixed by making that
// redirect back off whenever startAtQuiz is true.
const PASSING_ATTEMPTS = [
  { mode: "tier1", correctCount: 14, totalQuestions: 20 },
  { mode: "tier2", correctCount: 18, totalQuestions: 22 },
  { mode: "tier3", correctCount: 22, totalQuestions: 25 },
];

vi.mock("../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/database")>();
  return {
    ...actual,
    canUseDatabase: () => true,
    listAudioRecords: vi.fn(async () => []),
    listSpeakingProgress: vi.fn(async () => []),
    listVocabQuizAttempts: vi.fn(async () => PASSING_ATTEMPTS),
    // StoryVocabQuiz's own mode-select screen now waits on this too (its
    // "弱項複習 Weak words" card used to pop in late after the rest of the
    // screen) — leaving it unmocked meant a real, unmocked fetch, which
    // never resolves in this test environment and the screen never settles.
    getVocabQuizWeakWords: vi.fn(async () => []),
  };
});

describe("StoryRecorder — explicit startAtQuiz beats the already-passed redirect", () => {
  it("still shows the vocabulary quiz for a student who already earned all three stars", async () => {
    render(
      <StoryRecorder
        topic={topicWithQuizVocab}
        selectedImage={topicWithQuizVocab.images[0]}
        selectedImageIndex={0}
        onImageSelect={() => {}}
        onImageChange={() => {}}
        onAddRecord={() => {}}
        startAtQuiz
        studentId="student-already-passed"
        studentName="Test Student"
      />,
    );

    // findByRole retries (default up to 1s) — long enough for the mocked
    // listVocabQuizAttempts to resolve and, before the fix, force the view
    // away to practice. If that happened, this never finds the heading.
    expect(
      // The mode grid, not the headline: the headline is state-dependent
      // copy (it celebrates once all three stars are in), so asserting on
      // it would break every time that wording is tuned.
      await screen.findByRole("group", { name: "Quiz mode" }),
    ).toBeInTheDocument();
    // The real recording button's accessible name is "Record" (BiLabel key
    // "record", see translations-b.json) — confirms we're not secretly on
    // the practice screen underneath the quiz heading.
    expect(
      screen.queryByRole("button", { name: "Record" }),
    ).not.toBeInTheDocument();
  });
});
