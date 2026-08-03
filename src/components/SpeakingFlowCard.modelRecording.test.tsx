import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SpeakingFlowCard from "./SpeakingFlowCard";

describe("SpeakingFlowCard model recording integration", () => {
  it("puts a playable listen-and-repeat model inside the student record stage", () => {
    render(
      <SpeakingFlowCard
        selectedImage="/sample-scenes/market.svg"
        selectedImageIndex={0}
        totalScenes={1}
        modelSentence="請描述這張圖片。"
        narrativeMode="story"
        praatMetrics={null}
        analysisAudioBlob={null}
        error={null}
        isRecording={false}
        isBusy={false}
        isTranscribing={false}
        isAnalyzing={false}
        recordingDuration={0}
        silenceDuration={0}
        submittedAudioName=""
        selectedModel="webspeech"
        groqAvailable={false}
        onSelectedModelChange={vi.fn()}
        recordingButtonDisabled={false}
        onPrimaryRecordingAction={vi.fn()}
        onSubmitVoiceFile={vi.fn()}
        masteryPassed={false}
        contentPassed={false}
        clearedWords={[]}
        onWordDrillPass={vi.fn()}
        hasNextScene={false}
        onNextScene={vi.fn()}
        onViewSummary={vi.fn()}
      />,
    );

    expect(screen.getByRole("region", { name: "Record your story" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Listen and repeat model recording" })).toBeInTheDocument();
    expect(screen.getByLabelText("Model recording: 姐姐在家裡做飯。")).toHaveAttribute(
      "src",
      "/uploads/examples/pic1_example.mp3",
    );
    expect(screen.getByRole("button", { name: /Practice this model recording/ })).toBeInTheDocument();
  });
});
