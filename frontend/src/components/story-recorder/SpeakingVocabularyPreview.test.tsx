import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SpeakingVocabularyPreview from "./SpeakingVocabularyPreview";
import type { SpeakingVocabularyPreviewItem } from "../../utils/speakingVocabulary";

const items: SpeakingVocabularyPreviewItem[] = [
  { wordId: "w1", word: "錢包", pinyin: "qiánbāo", pos: "N", meaning: "wallet" },
  { wordId: "w2", word: "有空", pos: "V", meaning: "to be free" },
];

describe("SpeakingVocabularyPreview", () => {
  it("shows the word count and every vocabulary item's word/pinyin/pos/meaning", () => {
    render(<SpeakingVocabularyPreview items={items} onStart={vi.fn()} />);
    expect(screen.getByText("2 words")).toBeInTheDocument();
    expect(screen.getByText("錢包")).toBeInTheDocument();
    expect(screen.getByText("qiánbāo")).toBeInTheDocument();
    expect(screen.getByText("有空")).toBeInTheDocument();
  });

  it("never shows quiz answer buttons, scores, or mastery/BKT status", () => {
    render(<SpeakingVocabularyPreview items={items} onStart={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /submit|answer|correct/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/mastery|BKT|p\(learned\)/i)).not.toBeInTheDocument();
  });

  it("calls onStart when the Start Speaking button is pressed", () => {
    const onStart = vi.fn();
    render(<SpeakingVocabularyPreview items={items} onStart={onStart} />);
    fireEvent.click(screen.getByRole("button", { name: /Start Speaking/i }));
    expect(onStart).toHaveBeenCalled();
  });

  it("shows a Back button only when onBack is provided", () => {
    const { rerender } = render(<SpeakingVocabularyPreview items={items} onStart={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Back/i })).not.toBeInTheDocument();

    const onBack = vi.fn();
    rerender(<SpeakingVocabularyPreview items={items} onStart={vi.fn()} onBack={onBack} />);
    fireEvent.click(screen.getByRole("button", { name: /Back/i }));
    expect(onBack).toHaveBeenCalled();
  });
});
