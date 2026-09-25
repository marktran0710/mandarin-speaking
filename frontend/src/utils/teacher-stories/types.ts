export interface VocabGroup {
  name: string;
  words: string[];
}

import type { VocabAssessmentQuestion } from "../../components/story-vocab-quiz/model";
import type { ConversationTurn } from "../../components/story-recorder/StoryRecorder/conversation";

// Stories run one vocabulary set plus three canonical assessment rounds.
export type StoryDifficultyLevel = "easy";

/** Learning content shared by every scene in a story tier. */
export interface StoryVocabulary {
  vocabulary: string;
  vocabularyPinyin: string;
  vocabularyPos: string;
  vocabularyTranslation: string;
}

export interface StoryPhrases {
  phrases: string;
  phrasesTranslation: string;
}

export type StoryVocabularyByLevel = Record<StoryDifficultyLevel, StoryVocabulary>;
export type StoryPhrasesByLevel = Record<StoryDifficultyLevel, StoryPhrases>;

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
  suggestedAnswer?: string;
  listenAudioUrl?: string;
  listenAudioSource?: "teacher";
  listenScript?: string;
  // Model-voice reference audio, one per word in this tier's own vocabulary
  // list, these
  // ARE tiered — see storyToTopic). JSON-encoded array of URLs (a null entry
  // means that word's clip couldn't be sliced) and, in parallel, an array of
  // 100-point [0,1] pitch-shape curves the scoring engine sends back to the
  // backend as a real-voice comparison target — see reference_voice.py.
  vocabularyAudioUrls?: string;
  vocabularyReferenceCurves?: string;
  sentenceReferenceCurves?: string;
}

export interface CustomTeacherStory {
  id: string;
  title: string;
  frames: CustomStoryFrame[];
  /** Optional alternating system/student dialogue. Legacy stories omit it. */
  conversationTurns?: ConversationTurn[];
  /** Canonical story-wide vocabulary, keyed by difficulty tier. */
  storyVocabulary?: StoryVocabularyByLevel;
  /** Canonical story-wide reusable phrases, keyed by difficulty tier. */
  storyPhrases?: StoryPhrasesByLevel;
  published?: boolean;
  lessonNumber?: number | null;
  /** Position within its lesson (1, 2, 3...) for the in-lesson sequential
   * unlock (5-1 -> 5-2 -> 5-3). Only meaningful alongside lessonNumber; a
   * lesson with any story missing this leaves the whole lesson unordered
   * (see groupTopicsByLesson). */
  lessonSubOrder?: number | null;
  rubricScores?: Record<string, unknown> | null;
  vocabAssessment?: VocabAssessmentQuestion[];
}
