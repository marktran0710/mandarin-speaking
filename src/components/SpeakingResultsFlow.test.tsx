import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SpeakingResultsFlow from "./SpeakingResultsFlow";
import type { PraatMetrics } from "./StoryRecorder";

const metrics = (overrides: Partial<PraatMetrics> = {}): PraatMetrics => ({
  transcription: "你好嗎",
  pitch_contour: [],
  word_prosody: [],
  detected_tone: 1,
  tone_accuracy: 90,
  formants: {},
  speech_rate: 3,
  fluency_score: 80,
  pitch_statistics: {},
  feedback: "",
  ai_feedback: {
    provider: "test",
    vocabulary_coverage: { score: 100, used: [], missing: [], feedback: "" },
    coherence: { score: 0, feedback: "", corrections: [] },
    pronunciation_note: { score: 0, feedback: "" },
    improved_version: "",
    practice_prompt: "",
  },
  ...overrides,
});

const baseProps = {
  selectedImage: "img.png",
  selectedImageIndex: 0,
  totalScenes: 1,
  modelSentence: "你好嗎",
  narrativeMode: "story" as const,
  attempts: 1,
  masteryPassed: true,
  praatMetrics: metrics(),
  analysisAudioBlob: null,
  submittedAudioName: "",
  clearedWords: [],
  onWordDrillPass: vi.fn(),
  hasNextScene: false,
  onNextScene: vi.fn(),
  onViewSummary: vi.fn(),
  onRecordAgain: vi.fn(),
};

describe("SpeakingResultsFlow — self-eval step", () => {
  it("shows the self-eval step first on a ready attempt, then reveals the comparison after submitting", () => {
    const onSelfEvalSubmit = vi.fn();
    render(
      <SpeakingResultsFlow
        {...baseProps}
        ready
        onSelfEvalSubmit={onSelfEvalSubmit}
      />,
    );

    expect(screen.getByText(/Recording done!/)).toBeInTheDocument();
    expect(screen.queryByText("Meaning")).not.toBeInTheDocument();

    const [contentGroup, pronunciationGroup] = screen.getAllByRole("radiogroup");
    fireEvent.click(within(contentGroup).getByRole("radio", { name: /Good/ }));
    fireEvent.click(within(pronunciationGroup).getByRole("radio", { name: /OK/ }));
    fireEvent.click(screen.getByRole("button", { name: /See system feedback/ }));

    expect(onSelfEvalSubmit).toHaveBeenCalledWith({ content: "good", pronunciation: "ok" });
    expect(screen.getByText("Meaning")).toBeInTheDocument();
    expect(screen.getByText("Pronunciation")).toBeInTheDocument();
  });

  it("skips straight to the overview verdict without calling onSelfEvalSubmit", () => {
    const onSelfEvalSubmit = vi.fn();
    render(
      <SpeakingResultsFlow
        {...baseProps}
        ready
        onSelfEvalSubmit={onSelfEvalSubmit}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Skip/ }));

    expect(onSelfEvalSubmit).not.toHaveBeenCalled();
    expect(screen.queryByText(/Recording done!/)).not.toBeInTheDocument();
    expect(screen.queryByText("Meaning")).not.toBeInTheDocument();
  });

  it("never shows the self-eval step on a not-yet-ready attempt", () => {
    render(<SpeakingResultsFlow {...baseProps} ready={false} />);

    expect(screen.queryByText(/Recording done!/)).not.toBeInTheDocument();
  });
});
