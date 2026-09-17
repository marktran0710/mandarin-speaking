import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { QuizQuestion } from "./QuizQuestion";
import type { VocabQuizAssessmentQuestion, VocabQuizMode } from "./model";

function assessmentQuestion(questionType: VocabQuizAssessmentQuestion["assessment"]["questionType"]): VocabQuizAssessmentQuestion {
  return {
    kind: "assessment",
    word: "書",
    prompt: "書",
    options: ["book", "table", "room", "water"],
    correctAnswer: "book",
    acceptedAnswers: ["book"],
    explanation: "",
    isAiGenerated: false,
    assessment: {
      questionId: "q1", wordId: "w1", targetWord: "書", pinyin: "shū", pos: "N",
      simpleEnglishMeaning: "book", level: "easy", difficultyWeight: 1,
      questionType, answerFormat: questionType === "character_to_pinyin_typing" ? "free_text" : "single_choice",
      prompt: "書", options: ["book", "table", "room", "water"], correctAnswer: "book",
      acceptedAnswers: ["book"], explanation: "",
    },
  };
}

function renderQuestion(question: VocabQuizAssessmentQuestion, mode: VocabQuizMode, speakWord = vi.fn()) {
  render(
    <QuizQuestion
      question={question} mode={mode} selected={null} results={[]} index={0}
      questionLimit={5} requestedQuestionCount={5} isRetryRound={false} isLast={false}
      timeLeftMs={0} timeLimitMs={null} showFinishButton={false}
      choose={vi.fn()} next={vi.fn()} finish={vi.fn()} speakWord={speakWord}
    />,
  );
  return speakWord;
}

describe("Round 1 model-audio button", () => {
  it("offers a Listen button on the tier1 meaning question and plays the target word", () => {
    const speakWord = renderQuestion(assessmentQuestion("basic_meaning_mcq"), "tier1");
    const listen = screen.getByRole("button", { name: /Listen to 書/ });
    fireEvent.click(listen);
    expect(speakWord).toHaveBeenCalledWith("書");
  });

  it("does NOT offer audio in Round 2 (pinyin typing) — it would give the answer away", () => {
    renderQuestion(assessmentQuestion("character_to_pinyin_typing"), "tier2");
    expect(screen.queryByRole("button", { name: /Listen to/ })).not.toBeInTheDocument();
  });

  it("does NOT offer audio for a meaning question outside Round 1", () => {
    renderQuestion(assessmentQuestion("basic_meaning_mcq"), "weak_words");
    expect(screen.queryByRole("button", { name: /Listen to/ })).not.toBeInTheDocument();
  });
});
