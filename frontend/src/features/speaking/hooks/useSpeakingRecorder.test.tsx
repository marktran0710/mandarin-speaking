import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSpeakingRecorder } from "./useSpeakingRecorder";
import { postSpeechAnalysis } from "@shared/api/speech-analysis";

vi.mock("@entities/audio", () => ({ convertBlobToWav: vi.fn(async (audio: Blob) => audio) }));
vi.mock("@shared/api/speech-analysis", () => ({ postSpeechAnalysis: vi.fn() }));
vi.mock("../../../utils/studentSession", () => ({ getStudentId: () => "student-1" }));

const evaluation = { score: { total: 86 }, model: { feedback_model: "gpt-6-luna" } };

beforeEach(() => { vi.mocked(postSpeechAnalysis).mockReset(); });

describe("GPT speaking recorder", () => {
  it.each([false, true])("requests strict feedback for conversation=%s", async (conversation) => {
    vi.mocked(postSpeechAnalysis).mockResolvedValue({
      analysis: { pronunciation_evaluation: evaluation }, progressionEligible: true,
    });
    const { result } = renderHook(() => useSpeakingRecorder(() => ({
      baseStoryId: "story-1", sceneIndex: 2,
      ...(conversation ? { conversationId: "conv-1", turnId: "turn-1", turnIndex: 3 } : {}),
    })));
    await act(async () => {
      const response = await result.current.uploadRecording(new File(["audio"], "sample.wav", { type: "audio/wav" }));
      expect(response?.metrics.pronunciation_evaluation).toEqual(evaluation);
    });
    const [form, verified] = vi.mocked(postSpeechAnalysis).mock.calls[0];
    expect(verified).toBe(true);
    expect(form.get("pronunciation_feedback")).toBe("true");
    expect(form.get("base_story_id")).toBe("story-1");
    expect(form.get("scene_index")).toBe("2");
    if (conversation) {
      expect(form.get("turn_id")).toBe("turn-1");
      expect(form.get("turn_index")).toBe("3");
    }
  });

  it("reports model errors without accepting an old result", async () => {
    vi.mocked(postSpeechAnalysis).mockRejectedValue(new Error("GPT failed (llm_http_401)"));
    const { result } = renderHook(() => useSpeakingRecorder(() => ({ baseStoryId: "story-1", sceneIndex: 0 })));
    await act(async () => {
      expect(await result.current.uploadRecording(new File(["audio"], "sample.wav", { type: "audio/wav" }))).toBeNull();
    });
    expect(result.current.error).toContain("llm_http_401");
    expect(result.current.attemptNumber).toBe(0);
    expect(result.current.isAnalyzing).toBe(false);
  });

  it("rejects a response from an outdated backend", async () => {
    vi.mocked(postSpeechAnalysis).mockResolvedValue({ analysis: { feedback: "Old local feedback" } });
    const { result } = renderHook(() => useSpeakingRecorder(() => ({ baseStoryId: "story-1", sceneIndex: 0 })));
    await act(async () => {
      expect(await result.current.uploadRecording(new File(["audio"], "sample.wav", { type: "audio/wav" }))).toBeNull();
    });
    expect(result.current.error).toContain("Restart the backend");
  });
});
