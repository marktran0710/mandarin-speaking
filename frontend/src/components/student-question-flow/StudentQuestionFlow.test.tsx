import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StudentQuestionFlow } from "./StudentQuestionFlow";

describe("StudentQuestionFlow", () => {
  it("keeps the question frame and empty action row stable before an answer", () => {
    render(
      <StudentQuestionFlow
        ariaLabel="Placement test question"
        topbar={<p>Question 1 of 4</p>}
        prompt={<h1>Choose an answer</h1>}
        answers={<div role="group" aria-label="Answer choices"><button type="button">A</button></div>}
      />,
    );

    const frame = screen.getByRole("region", { name: "Placement test question" });
    expect(frame).toHaveClass("student-question-flow", "vocab-quiz-question-screen");
    expect(frame.querySelector(".vocab-quiz-topbar")).toBeTruthy();
    expect(frame.querySelector(".vocab-quiz-question-panel")).toBeTruthy();
    expect(frame.querySelector(".vocab-quiz-answer-panel")).toBeTruthy();
    expect(frame.querySelector(".vocab-quiz-actions")).toBeTruthy();
    expect(screen.getByRole("group", { name: "Answer choices" })).toBeInTheDocument();
  });
});
