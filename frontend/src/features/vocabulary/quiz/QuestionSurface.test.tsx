import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { VocabAssessmentQuestion, VocabQuizQuestion } from "@entities/vocabulary";
import QuizQuestionSurface from "./QuestionSurface";

function makeQuestion(
  questionType: VocabAssessmentQuestion["questionType"],
  answerFormat: VocabAssessmentQuestion["answerFormat"],
  prompt: string,
): VocabQuizQuestion {
  const assessment: VocabAssessmentQuestion = {
    questionId: `${questionType}-1`,
    wordId: "word-1",
    targetWord: "電話",
    pinyin: "diàn huà",
    pos: "N",
    simpleEnglishMeaning: "telephone",
    level: "easy",
    difficultyWeight: 1,
    questionType,
    answerFormat,
    prompt,
    options: ["電話", "朋友", "老師", "電腦"],
    correctAnswer: answerFormat === "free_text" ? "diàn huà" : "電話",
    acceptedAnswers: [answerFormat === "free_text" ? "diàn huà" : "電話"],
    explanation: "A context clue.",
  };
  return {
    kind: "assessment",
    word: "電話",
    prompt,
    options: assessment.options,
    correctAnswer: assessment.correctAnswer,
    acceptedAnswers: assessment.acceptedAnswers,
    explanation: assessment.explanation,
    assessment,
    isAiGenerated: false,
  };
}

function SurfaceHarness({ question, onSubmit }: { question: VocabQuizQuestion; onSubmit: () => void }) {
  const [draftAnswer, setDraftAnswer] = useState<string | null>(null);
  const [pinyinDraft, setPinyinDraft] = useState("");
  return (
    <QuizQuestionSurface
      question={question}
      entry={{ word: "電話", translation: "telephone", pinyin: "diàn huà" }}
      entries={[{ word: "電話", translation: "telephone", pinyin: "diàn huà" }]}
      lessonLabel="Lesson 1"
      draftAnswer={draftAnswer}
      onDraftAnswerChange={setDraftAnswer}
      pinyinDraft={pinyinDraft}
      onPinyinChange={setPinyinDraft}
      showingFeedback={false}
      hint="Think about the action in this sentence."
      hintOpen={false}
      onToggleHint={vi.fn()}
      onSubmit={onSubmit}
      onNext={vi.fn()}
    />
  );
}

describe("QuizQuestionSurface", () => {
  it("stages a meaning choice and only submits after explicit confirmation", () => {
    const onSubmit = vi.fn();
    render(<SurfaceHarness question={makeQuestion("basic_meaning_mcq", "single_choice", "What does 電話 mean?")} onSubmit={onSubmit} />);

    fireEvent.click(screen.getByRole("button", { name: "Option 1: 電話" }));
    expect(screen.getByRole("button", { name: /Submit answer/i })).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /Submit answer/i }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("supports option 1 and Enter without submitting twice", () => {
    const onSubmit = vi.fn();
    render(<SurfaceHarness question={makeQuestion("basic_meaning_mcq", "single_choice", "Choose one.")} onSubmit={onSubmit} />);

    fireEvent.keyDown(window, { key: "1" });
    expect(screen.getByRole("button", { name: "Option 1: 電話" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("accepts pinyin typing and tone keypad input", () => {
    const onSubmit = vi.fn();
    render(<SurfaceHarness question={makeQuestion("character_to_pinyin_typing", "free_text", "Type the pinyin reading.")} onSubmit={onSubmit} />);

    const input = screen.getByLabelText("Pinyin with tones") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "ni3" } });
    input.setSelectionRange(3, 3);
    fireEvent.click(screen.getByRole("button", { name: "i tone 2: í" }));
    expect(input).toHaveValue("ní");

    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("renders a context blank as a dedicated answer slot", () => {
    render(<SurfaceHarness question={makeQuestion("context_cloze_mcq", "single_choice", "Choose the correct word in the sentence: 我找不到____。 ")} onSubmit={vi.fn()} />);

    expect(screen.getByLabelText("Sentence completion prompt")).toBeInTheDocument();
    expect(screen.getByLabelText("missing word")).toHaveTextContent("____");
    expect(screen.getByRole("button", { name: "Option 1: 電話" })).toBeInTheDocument();
  });
});
