import { describe, expect, it } from "vitest";
import { buildPracticeAnalysisFormData } from "./practiceAnalysis";

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
});
