import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "../../components/content/topic-selector/types";
import type { ConversationTurn, WordProsody, WordProsodySyllable } from "../../components/story-recorder/StoryRecorder";
import type { SpeakingResultAnalysis } from "../../components/speaking-flow-card/SpeakingResultsFlow.analysis";
import { analyzeSpeakingResult } from "../../components/speaking-flow-card/SpeakingResultsFlow.analysis";
import { saveSpeakingProgress } from "../../services/database";
import ConversationPage from "./ConversationPage";
import { useSpeakingRecorder, type SpeakingAnalysisResult } from "../speaking/hooks/useSpeakingRecorder";

vi.mock("../speaking/hooks/useSpeakingRecorder", () => ({ useSpeakingRecorder: vi.fn() }));
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
    name: "打電話",
    description: "desc",
    skillFocus: "conversation",
    images: ["img-0.png"],
    vocabulary: {},
    ...overrides,
  };
}

const turns: ConversationTurn[] = [
  { id: "t0", speaker: "system", text: "你好嗎？", pinyin: "nǐ hǎo ma", translation: "How are you?" },
  { id: "t1", speaker: "student", text: "我很好", targetText: "我很好", pinyin: "wǒ hěn hǎo", translation: "I'm good" },
];

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

function makeWord(token: string, index: number, status: WordProsody["diagnostic_status"]): WordProsody {
  return {
    token,
    index,
    start_time: 0,
    end_time: 0.5,
    pitch_contour: [],
    mean_pitch: 0,
    pitch_range: 0,
    start_pitch: 0,
    end_pitch: 0,
    contour_shape: "",
    feedback: index === 0 ? "Keep this word clear." : "",
    diagnostic_status: status,
    syllables: [{
      char: token,
      tone: 3,
      score: 80,
      passed: status === "CORRECT",
      diagnostic_status: status,
      pinyin: index === 0 ? "w\u01d2" : "h\u011bn",
    } as WordProsodySyllable],
  };
}

function makeRecorderResult(overrides: Partial<SpeakingAnalysisResult> = {}): SpeakingAnalysisResult {
  return {
    metrics: {
      transcription_model: "auto:ctwhisper",
      word_prosody: [makeWord("\u6211", 0, "CORRECT"), makeWord("\u5f88", 1, "UNCERTAIN")],
      transcription: "我很好",
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
    targetScript: "我很好",
    hasTargetScript: true,
    recognizedText: "我很好",
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

describe("ConversationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("walks system -> student -> feedback -> summary, saving progress and finishing on the last turn", async () => {
    const startRecording = vi.fn().mockResolvedValueOnce(makeRecorderResult());
    vi.mocked(useSpeakingRecorder).mockReturnValue(recorderMock({ startRecording }));
    vi.mocked(analyzeSpeakingResult).mockReturnValueOnce(makeAnalysis({ accepted: true }));

    const onAddRecord = vi.fn();
    const onDone = vi.fn();
    render(
      <ConversationPage topic={makeTopic()} turns={turns} onAddRecord={onAddRecord} onSceneSubmission={vi.fn()} onDone={onDone} onBack={vi.fn()} />,
    );

    // System turn: listen, then Continue moves to the student's turn.
    expect(screen.getByText("你好嗎？")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    // Student turn: selfEval is auto-skipped, Record triggers analysis.
    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    await screen.findByText("Meaning accurate");
    expect(screen.getByText("w\u01d2")).toBeInTheDocument();
    expect(screen.getByText("Keep this word clear.")).toBeInTheDocument();
    expect(screen.getByText("Uncertain")).toBeInTheDocument();
    expect(screen.getByText("Verified recording")).toBeInTheDocument();
    expect(onAddRecord).toHaveBeenCalledTimes(1);
    expect(onAddRecord.mock.calls[0][0].model).toBe("ctwhisper");
    expect(saveSpeakingProgress).toHaveBeenCalledTimes(1);

    // Only one exchange in this fixture -> the feedback continue button reads "Finish".
    fireEvent.click(screen.getByRole("button", { name: "Finish" }));

    expect(onDone).toHaveBeenCalledTimes(1);
    expect(JSON.parse(sessionStorage.getItem("studentPhaseFlags:student-1:story-1") ?? "{}").conversation).toBe(true);
  });

  it("shows a Stop button while recording and calls stopRecording", () => {
    const stopRecording = vi.fn();
    vi.mocked(useSpeakingRecorder).mockReturnValue(
      recorderMock({ isRecording: true, recordingDuration: 4, stopRecording }),
    );

    render(
      <ConversationPage topic={makeTopic()} turns={turns} onAddRecord={vi.fn()} onSceneSubmission={vi.fn()} onDone={vi.fn()} onBack={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    fireEvent.click(screen.getByRole("button", { name: "Stop (4s)" }));
    expect(stopRecording).toHaveBeenCalledTimes(1);
  });

  it("Record again returns to the student recording step", async () => {
    const startRecording = vi.fn().mockResolvedValueOnce(makeRecorderResult());
    vi.mocked(useSpeakingRecorder).mockReturnValue(recorderMock({ startRecording }));
    vi.mocked(analyzeSpeakingResult).mockReturnValueOnce(makeAnalysis({ accepted: false }));

    render(
      <ConversationPage topic={makeTopic()} turns={turns} onAddRecord={vi.fn()} onSceneSubmission={vi.fn()} onDone={vi.fn()} onBack={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    await screen.findByText("Meaning needs another look");

    fireEvent.click(screen.getByRole("button", { name: "Record again" }));

    expect(screen.getByRole("button", { name: "Record" })).toBeInTheDocument();
    expect(screen.queryByText("Meaning needs another look")).not.toBeInTheDocument();
  });

  it("does not label an unverified recorder result as verified", async () => {
    const startRecording = vi.fn().mockResolvedValueOnce(makeRecorderResult({ verified: false }));
    vi.mocked(useSpeakingRecorder).mockReturnValue(recorderMock({ startRecording }));
    vi.mocked(analyzeSpeakingResult).mockReturnValueOnce(makeAnalysis({ accepted: true }));

    render(
      <ConversationPage topic={makeTopic()} turns={turns} onAddRecord={vi.fn()} onSceneSubmission={vi.fn()} onDone={vi.fn()} onBack={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    await screen.findByText("Meaning accurate");

    expect(screen.queryByText("Verified recording")).not.toBeInTheDocument();
  });
});
