export interface VocabGroup {
  name: string;
  words: string[];
}

export interface CustomStoryFrame {
  imageUrl: string;
  prompt: string;
  vocabulary: string;
  vocabularyGroups?: VocabGroup[];
  // Handy, easy-to-learn-and-reuse phrases for this scene (replaces the old
  // single whole-story "grammar pattern" note), comma-joined per scene —
  // same convention as vocabulary/vocabularyTranslation below.
  phrases?: string;
  phrasesTranslation?: string;
  vocabularyPinyin?: string;
  vocabularyPos?: string;
  vocabularyTranslation?: string;
  // JSON-encoded array of arrays (one entry per word, aligned with the
  // comma-split `vocabulary` above) — distractors are inherently multi-valued
  // per word, unlike the other comma-joined single-value fields.
  vocabularyDistractors?: string;
  // JSON-encoded array of arrays (one entry per word, aligned with the
  // comma-split `vocabulary` above) — each word's entry is a list of
  // AI-generated {sentence, distractors} cloze candidates, grown the same
  // way vocabularyDistractors is.
  vocabularyCloze?: string;
  // JSON-encoded array of arrays (one entry per word) — each word's entry
  // is a list of AI-generated {synonym, distractors} candidates, grown the
  // same way vocabularyCloze is.
  vocabularySynonym?: string;
  suggestedAnswer?: string;
  listenAudioUrl?: string;
  listenAudioSource?: "teacher" | "tts";
  listenScript?: string;
  // Model-voice reference audio, one per word in this tier's own vocabulary
  // list (unlike vocabularyDistractors/Cloze/Synonym above, these
  // ARE tiered — see storyToTopic). JSON-encoded array of URLs (a null entry
  // means that word's clip couldn't be sliced) and, in parallel, an array of
  // 100-point [0,1] pitch-shape curves the scoring engine sends back to the
  // backend as a real-voice comparison target — see reference_voice.py.
  vocabularyAudioUrls?: string;
  vocabularyReferenceCurves?: string;
  sentenceReferenceCurves?: string;
  // Medium/Hard tiers of the same scene — progressively more complex text,
  // and optionally their own image. Absent means that tier hasn't been
  // authored yet.
  imageUrlMedium?: string;
  imageUrlHard?: string;
  promptMedium?: string;
  promptHard?: string;
  vocabularyMedium?: string;
  vocabularyHard?: string;
  vocabularyPinyinMedium?: string;
  vocabularyPinyinHard?: string;
  vocabularyPosMedium?: string;
  vocabularyPosHard?: string;
  vocabularyTranslationMedium?: string;
  vocabularyTranslationHard?: string;
  phrasesMedium?: string;
  phrasesHard?: string;
  phrasesTranslationMedium?: string;
  phrasesTranslationHard?: string;
  suggestedAnswerMedium?: string;
  suggestedAnswerHard?: string;
  listenAudioUrlMedium?: string;
  listenAudioUrlHard?: string;
  listenAudioSourceMedium?: "teacher" | "tts";
  listenAudioSourceHard?: "teacher" | "tts";
  listenScriptMedium?: string;
  listenScriptHard?: string;
  vocabularyAudioUrlsMedium?: string;
  vocabularyAudioUrlsHard?: string;
  vocabularyReferenceCurvesMedium?: string;
  vocabularyReferenceCurvesHard?: string;
  sentenceReferenceCurvesMedium?: string;
  sentenceReferenceCurvesHard?: string;
}

export interface CustomTeacherStory {
  id: string;
  title: string;
  frames: CustomStoryFrame[];
  published?: boolean;
  lessonNumber?: number | null;
  /** Position within its lesson (1, 2, 3...) for the in-lesson sequential
   * unlock (5-1 -> 5-2 -> 5-3). Only meaningful alongside lessonNumber; a
   * lesson with any story missing this leaves the whole lesson unordered
   * (see groupTopicsByLesson). */
  lessonSubOrder?: number | null;
  rubricScores?: Record<string, unknown> | null;
  /** Teacher quiz review's diff baseline, keyed by tier — see
   * utils/quizMaterialDiff.ts. Opaque here to avoid a dependency cycle
   * (quizMaterialDiff already imports StoryDifficultyLevel from this file). */
  quizMaterialSnapshot?: Record<string, unknown>;
  /** Teacher-approved AI quiz material, keyed by tier — see
   * utils/quizApprovedMaterial.ts. What storyToTopic(story, level,
   * "approved") actually serves students. */
  quizApprovedSnapshot?: Record<string, unknown>;
  /** Quiz Review's in-progress checkbox selections, keyed by tier — see
   * utils/quizPendingApprovals.ts. Not yet published; survives a reload. */
  quizPendingApprovals?: Record<string, unknown>;
}

export type StoryDifficultyLevel = "easy" | "medium" | "hard";

