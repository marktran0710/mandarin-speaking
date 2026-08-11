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
  /** Authoritative full-sentence target used to verify an ASR transcript for
   * whole-sentence practice. This is intentionally separate from
   * `transcription`, which may be empty for an uploaded file. */
  sceneTargetText?: string;
  sceneAttemptNumber?: number;
  sceneReferenceCurves?: Record<string, number[]> | null;
  verifyWord?: string;
  pinyinHint?: string;
  analysisDetail?: string;
  /** STEPs 2-6 of the pre-pilot research-logging plumbing -- all optional,
   * all additive (the backend already defaults every one of these to
   * absent/`""`, unchanged legacy behavior when they're not sent). See
   * `benchmarking/results/pilot_readiness.md`. Reuses EXISTING identifiers
   * (`students.id`, the `(topic.id, sceneIndex)` composite item key) rather
   * than inventing new ones -- only `sessionId`/`studyPhase` are genuinely
   * new concepts (see `src/utils/pilotSession.ts`). */
  participantId?: string;
  itemId?: string;
  sessionId?: string;
  attemptId?: string;
  attemptNumber?: number;
  attemptType?: "WHOLE_SENTENCE_INITIAL" | "FOCUSED_RETRY" | "WHOLE_SENTENCE_FINAL";
  studyPhase?: "" | "pilot";
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
  appendIfPresent("scene_target_text", context.sceneTargetText);
  appendIfPresent("verify_word", context.verifyWord);
  appendIfPresent("pinyin_hint", context.pinyinHint);
  appendIfPresent("alignment_detail", context.analysisDetail);

  if (context.sceneAttemptNumber !== undefined) {
    formData.append("scene_attempt_number", String(context.sceneAttemptNumber));
  }
  if (context.sceneReferenceCurves && Object.keys(context.sceneReferenceCurves).length > 0) {
    formData.append("scene_reference_curves", JSON.stringify(context.sceneReferenceCurves));
  }

  appendIfPresent("participant_id", context.participantId);
  appendIfPresent("item_id", context.itemId);
  appendIfPresent("session_id", context.sessionId);
  appendIfPresent("attempt_id", context.attemptId);
  appendIfPresent("attempt_type", context.attemptType);
  appendIfPresent("study_phase", context.studyPhase);
  if (context.attemptNumber !== undefined) {
    formData.append("attempt_number", String(context.attemptNumber));
  }

  return formData;
}
