import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
      onSubmit={onSubmit}
    />
  );
}

describe("QuizQuestionSurface", () => {
  it("stages a meaning choice and only submits after explicit confirmation", () => {
    const onSubmit = vi.fn();
    const { container } = render(<SurfaceHarness question={makeQuestion("basic_meaning_mcq", "single_choice", "What does 電話 mean?")} onSubmit={onSubmit} />);

    fireEvent.click(screen.getByRole("button", { name: "選項 1：電話" }));
    expect(container.querySelectorAll(".sa-quiz__option .sa-icon")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "提交答案" })).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("supports option 1 and Enter without submitting twice", () => {
    const onSubmit = vi.fn();
    render(<SurfaceHarness question={makeQuestion("basic_meaning_mcq", "single_choice", "Choose one.")} onSubmit={onSubmit} />);

    fireEvent.keyDown(window, { key: "1" });
    expect(screen.getByRole("button", { name: "選項 1：電話" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("accepts pinyin typing and tone keypad input", () => {
    const onSubmit = vi.fn();
    render(<SurfaceHarness question={makeQuestion("character_to_pinyin_typing", "free_text", "Type the pinyin reading.")} onSubmit={onSubmit} />);

    const input = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "n" } });
    input.setSelectionRange(1, 1);
    fireEvent.click(screen.getByRole("button", { name: "i tone 2: í" }));
    expect(input).toHaveValue("ní");

    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("inserts the displayed character from every vowel row", () => {
    render(<SurfaceHarness question={makeQuestion("character_to_pinyin_typing", "free_text", "Type the pinyin reading.")} onSubmit={vi.fn()} />);

    const input = screen.getByRole("textbox") as HTMLInputElement;
    const marks = [
      "ā", "á", "ǎ", "à", "ē", "é", "ě", "è",
      "ī", "í", "ǐ", "ì", "ō", "ó", "ǒ", "ò",
      "ū", "ú", "ǔ", "ù", "ǖ", "ǘ", "ǚ", "ǜ",
    ];
    marks.forEach((mark) => {
      fireEvent.change(input, { target: { value: "" } });
      input.setSelectionRange(0, 0);
      fireEvent.click(screen.getByRole("button", { name: new RegExp(`: ${mark}$`) }));
      expect(input).toHaveValue(mark);
    });
  });

  it("inserts at the cursor and restores focus for continued typing", async () => {
    const user = userEvent.setup();
    render(<SurfaceHarness question={makeQuestion("character_to_pinyin_typing", "free_text", "Type the pinyin reading.")} onSubmit={vi.fn()} />);

    const input = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "n hao" } });
    input.focus();
    input.setSelectionRange(1, 1);
    await user.click(screen.getByRole("button", { name: "i tone 3: ǐ" }));

    expect(input).toHaveValue("nǐ hao");
    await waitFor(() => {
      expect(input).toHaveFocus();
      expect(input.selectionStart).toBe(2);
      expect(input.selectionEnd).toBe(2);
    });
    await user.keyboard("men");
    expect(input).toHaveValue("nǐmen hao");
  });

  it("replaces only the selected text with the chosen character", async () => {
    const user = userEvent.setup();
    render(<SurfaceHarness question={makeQuestion("character_to_pinyin_typing", "free_text", "Type the pinyin reading.")} onSubmit={vi.fn()} />);

    const input = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "ni hao" } });
    input.focus();
    input.setSelectionRange(0, 2);
    await user.click(screen.getByRole("button", { name: "e tone 2: é" }));

    expect(input).toHaveValue("é hao");
    await waitFor(() => expect(input.selectionStart).toBe(1));
  });

  it("renders a context blank as a dedicated answer slot", () => {
    const { container } = render(<SurfaceHarness question={makeQuestion("context_cloze_mcq", "single_choice", "Choose the correct word in the sentence: 我找不到____。 ")} onSubmit={vi.fn()} />);

    expect(container.querySelector(".sa-quiz__cloze-stage")).toBeInTheDocument();
    expect(screen.getByLabelText("missing word")).toHaveTextContent("____");
    expect(screen.getByRole("heading", { name: "選擇能完成句子的詞語。" })).toBeInTheDocument();
    expect(screen.queryByText("Context clue")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "選項 1：電話" })).toBeInTheDocument();
  });
});
