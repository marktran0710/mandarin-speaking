import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "@entities/topic";
import type { ConversationTurn, WordProsody, WordProsodySyllable } from "../../components/story-recorder/StoryRecorder";
import type { SpeakingResultAnalysis } from "../../components/speaking-flow-card/model/analysis";
import { analyzeSpeakingResult } from "../../components/speaking-flow-card/model/analysis";
import { saveSpeakingProgress } from "../../services/database";
import ConversationPage, { groupConversationTurns } from "./ConversationPage";
import { useSpeakingRecorder, type SpeakingAnalysisResult } from "../speaking/hooks/useSpeakingRecorder";

vi.mock("../speaking/hooks/useSpeakingRecorder", () => ({ useSpeakingRecorder: vi.fn() }));
vi.mock("../../components/speaking-flow-card/model/analysis", () => ({ analyzeSpeakingResult: vi.fn() }));
vi.mock("../../services/database", () => ({ saveSpeakingProgress: vi.fn().mockResolvedValue(undefined) }));
vi.mock("../../utils/studentSession", () => ({
  getStudentId: () => "student-1",
  getStudentScopeKey: () => "student-1",
  getStudentName: () => "Student One",
  getStudentGender: () => "male",
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
  { id: "t1", speaker: "student", text: "我很好", targetText: "我很好", pinyin: "wǒ hěn hǎo", translation: "I'm good", targetAudioUrl: "/uploads/audio/student-model.mp3" },
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
    uploadRecording: vi.fn(),
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

describe("ConversationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  afterEach(() => vi.unstubAllGlobals());

  it("groups consecutive history turns by speaker so only each group end needs a marker", () => {
    const grouped = groupConversationTurns([
      { id: "system-1", speaker: "system", text: "你好" },
      { id: "system-2", speaker: "system", text: "你好嗎？" },
      { id: "student-1", speaker: "student", text: "很好" },
      { id: "student-2", speaker: "student", text: "謝謝" },
    ]);

    expect(grouped.map((group) => group.map((turn) => turn.id))).toEqual([
      ["system-1", "system-2"],
      ["student-1", "student-2"],
    ]);
  });

  it("keeps the page usable when a lesson has no authored conversation turns", () => {
    const onBack = vi.fn();
    render(
      <ConversationPage topic={makeTopic()} turns={[]} onAddRecord={vi.fn()} onSceneSubmission={vi.fn()} onDone={vi.fn()} onBack={onBack} />,
    );

    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByText("對話內容尚未準備好")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "返回課程目錄" })[1]);
    expect(onBack).toHaveBeenCalledTimes(1);
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
    fireEvent.click(screen.getByRole("button", { name: "繼續" }));
    expect(screen.getByRole("button", { name: "示範音" })).toBeInTheDocument();

    // Student turn: analysis opens the self-evaluation step first.
    fireEvent.click(screen.getByRole("button", { name: "錄音" }));
    await screen.findByText("你覺得表現如何？");
    fireEvent.click(screen.getByRole("button", { name: "略過自我評估" }));
    await screen.findByText("你的錄音");
    const firstWord = screen.getByRole("button", { name: "我: 選擇以比較" });
    expect(firstWord).toBeInTheDocument();
    fireEvent.click(firstWord);
    expect(screen.getByText("錄音已確認")).toBeInTheDocument();
    expect(onAddRecord).toHaveBeenCalledTimes(1);
    expect(onAddRecord.mock.calls[0][0].model).toBe("ctwhisper");
    expect(saveSpeakingProgress).toHaveBeenCalledTimes(1);
    expect(document.querySelector(".sa-result-review__footer")).toBeTruthy();
    expect(document.querySelector(".sa-result-review__footer .sa-conversation__footer")).toBeTruthy();

    // Only one exchange in this fixture -> the feedback continue button reads "Finish".
    fireEvent.click(screen.getByRole("button", { name: "完成" }));

    expect(onDone).toHaveBeenCalledTimes(1);
    expect(JSON.parse(localStorage.getItem("studentPhaseFlags:student-1:story-1") ?? "{}").conversation).toBe(true);
  });

  it("shows a Stop button while recording and calls stopRecording", () => {
    const stopRecording = vi.fn();
    vi.mocked(useSpeakingRecorder).mockReturnValue(
      recorderMock({ isRecording: true, recordingDuration: 4, stopRecording }),
    );

    render(
      <ConversationPage topic={makeTopic()} turns={turns} onAddRecord={vi.fn()} onSceneSubmission={vi.fn()} onDone={vi.fn()} onBack={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "繼續" }));

    fireEvent.click(screen.getByRole("button", { name: /停止.*4/ }));
    expect(stopRecording).toHaveBeenCalledTimes(1);
  });

  it("analyses an uploaded recording for the current response", async () => {
    const result = makeRecorderResult();
    result.metrics.pronunciation_evaluation = {
      status: "scored", reason: null, score: { total: 87, renormalized: false, dimensions: [] },
      metrics: {}, words: [],
      feedback: { summary: "Keep the falling tone clear.", focus_words: [{ word: "好", feedback: "Let the pitch dip gently." }], practice_tip: "Repeat the sentence slowly.", source: "llm" },
      model: { scoring_version: "pronunciation-score-v1", acoustic_pipeline_version: "v1", feedback_model: "gpt-6-luna", feedback_source: "llm" },
      reference: { key: "reference-1", cache_hit: false, audio_url: "/uploads/sample.wav" },
    };
    const uploadRecording = vi.fn().mockResolvedValue(result);
    vi.mocked(useSpeakingRecorder).mockReturnValue(recorderMock({ uploadRecording }));
    vi.mocked(analyzeSpeakingResult).mockReturnValueOnce(makeAnalysis({ accepted: true }));
    const onAddRecord = vi.fn();
    const onSceneSubmission = vi.fn();

    render(
      <ConversationPage
        topic={makeTopic()}
        turns={turns}
        onAddRecord={onAddRecord}
        onSceneSubmission={onSceneSubmission}
        onDone={vi.fn()}
        onBack={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "繼續" }));

    const file = new File(["uploaded audio"], "reply.mp3", { type: "audio/mpeg" });
    const uploadInput = screen.getAllByLabelText("上傳").find((element) => element.tagName === "INPUT") as HTMLInputElement;
    fireEvent.change(uploadInput, { target: { files: [file] } });

    await screen.findByText("你覺得表現如何？");
    fireEvent.click(screen.getByRole("button", { name: "略過自我評估" }));
    await screen.findByText("你的錄音");
    expect(screen.getByText("87/100")).toBeInTheDocument();
    expect(screen.getByText(/gpt-6-luna/)).toBeInTheDocument();
    expect(screen.getByText("Keep the falling tone clear.")).toBeInTheDocument();
    expect(screen.getByText("Let the pitch dip gently.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "老師示範" })).toBeInTheDocument();
    expect(uploadRecording).toHaveBeenCalledWith(file);
    expect(onAddRecord).toHaveBeenCalledTimes(1);
    expect(onSceneSubmission).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ pronScore: 87 }));
  });

  it("keeps the submitted recording for replay after advancing the conversation", async () => {
    const submittedAudioUrl = "/uploads/audio/submitted-answer.wav";
    const startRecording = vi.fn().mockResolvedValueOnce(makeRecorderResult({ audioUrl: submittedAudioUrl }));
    vi.mocked(useSpeakingRecorder).mockReturnValue(recorderMock({ startRecording }));
    vi.mocked(analyzeSpeakingResult).mockReturnValueOnce(makeAnalysis({ accepted: true }));

    const constructedUrls: string[] = [];
    class AudioMock {
      duration = Number.NaN;
      play = vi.fn().mockResolvedValue(undefined);

      constructor(url: string) {
        constructedUrls.push(url);
      }

      addEventListener() {}
    }
    vi.stubGlobal("Audio", AudioMock);

    render(
      <ConversationPage
        topic={makeTopic()}
        turns={[
          ...turns,
          { id: "t2", speaker: "system", text: "星期六下午有空嗎？", audioUrl: "/uploads/audio/next-model.mp3" },
        ]}
        onAddRecord={vi.fn()}
        onSceneSubmission={vi.fn()}
        onDone={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "繼續" }));
    fireEvent.click(screen.getByRole("button", { name: "錄音" }));
    await screen.findByText("你覺得表現如何？");
    fireEvent.click(screen.getByRole("button", { name: "略過自我評估" }));
    await screen.findByText("你的錄音");
    fireEvent.click(screen.getByRole("button", { name: "下一頁" }));
    fireEvent.click(await screen.findByRole("button", { name: "重播回答" }));

    expect(constructedUrls).toEqual([submittedAudioUrl]);
    expect(constructedUrls).not.toContain("/uploads/audio/student-model.mp3");
  });

  it("Record again returns to the student recording step", async () => {
    const startRecording = vi.fn().mockResolvedValueOnce(makeRecorderResult());
    vi.mocked(useSpeakingRecorder).mockReturnValue(recorderMock({ startRecording }));
    vi.mocked(analyzeSpeakingResult).mockReturnValueOnce(makeAnalysis({ accepted: false }));

    render(
      <ConversationPage topic={makeTopic()} turns={turns} onAddRecord={vi.fn()} onSceneSubmission={vi.fn()} onDone={vi.fn()} onBack={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "繼續" }));
    fireEvent.click(screen.getByRole("button", { name: "錄音" }));
    await screen.findByText("你覺得表現如何？");
    fireEvent.click(screen.getByRole("button", { name: "略過自我評估" }));
    await screen.findByText("你的錄音");

    fireEvent.click(screen.getByRole("button", { name: "再錄一次" }));

    expect(screen.getByRole("button", { name: "錄音" })).toBeInTheDocument();
    expect(screen.queryByText("需要加強")).not.toBeInTheDocument();
  });

  it("does not label an unverified recorder result as verified", async () => {
    const startRecording = vi.fn().mockResolvedValueOnce(makeRecorderResult({ verified: false }));
    vi.mocked(useSpeakingRecorder).mockReturnValue(recorderMock({ startRecording }));
    vi.mocked(analyzeSpeakingResult).mockReturnValueOnce(makeAnalysis({ accepted: true }));

    render(
      <ConversationPage topic={makeTopic()} turns={turns} onAddRecord={vi.fn()} onSceneSubmission={vi.fn()} onDone={vi.fn()} onBack={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "繼續" }));
    fireEvent.click(screen.getByRole("button", { name: "錄音" }));
    await screen.findByText("你覺得表現如何？");
    fireEvent.click(screen.getByRole("button", { name: "略過自我評估" }));
    await screen.findByText("你的錄音");

    expect(screen.queryByText("錄音已確認")).not.toBeInTheDocument();
  });
});
