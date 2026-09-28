import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "@entities/topic";
import type { SpeakingResultAnalysis } from "../../components/speaking-flow-card/model/analysis";
import { analyzeSpeakingResult } from "../../components/speaking-flow-card/model/analysis";
import { saveSpeakingProgress } from "../../services/database";
import StorySpeakingPage from "./StorySpeakingPage";
import { useSpeakingRecorder, type SpeakingAnalysisResult } from "./hooks/useSpeakingRecorder";

vi.mock("./hooks/useSpeakingRecorder", () => ({ useSpeakingRecorder: vi.fn() }));
vi.mock("../../components/speaking-flow-card/model/analysis", () => ({ analyzeSpeakingResult: vi.fn() }));
vi.mock("../../services/database", () => ({ saveSpeakingProgress: vi.fn().mockResolvedValue(undefined) }));
vi.mock("../../utils/studentSession", () => ({
  getStudentId: () => "student-1",
  getStudentScopeKey: () => "student-1",
  getStudentName: () => "Student One",
}));

function makeTopic(overrides: Partial<Topic> = {}): Topic {
  return {
    id: "story-1",
    name: "午茶時間",
    description: "desc",
    skillFocus: "conversation",
    images: ["img-0.png", "img-1.png"],
    vocabulary: {},
    prompts: ["Scene 0 prompt", "Scene 1 prompt"],
    suggestedAnswers: { 0: "你好", 1: "再見" },
    ...overrides,
  };
}

function recorderMock(overrides: Partial<ReturnType<typeof useSpeakingRecorder>> = {}) {
  return {
    isRecording: false,
    isAnalyzing: false,
    error: null,
    recordingDuration: 0,
    attemptNumber: 0,
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    uploadRecording: vi.fn(),
    ...overrides,
  };
}

function makeRecorderResult(overrides: Partial<SpeakingAnalysisResult> = {}): SpeakingAnalysisResult {
  return {
    metrics: {
      transcription_model: "auto:groq",
      transcription: "你好",
      pitch_contour: [],
      detected_tone: 0,
      tone_accuracy: 80,
      formants: {},
      speech_rate: 1,
      fluency_score: 80,
      pitch_statistics: {},
      feedback: "",
      analysis_version: "stable_v1",
      progression_eligible: true,
    },
    audioBlob: new Blob(),
    masteryPassed: true,
    contentPassed: true,
    verified: true,
    ...overrides,
  };
}

function makeAnalysis(overrides: Partial<SpeakingResultAnalysis> = {}): SpeakingResultAnalysis {
  return {
    accepted: true,
    targetScript: "你好",
    hasTargetScript: true,
    recognizedText: "你好",
    missing: [],
    scriptMismatches: [],
    scriptChunks: [],
    teacherPhraseChunks: [],
    isChunked: false,
    chunkScores: [],
    failedChunks: [],
    contentAccuracy: undefined,
    corrective: undefined,
    meaningJudged: false,
    feedbackReliability: { reliable: true, reasons: [] } as unknown as SpeakingResultAnalysis["feedbackReliability"],
    contentMatchVerified: true,
    contentNeedsRetry: false,
    contentMismatchChunks: [],
    hasChunkMismatch: false,
    effectiveScriptMismatches: [],
    hasScriptMismatch: false,
    needsPhrasePractice: false,
    phrasePracticeItems: [],
    verdict: "ready",
    showCorrective: false,
    hasFix: false,
    hasPhrasePractice: false,
    steps: ["overview"],
    ...overrides,
  };
}

function Harness({
  topic,
  onAddRecord,
  onDone,
  onImageIndexChange,
}: {
  topic: Topic;
  onAddRecord: (record: unknown) => void;
  onDone: () => void;
  onImageIndexChange: (index: number) => void;
}) {
  const [sceneIndex, setSceneIndex] = useState(0);
  return (
    <StorySpeakingPage
      topic={topic}
      selectedImageIndex={sceneIndex}
      onImageIndexChange={(i) => {
        onImageIndexChange(i);
        setSceneIndex(i);
      }}
      onAddRecord={onAddRecord}
      onSceneSubmission={vi.fn()}
      onDone={onDone}
    />
  );
}

describe("StorySpeakingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("shows a Stop button while recording and calls stopRecording", () => {
    const stopRecording = vi.fn();
    vi.mocked(useSpeakingRecorder).mockReturnValue(
      recorderMock({ isRecording: true, recordingDuration: 5, stopRecording }),
    );

    render(
      <StorySpeakingPage
        topic={makeTopic()}
        selectedImageIndex={0}
        onImageIndexChange={vi.fn()}
        onAddRecord={vi.fn()}
        onSceneSubmission={vi.fn()}
        onDone={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Stop (5s)" }));
    expect(stopRecording).toHaveBeenCalledTimes(1);
  });

  it("analyses an uploaded recording through the same feedback flow", async () => {
    const uploadRecording = vi.fn().mockResolvedValue(makeRecorderResult());
    vi.mocked(useSpeakingRecorder).mockReturnValue(recorderMock({ uploadRecording }));
    vi.mocked(analyzeSpeakingResult).mockReturnValue(makeAnalysis());
    const onAddRecord = vi.fn();

    render(
      <StorySpeakingPage
        topic={makeTopic()}
        selectedImageIndex={0}
        onImageIndexChange={vi.fn()}
        onAddRecord={onAddRecord}
        onSceneSubmission={vi.fn()}
        onDone={vi.fn()}
      />,
    );

    const file = new File(["uploaded audio"], "practice.wav", { type: "audio/wav" });
    fireEvent.change(screen.getByLabelText("Upload recording"), { target: { files: [file] } });

    await screen.findByText("How did you do?");
    expect(screen.queryByText("你的錄音")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "略過自我評估" }));
    await screen.findByText("你的錄音");
    expect(uploadRecording).toHaveBeenCalledWith(file);
    expect(onAddRecord).toHaveBeenCalledTimes(1);
  });

  it("shows the executed feedback provider and Praat grounding", async () => {
    const startRecording = vi.fn().mockResolvedValue(
      makeRecorderResult({
        metrics: {
          ...makeRecorderResult().metrics,
          feedback_provenance: {
            requested_provider: "groq",
            executed_provider: "gemini",
            fallback_used: true,
            fallback_reason: "provider_unavailable_or_failed",
            acoustic_context_used: true,
            acoustic_context_supplied: true,
            pronunciation_source: "praat_acoustic_measurements",
          },
        },
      }),
    );
    vi.mocked(useSpeakingRecorder).mockReturnValue(recorderMock({ startRecording }));
    vi.mocked(analyzeSpeakingResult).mockReturnValue(makeAnalysis());

    render(
      <StorySpeakingPage
        topic={makeTopic()}
        selectedImageIndex={0}
        onImageIndexChange={vi.fn()}
        onAddRecord={vi.fn()}
        onSceneSubmission={vi.fn()}
        onDone={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    await screen.findByText("How did you do?");
    fireEvent.click(screen.getByRole("button", { name: "略過自我評估" }));
    expect(await screen.findByText("AI Coach")).toBeInTheDocument();
  });

  it("walks a clean scene straight to the next scene, then Fix before finishing the last scene", async () => {
    const startRecording = vi
      .fn()
      .mockResolvedValueOnce(makeRecorderResult({ metrics: { ...makeRecorderResult().metrics, transcription: "你好" } }))
      .mockResolvedValueOnce(makeRecorderResult({ metrics: { ...makeRecorderResult().metrics, transcription: "再見" } }));
    vi.mocked(useSpeakingRecorder).mockReturnValue(recorderMock({ startRecording }));

    vi.mocked(analyzeSpeakingResult)
      .mockReturnValueOnce(makeAnalysis({ steps: ["overview"], accepted: true }))
      .mockReturnValueOnce(
        makeAnalysis({
          steps: ["overview", "fix"],
          accepted: false,
          showCorrective: true,
          corrective: { errors: ["wrong tone on 再"], hint: "", reveal_answer: false, correct_version: "再見" },
        }),
      );

    const onAddRecord = vi.fn();
    const onDone = vi.fn();
    const onImageIndexChange = vi.fn();
    render(<Harness topic={makeTopic()} onAddRecord={onAddRecord} onDone={onDone} onImageIndexChange={onImageIndexChange} />);

    // Scene 0: clean attempt — Overview is the only step, Continue advances the scene.
    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    await screen.findByText("How did you do?");
    fireEvent.click(screen.getByRole("button", { name: "略過自我評估" }));
    await screen.findByText("你的錄音");
    fireEvent.click(screen.getByRole("button", { name: "Next scene" }));
    // Advancing runs an async saveSpeakingProgress before the scene state
    // updates — wait for scene 1's target text to confirm it landed.
    await screen.findByText("再見");

    expect(onAddRecord).toHaveBeenCalledTimes(1);
    expect(onAddRecord.mock.calls[0][0]).toMatchObject({ model: "groq" });
    expect(onImageIndexChange).toHaveBeenCalledWith(1);
    expect(onDone).not.toHaveBeenCalled();
    expect(saveSpeakingProgress).toHaveBeenCalledTimes(1);
    expect(JSON.parse(localStorage.getItem("studentPhaseFlags:student-1:story-1") ?? "{}").speaking).not.toBe(true);

    // Scene 1 (last scene): needs Fix before Finish is reachable.
    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    await screen.findByText("How did you do?");
    fireEvent.click(screen.getByRole("button", { name: "略過自我評估" }));
    await screen.findByText("你的錄音");
    fireEvent.click(screen.getByRole("button", { name: "See Fix" }));
    // Overview's forward button also runs the async self-eval persist path.
    await screen.findByText("wrong tone on 再");
    fireEvent.click(screen.getByRole("button", { name: "Finish" }));

    expect(onAddRecord).toHaveBeenCalledTimes(2);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(saveSpeakingProgress).toHaveBeenCalledTimes(2);
    expect(JSON.parse(localStorage.getItem("studentPhaseFlags:student-1:story-1") ?? "{}").speaking).toBe(true);
  });
});
