import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Topic } from "@entities/topic";
import VocabularyPreviewPage from "./VocabularyPreviewPage";

function makeTopic(wordCount = 1): Topic {
  return {
    id: "lesson-1",
    name: "Lesson 1",
    images: [],
    vocabulary: {},
    vocabAssessment: Array.from({ length: wordCount }, (_, index) => ({
      questionId: `word-${index + 1}-question`,
      wordId: `word-${index + 1}`,
      targetWord: index === 0 ? "知道" : `word-${index + 1}`,
      pinyin: index === 0 ? "zhidao" : `pinyin-${index + 1}`,
      pos: "V",
      simpleEnglishMeaning: index === 0 ? "to know" : `meaning ${index + 1}`,
      level: "easy",
      difficultyWeight: 1,
      questionType: "basic_meaning_mcq",
      answerFormat: "single_choice",
      prompt: "What does this word mean?",
      options: ["to know", "to eat"],
      correctAnswer: "to know",
      acceptedAnswers: ["to know"],
      explanation: "",
      audioUrl: "/uploads/audio/zhidao.mp3",
    })),
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

  it("paginates larger vocabulary sets to keep review pages short", async () => {
    const user = userEvent.setup();
    render(
      <VocabularyPreviewPage
        topic={makeTopic(20)}
        lessonLabel="Lesson 1"
        onStartSpeaking={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Vocabulary preview").querySelectorAll(".sa-vocab-preview__card")).toHaveLength(12);
    const pager = screen.getByRole("navigation", { name: "Vocabulary pages" });
    const footer = pager.closest(".sa-page__actions");
    expect(footer).not.toBeNull();
    expect(footer).toContainElement(screen.getByRole("button", { name: /Start quiz/i }));
    expect(screen.getByRole("status")).toHaveTextContent(/Page 1 of 2.*1.?12 of 20/);
    expect(screen.getByRole("button", { name: "Previous vocabulary page" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next vocabulary page" }));

    expect(screen.getByText("13")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/Page 2 of 2.*13.?20 of 20/);
    expect(screen.getByRole("button", { name: "Next vocabulary page" })).toBeDisabled();
  });

  it("keeps the start action in the shared footer without a pager for short lessons", () => {
    render(
      <VocabularyPreviewPage
        topic={makeTopic(12)}
        lessonLabel="Lesson 1"
        onStartSpeaking={vi.fn()}
      />,
    );

    expect(screen.queryByRole("navigation", { name: "Vocabulary pages" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start quiz/i })).toBeInTheDocument();
  });
});
