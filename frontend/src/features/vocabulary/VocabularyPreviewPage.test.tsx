import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Topic } from "@entities/topic";
import VocabularyPreviewPage from "./VocabularyPreviewPage";

function makeTopic(): Topic {
  return {
    id: "lesson-1",
    name: "Lesson 1",
    images: [],
    vocabulary: {},
    vocabAssessment: [
      {
        questionId: "word-1-question",
        wordId: "word-1",
        targetWord: "知道",
        pinyin: "zhidao",
        pos: "V",
        simpleEnglishMeaning: "to know",
        level: "easy",
        difficultyWeight: 1,
        questionType: "basic_meaning_mcq",
        answerFormat: "single_choice",
        prompt: "What does 知道 mean?",
        options: ["to know", "to eat"],
        correctAnswer: "to know",
        acceptedAnswers: ["to know"],
        explanation: "",
        audioUrl: "/uploads/audio/zhidao.mp3",
      },
    ],
  };
}

describe("VocabularyPreviewPage", () => {
  it("uses the reference card anatomy with real vocabulary data", () => {
    render(
      <VocabularyPreviewPage
        topic={makeTopic()}
        lessonLabel="Lesson 1"
        onStartSpeaking={vi.fn()}
      />,
    );

    const grid = screen.getByLabelText("Vocabulary preview");
    expect(grid).toHaveClass("sa-vocab-preview__grid");
    expect(screen.getByText("01")).toBeInTheDocument();
    expect(screen.getByText("知道")).toBeInTheDocument();
    expect(screen.getByText("to know")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Listen" })).toBeInTheDocument();
  });
});
