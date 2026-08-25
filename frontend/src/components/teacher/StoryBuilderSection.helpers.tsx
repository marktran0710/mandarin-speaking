// @ts-nocheck
import React from "react";
import type {
  CustomStoryFrame,
  CustomTeacherStory,
  StoryDifficultyLevel,
  StoryPhrasesByLevel,
  StoryVocabularyByLevel,
  VocabGroup,
} from "../../utils/teacherStories";
import { frameCountForMode } from "../../utils/myStoriesUtils";

export const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV && typeof window !== "undefined" ? window.location.origin : "");

// How many phrases to ask the AI for per difficulty tier — a harder tier's
// suggested-answer sentence is longer/more complex, so it naturally yields
// more reusable phrase-level chunks.
export const PHRASE_COUNT_BY_LEVEL: Record<StoryDifficultyLevel, number> = {
  easy: 1,
  medium: 2,
  hard: 3,
};

export interface CustomStoryValidationErrors {
  title?: string;
  form?: string;
  frames?: Record<number, { imageUrl?: string; prompt?: string }>;
}

export interface StoryFrameGuide {
  zh: string;
  en: string;
  tip: string;
  color: string;
  accent: string;
  renderIcon: () => React.ReactElement;
}

export const STORY_FRAME_GUIDES: StoryFrameGuide[] = [
  {
    zh: "開場 — 誰在哪裡？",
    en: "Scene 1 · Setting",
    tip: "Show the character(s) and location",
    color: "var(--jade)",
    accent: "var(--jade-soft)",
    renderIcon: () => (
      <g>
        <circle cx="72" cy="56" r="18" fill="var(--jade)" />
        <path d="M54 90 Q72 72 90 90 L90 108 L54 108 Z" fill="var(--jade)" opacity="0.8" />
        <path d="M128 38 C128 52 112 68 112 68 C112 68 96 52 96 38 C96 29 103 22 112 22 C121 22 128 29 128 38 Z" fill="var(--gold)" />
        <circle cx="112" cy="38" r="7" fill="white" />
      </g>
    ),
  },
  {
    zh: "第一個動作",
    en: "Scene 2 · First Action",
    tip: "What does the character do first?",
    color: "var(--seal)",
    accent: "var(--seal-soft)",
    renderIcon: () => (
      <g>
        <circle cx="88" cy="42" r="16" fill="var(--seal)" />
        <path d="M68 62 L88 58 L108 62" stroke="var(--seal)" strokeWidth="5" fill="none" strokeLinecap="round" />
        <path d="M72 62 L62 86 M78 62 L72 86" stroke="var(--seal)" strokeWidth="5" strokeLinecap="round" />
        <path d="M100 62 L108 82 M106 62 L116 80" stroke="var(--seal)" strokeWidth="5" strokeLinecap="round" />
        <path d="M52 70 L140 70" stroke="var(--seal)" strokeWidth="3" strokeDasharray="6 4" opacity="0.5" />
      </g>
    ),
  },
  {
    zh: "問題出現",
    en: "Scene 3 · Problem",
    tip: "A problem or surprise happens",
    color: "var(--gold)",
    accent: "var(--gold-soft)",
    renderIcon: () => (
      <g>
        <ellipse cx="88" cy="52" rx="34" ry="24" fill="var(--gold)" opacity="0.85" />
        <ellipse cx="68" cy="60" rx="22" ry="18" fill="var(--gold)" opacity="0.85" />
        <ellipse cx="108" cy="58" rx="26" ry="20" fill="var(--gold)" opacity="0.85" />
        <path d="M94 72 L80 96 L90 96 L80 114" stroke="var(--gold-deep)" strokeWidth="5" strokeLinecap="round" fill="none" />
      </g>
    ),
  },
  {
    zh: "尋求幫助",
    en: "Scene 4 · Asking for Help",
    tip: "Someone asks or offers to help",
    color: "var(--jade-deep)",
    accent: "var(--jade-soft)",
    renderIcon: () => (
      <g>
        <circle cx="62" cy="50" r="14" fill="var(--jade-deep)" />
        <path d="M48 72 Q62 60 76 72 L76 92 L48 92 Z" fill="var(--jade-deep)" opacity="0.8" />
        <circle cx="118" cy="50" r="14" fill="var(--jade-deep)" opacity="0.7" />
        <path d="M104 72 Q118 60 132 72 L132 92 L104 92 Z" fill="var(--jade-deep)" opacity="0.55" />
        <rect x="72" y="28" width="36" height="22" rx="6" fill="var(--gold)" />
        <polygon points="84,50 92,50 88,58" fill="var(--gold)" />
        <line x1="78" y1="36" x2="100" y2="36" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="78" y1="43" x2="94" y2="43" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
      </g>
    ),
  },
  {
    zh: "解決問題",
    en: "Scene 5 · Solution",
    tip: "Show how the problem gets solved",
    color: "var(--seal-deep)",
    accent: "var(--seal-soft)",
    renderIcon: () => (
      <g>
        <circle cx="88" cy="65" r="32" fill="var(--seal-deep)" opacity="0.15" />
        <circle cx="88" cy="65" r="26" fill="var(--seal-deep)" opacity="0.2" />
        <path d="M68 65 L82 79 L108 52" stroke="var(--seal-deep)" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <circle cx="118" cy="38" r="5" fill="var(--gold)" />
        <circle cx="60" cy="42" r="3" fill="var(--gold)" />
        <circle cx="126" cy="80" r="4" fill="var(--gold)" />
      </g>
    ),
  },
  {
    zh: "結尾感受",
    en: "Scene 6 · Ending Feeling",
    tip: "How does everyone feel at the end?",
    color: "var(--gold-deep)",
    accent: "var(--gold-soft)",
    renderIcon: () => (
      <g>
        <circle cx="88" cy="60" r="30" fill="var(--gold-deep)" opacity="0.15" />
        <circle cx="88" cy="60" r="24" fill="var(--gold-deep)" opacity="0.85" />
        <circle cx="80" cy="55" r="3.5" fill="white" />
        <circle cx="96" cy="55" r="3.5" fill="white" />
        <path d="M76 66 Q88 78 100 66" stroke="white" strokeWidth="3.5" strokeLinecap="round" fill="none" />
        <path d="M112 28 C112 24 116 22 118 26 C120 22 124 24 124 28 C124 34 118 38 118 38 C118 38 112 34 112 28 Z" fill="var(--gold-deep)" />
      </g>
    ),
  },
];

// Temporarily disabled 2026-07-07 at the user's request. The component,
// its data (vocabularyGroups), and this flag stay in place so it's a
// one-line flip to bring back.
export const GRAMMAR_CANVAS_ENABLED = false;

/** Fields that vary per difficulty tier — same scene/plot, just a
 * progressively more complex image/text. Each holds one array per tier, all
 * three kept the same length (see updateFrameCount). */
export type TieredDraftField =
  | "imageUrls"
  | "prompts"
  | "vocabulary"
  | "vocabularyPinyin"
  | "vocabularyPos"
  | "vocabularyTranslation"
  | "phrases"
  | "phrasesTranslation"
  | "suggestedAnswers"
  | "listenAudioUrls"
  | "listenAudioSources"
  | "listenScripts";

export function blankTiers(count: number): Record<StoryDifficultyLevel, string[]> {
  return {
    easy: new Array(count).fill(""),
    medium: new Array(count).fill(""),
    hard: new Array(count).fill(""),
  };
}

export function blankStoryVocabulary(): StoryVocabularyByLevel {
  const blank = () => ({
    vocabulary: "",
    vocabularyPinyin: "",
    vocabularyPos: "",
    vocabularyTranslation: "",
  });
  return { easy: blank(), medium: blank(), hard: blank() };
}

export function blankStoryPhrases(): StoryPhrasesByLevel {
  const blank = () => ({ phrases: "", phrasesTranslation: "" });
  return { easy: blank(), medium: blank(), hard: blank() };
}

export const emptyCustomStoryDraft = {
  title: "Taiwan Community Story",
  lessonNumber: "",
  lessonSubOrder: "",
  activeLevel: "easy" as StoryDifficultyLevel,
  storyVocabulary: blankStoryVocabulary(),
  storyPhrases: blankStoryPhrases(),
  imageUrls: blankTiers(6),
  prompts: {
    easy: [
      "Introduce the place and the people.",
      "Describe the first event.",
      "Explain the problem or surprise.",
      "Tell the result and feeling.",
      "Revise the story with one clearer detail.",
      "Finish with a lesson or next step.",
    ],
    medium: ["", "", "", "", "", ""],
    hard: ["", "", "", "", "", ""],
  },
  vocabulary: blankTiers(6),
  vocabularyPinyin: blankTiers(6),
  vocabularyPos: blankTiers(6),
  vocabularyTranslation: blankTiers(6),
  vocabularyDistractors: ["", "", "", "", "", ""],
  vocabularyGroups: [null, null, null, null, null, null] as (VocabGroup[] | null)[],
  phrases: blankTiers(6),
  phrasesTranslation: blankTiers(6),
  suggestedAnswers: blankTiers(6),
  listenAudioUrls: blankTiers(6),
  listenAudioSources: blankTiers(6),
  listenScripts: blankTiers(6),
};

export function validateCustomStoryDraft(
  draft: typeof emptyCustomStoryDraft,
  existingStories: CustomTeacherStory[],
  editingStoryId: string | null,
): CustomStoryValidationErrors {
  const errors: CustomStoryValidationErrors = {};
  const frameErrors: CustomStoryValidationErrors["frames"] = {};

  if (!draft.title.trim()) {
    errors.title = "Add a story title for students.";
  }

  draft.imageUrls.easy.forEach((imageUrl, index) => {
    const imageMissing = !imageUrl.trim();

    if (imageMissing) {
      frameErrors[index] = {
        imageUrl: `Frame ${index + 1} needs an image URL or uploaded image.`,
      };
    }
  });

  if (Object.keys(frameErrors).length > 0) {
    errors.frames = frameErrors;
  }

  // Two stories in the same lesson can't claim the same position — the
  // in-lesson unlock (5-1 -> 5-2) needs a single well-defined order.
  const lessonNumber = draft.lessonNumber.trim() ? Number(draft.lessonNumber) : null;
  const lessonSubOrder = draft.lessonSubOrder.trim() ? Number(draft.lessonSubOrder) : null;
  if (lessonNumber != null && lessonSubOrder != null) {
    const clash = existingStories.some(
      (story) =>
        story.id !== editingStoryId &&
        story.lessonNumber === lessonNumber &&
        story.lessonSubOrder === lessonSubOrder,
    );
    if (clash) {
      errors.form = `Another story is already Lesson ${lessonNumber}-${lessonSubOrder}. Pick a different story order.`;
    }
  }

  return errors;
}
