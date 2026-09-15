import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuizQuestion } from "./QuizQuestion";
import type { VocabQuizQuestion } from "./model";

// A minimal multiple-choice (translation) question. `tea` is the correct
// translation, which is also the answer we pass as already-selected below.
const question = {
  kind: "translation",
  word: "茶",
  translation: "tea",
  options: ["tea", "water", "rice", "book"],
  isAiGenerated: false,
} as unknown as VocabQuizQuestion;

function renderAnswered(next: () => void, overrides: Partial<Parameters<typeof QuizQuestion>[0]> = {}) {
  return render(
    <QuizQuestion
      question={question}
      mode="tier1"
      selected="tea"
      results={[]}
      index={0}
      questionLimit={5}
      requestedQuestionCount={5}
      isRetryRound={false}
      isLast={false}
      timeLeftMs={0}
      timeLimitMs={null}
      showFinishButton={false}
      choose={vi.fn()}
      next={next}
      finish={vi.fn()}
      speakWord={vi.fn()}
      {...overrides}
    />,
  );
}

describe("QuizQuestion Enter to continue", () => {
  it("does not submit a free-text answer while a Chinese IME is composing", () => {
    const choose = vi.fn();
    const freeTextQuestion = {
      kind: "assessment",
      word: "target",
      prompt: "Complete the sentence.",
      options: [],
      correctAnswer: "answer",
      acceptedAnswers: ["answer"],
      explanation: "",
      isAiGenerated: false,
      assessment: {
        questionId: "target_HARD",
        wordId: "target",
        targetWord: "target",
        pinyin: "target",
        pos: "N",
        simpleEnglishMeaning: "target",
        level: "hard",
        difficultyWeight: 3,
        questionType: "contextual_productive_recall",
        answerFormat: "free_text",
        prompt: "Complete the sentence.",
        options: [],
        correctAnswer: "answer",
        acceptedAnswers: ["answer"],
        explanation: "",
      },
    } as unknown as VocabQuizQuestion;
    render(
      <QuizQuestion
        question={freeTextQuestion}
        mode="tier3"
        selected={null}
        results={[]}
        index={0}
        questionLimit={1}
        requestedQuestionCount={1}
        isRetryRound={false}
        isLast
        timeLeftMs={0}
        timeLimitMs={150000}
        showFinishButton={false}
        choose={choose}
        next={vi.fn()}
        finish={vi.fn()}
        speakWord={vi.fn()}
      />,
    );

    const input = screen.getByRole("textbox", { name: "Your answer" });
    fireEvent.change(input, { target: { value: "answer" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", isComposing: false, keyCode: 229 });

    expect(choose).not.toHaveBeenCalled();
  });

  it("focuses the continue button once an answer is submitted so Enter advances", async () => {
    const next = vi.fn();
    renderAnswered(next);

    const nextButton = screen.getByRole("button", { name: /Next question/ });
    expect(nextButton).toHaveFocus();

    await userEvent.keyboard("{Enter}");
    expect(next).toHaveBeenCalledTimes(1);
  });

  it("advances with Enter on the last question too (See results)", async () => {
    const next = vi.fn();
    renderAnswered(next, { isLast: true });

    const resultsButton = screen.getByRole("button", { name: /See results/ });
    expect(resultsButton).toHaveFocus();

    await userEvent.keyboard("{Enter}");
    expect(next).toHaveBeenCalledTimes(1);
  });

  it("does not submit Enter while a Chinese IME composition is active", () => {
    const choose = vi.fn();
    const assessmentQuestion = {
      kind: "assessment",
      word: "喜歡",
      prompt: "Type the pinyin",
      correctAnswer: "xihuan",
      explanation: "",
      options: [],
      assessment: {
        questionType: "character_to_pinyin_typing",
        answerFormat: "free_text",
      },
    } as unknown as VocabQuizQuestion;
    render(
      <QuizQuestion
        question={assessmentQuestion}
        mode="tier1"
        selected={null}
        results={[]}
        index={0}
        questionLimit={5}
        requestedQuestionCount={5}
        isRetryRound={false}
        isLast={false}
        timeLeftMs={0}
        timeLimitMs={null}
        showFinishButton={false}
        choose={choose}
        next={vi.fn()}
        finish={vi.fn()}
        speakWord={vi.fn()}
      />,
    );
    const input = screen.getByRole("textbox", { name: "Your answer" });
    fireEvent.change(input, { target: { value: "xi" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    expect(choose).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter", isComposing: false });
    expect(choose).toHaveBeenCalledWith("xi");
  });

  it("shows no continue button before an answer is chosen", () => {
    render(
      <QuizQuestion
        question={question}
        mode="tier1"
        selected={null}
        results={[]}
        index={0}
        questionLimit={5}
        requestedQuestionCount={5}
        isRetryRound={false}
        isLast={false}
        timeLeftMs={0}
        timeLimitMs={null}
        showFinishButton={false}
        choose={vi.fn()}
        next={vi.fn()}
        finish={vi.fn()}
        speakWord={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /Next question|See results/ })).not.toBeInTheDocument();
  });
});
