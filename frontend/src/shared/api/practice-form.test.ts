import { describe, expect, it } from "vitest";
import { buildPracticeAnalysisFormData } from "./practice-form";

describe("buildPracticeAnalysisFormData", () => {
  it("sends the authoritative scene target separately from the transcript", () => {
    const form = buildPracticeAnalysisFormData(new Blob(["audio"]), {
      transcription: "",
      asrModel: "groq",
      sceneSuggestedAnswer: "友美，妳這個週末要做什麼？",
      sceneTargetText: "友美，妳這個週末要做什麼？",
    });

    expect(form.get("transcription")).toBe("");
    expect(form.get("asr_model")).toBe("groq");
    expect(form.get("scene_target_text")).toBe("友美，妳這個週末要做什麼？");
  });

  it("carries conversation turn identity through the multipart request", () => {
    const form = buildPracticeAnalysisFormData(new Blob(["audio"]), {
      conversationId: "conversation:story-1",
      turnId: "student-2",
      turnIndex: 3,
    });

    expect(form.get("conversation_id")).toBe("conversation:story-1");
    expect(form.get("turn_id")).toBe("student-2");
    expect(form.get("turn_index")).toBe("3");
  });
});
