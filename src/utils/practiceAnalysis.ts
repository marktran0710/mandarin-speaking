/** Shared multipart contract for the student speaking flow and teacher debug.
 * Keeping this builder in one place makes a debug recording replay the same
 * scene-aware request the learner sends, including optional model-voice curves.
 */
export interface PracticeAnalysisRequestContext {
  transcription?: string;
  asrModel?: string;
  aiProvider?: string;
  sceneVocabulary?: string;
  scenePrompt?: string;
  sceneImageUrl?: string;
  scenePhrases?: string;
  sceneSuggestedAnswer?: string;
  sceneAttemptNumber?: number;
  sceneReferenceCurves?: Record<string, number[]> | null;
  verifyWord?: string;
  pinyinHint?: string;
  analysisDetail?: string;
}

export function buildPracticeAnalysisFormData(
  audio: Blob,
  context: PracticeAnalysisRequestContext = {},
): FormData {
  const formData = new FormData();
  formData.append("file", audio, "speech.wav");
  formData.append("transcription", context.transcription?.trim() ?? "");

  const appendIfPresent = (key: string, value: string | undefined) => {
    if (value?.trim()) formData.append(key, value.trim());
  };

  appendIfPresent("asr_model", context.asrModel);
  appendIfPresent("ai_provider", context.aiProvider);
  appendIfPresent("scene_vocabulary", context.sceneVocabulary);
  appendIfPresent("scene_prompt", context.scenePrompt);
  appendIfPresent("scene_image_url", context.sceneImageUrl);
  appendIfPresent("scene_phrases", context.scenePhrases);
  appendIfPresent("scene_suggested_answer", context.sceneSuggestedAnswer);
  appendIfPresent("verify_word", context.verifyWord);
  appendIfPresent("pinyin_hint", context.pinyinHint);
  appendIfPresent("alignment_detail", context.analysisDetail);

  if (context.sceneAttemptNumber !== undefined) {
    formData.append("scene_attempt_number", String(context.sceneAttemptNumber));
  }
  if (context.sceneReferenceCurves && Object.keys(context.sceneReferenceCurves).length > 0) {
    formData.append("scene_reference_curves", JSON.stringify(context.sceneReferenceCurves));
  }

  return formData;
}
