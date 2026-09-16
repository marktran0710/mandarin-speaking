import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MasteryProgressBar } from "./LessonVocabularyProgress";
import type { LessonVocabularyProgress } from "./lesson-vocab-progress";

const round = { completed: false, answered: 0, total: 0, correct: 0, accuracy: 0 };

function makeProgress(overrides: Partial<LessonVocabularyProgress>): LessonVocabularyProgress {
  return {
    lessonId: "L1",
    totalWords: 15,
    strongWords: 0,
    remainingWords: 15,
    vocabularyReviewCompleted: false,
    knowIt: { ...round },
    sayIt: { ...round },
    useIt: { ...round },
    strengthen: { required: 15, strengthened: 0, remaining: 15, completed: false },
    lessonCompleted: false,
    challenge: { available: false, attempts: 0 },
    initialStrongCount: 0,
    strengthenedCount: 0,
    improvements: [],
    focusWords: [],
    ...overrides,
  } as LessonVocabularyProgress;
}

describe("MasteryProgressBar — measured vs not-measured states", () => {
  it("shows a 'take the star rounds' cue instead of a stalled count before any diagnostic", () => {
    render(<MasteryProgressBar progress={makeProgress({ vocabularyReviewCompleted: false })} />);
    expect(screen.getByText(/Take the star rounds to start measuring mastery/)).toBeInTheDocument();
    // The stalled "N to strengthen" line must NOT appear before measurement.
    expect(screen.queryByText(/to strengthen/)).not.toBeInTheDocument();
  });

  it("shows remaining count plus a hint on how mastery grows once measured", () => {
    render(
      <MasteryProgressBar
        progress={makeProgress({ vocabularyReviewCompleted: true, strongWords: 5, remainingWords: 10 })}
      />,
    );
    expect(screen.getByText(/10 words to strengthen/)).toBeInTheDocument();
    expect(screen.getByText(/Passing the star rounds raises mastery/)).toBeInTheDocument();
    expect(screen.queryByText(/Take the star rounds to start measuring/)).not.toBeInTheDocument();
  });

  it("shows the all-done message when every word is strong", () => {
    render(
      <MasteryProgressBar
        progress={makeProgress({ vocabularyReviewCompleted: true, strongWords: 15, remainingWords: 0 })}
      />,
    );
    expect(screen.getByText(/You know every word in this lesson/)).toBeInTheDocument();
    expect(screen.queryByText(/to strengthen/)).not.toBeInTheDocument();
  });
});
