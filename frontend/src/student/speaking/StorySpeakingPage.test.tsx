import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "../../components/content/topic-selector/types";
import type { SpeakingResultAnalysis } from "../../components/speaking-flow-card/SpeakingResultsFlow.analysis";
import { analyzeSpeakingResult } from "../../components/speaking-flow-card/SpeakingResultsFlow.analysis";
import { saveSpeakingProgress } from "../../services/database";
import StorySpeakingPage from "./StorySpeakingPage";
import { useSpeakingRecorder, type SpeakingAnalysisResult } from "./useSpeakingRecorder";

vi.mock("./useSpeakingRecorder", () => ({ useSpeakingRecorder: vi.fn() }));
vi.mock("../../components/speaking-flow-card/SpeakingResultsFlow.analysis", () => ({ analyzeSpeakingResult: vi.fn() }));
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
    ...overrides,
  };
}

function makeRecorderResult(overrides: Partial<SpeakingAnalysisResult> = {}): SpeakingAnalysisResult {
  return {
    metrics: {
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
    weakItems: [],
    pronunciationMastery: undefined,
    masteryCounts: undefined,
    contentAccuracy: undefined,
    corrective: undefined,
    meaningJudged: false,
    feedbackReliability: { reliable: true, reasons: [] } as unknown as SpeakingResultAnalysis["feedbackReliability"],
    failedWords: [],
    contentMatchVerified: true,
    contentNeedsRetry: false,
    contentMismatchChunks: [],
    hasChunkMismatch: false,
    effectiveScriptMismatches: [],
    legacyPracticeWords: [],
    hasScriptMismatch: false,
    needsPhrasePractice: false,
    phrasePracticeItems: [],
    practicePartLabels: [],
    practiceTargets: [],
    practicePartCount: 0,
    verdict: "ready",
    showCorrective: false,
    hasFix: false,
    hasPhrasePractice: false,
    hasPractice: false,
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
      onDone={onDone}
    />
  );
}

describe("StorySpeakingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
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
        onDone={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Stop (5s)" }));
    expect(stopRecording).toHaveBeenCalledTimes(1);
  });

  it("walks a clean scene straight to the next scene, then Fix/Practice before finishing the last scene", async () => {
    const startRecording = vi
      .fn()
      .mockResolvedValueOnce(makeRecorderResult({ metrics: { ...makeRecorderResult().metrics, transcription: "你好" } }))
      .mockResolvedValueOnce(makeRecorderResult({ metrics: { ...makeRecorderResult().metrics, transcription: "再見" } }));
    vi.mocked(useSpeakingRecorder).mockReturnValue(recorderMock({ startRecording }));

    vi.mocked(analyzeSpeakingResult)
      .mockReturnValueOnce(makeAnalysis({ steps: ["overview"], accepted: true }))
      .mockReturnValueOnce(
        makeAnalysis({
          steps: ["overview", "fix", "practice"],
          accepted: false,
          showCorrective: true,
          corrective: { errors: ["wrong tone on 再"], hint: "", reveal_answer: false, correct_version: "再見" },
          practiceTargets: [{ key: "p0", label: "再", word: null }],
        }),
      );

    const onAddRecord = vi.fn();
    const onDone = vi.fn();
    const onImageIndexChange = vi.fn();
    render(<Harness topic={makeTopic()} onAddRecord={onAddRecord} onDone={onDone} onImageIndexChange={onImageIndexChange} />);

    // Scene 0: clean attempt — Overview is the only step, Continue advances the scene.
    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    await screen.findByText("Meaning accurate");
    fireEvent.click(screen.getByRole("button", { name: "Next scene" }));

    expect(onAddRecord).toHaveBeenCalledTimes(1);
    expect(onImageIndexChange).toHaveBeenCalledWith(1);
    expect(onDone).not.toHaveBeenCalled();
    expect(saveSpeakingProgress).toHaveBeenCalledTimes(1);
    expect(JSON.parse(sessionStorage.getItem("studentPhaseFlags:student-1:story-1") ?? "{}").speaking).not.toBe(true);

    // Scene 1 (last scene): needs Fix then Practice before Finish is reachable.
    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    await screen.findByText("Meaning needs another look");
    fireEvent.click(screen.getByRole("button", { name: "See Fix" }));
    expect(screen.getByText("wrong tone on 再")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "See Practice" }));
    expect(screen.getByText("再")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Finish" }));

    expect(onAddRecord).toHaveBeenCalledTimes(2);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(saveSpeakingProgress).toHaveBeenCalledTimes(2);
    expect(JSON.parse(sessionStorage.getItem("studentPhaseFlags:student-1:story-1") ?? "{}").speaking).toBe(true);
  });
});
