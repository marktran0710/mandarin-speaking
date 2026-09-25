import type { SpeechModel } from "../../components/story-recorder/StoryRecorder";

export function normalizeSpeechModel(model?: string): SpeechModel {
  const candidate = model?.toLowerCase().replace(/^auto:/, "").split(":")[0];
  if (candidate === "ctwhisper" || candidate === "groq" || candidate === "vibevoice" || candidate === "openai" || candidate === "webspeech") {
    return candidate;
  }
  return "webspeech";
}

