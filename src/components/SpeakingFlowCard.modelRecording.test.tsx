import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SpeakingFlowCard from "./SpeakingFlowCard";

describe("SpeakingFlowCard model recording integration", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("puts a playable listen-and-repeat model inside the student record stage", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("backend unreachable")));

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
        openaiAvailable={false}
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
    expect(screen.getAllByText("請描述這張圖片。")).toHaveLength(1);
    expect(
      await screen.findByText("The scene sentence is ready to repeat; a teacher recording is not available yet."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/Model recording:/)).not.toBeInTheDocument();
  });
});
