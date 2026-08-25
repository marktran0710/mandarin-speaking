// @ts-nocheck
import type { CustomStoryFrame, CustomTeacherStory, StoryDifficultyLevel } from "../../utils/teacherStories";
import { emptyCustomStoryDraft } from "./StoryBuilderSection.helpers";

const TIER_BACKEND_FIELD: Record<
  TieredDraftField,
  { easy: keyof CustomStoryFrame; medium: keyof CustomStoryFrame; hard: keyof CustomStoryFrame }
> = {
  imageUrls: { easy: "imageUrl", medium: "imageUrlMedium", hard: "imageUrlHard" },
  prompts: { easy: "prompt", medium: "promptMedium", hard: "promptHard" },
  vocabulary: { easy: "vocabulary", medium: "vocabularyMedium", hard: "vocabularyHard" },
  vocabularyPinyin: {
    easy: "vocabularyPinyin",
    medium: "vocabularyPinyinMedium",
    hard: "vocabularyPinyinHard",
  },
  vocabularyPos: { easy: "vocabularyPos", medium: "vocabularyPosMedium", hard: "vocabularyPosHard" },
  vocabularyTranslation: {
    easy: "vocabularyTranslation",
    medium: "vocabularyTranslationMedium",
    hard: "vocabularyTranslationHard",
  },
  phrases: { easy: "phrases", medium: "phrasesMedium", hard: "phrasesHard" },
  phrasesTranslation: {
    easy: "phrasesTranslation",
    medium: "phrasesTranslationMedium",
    hard: "phrasesTranslationHard",
  },
  suggestedAnswers: {
    easy: "suggestedAnswer",
    medium: "suggestedAnswerMedium",
    hard: "suggestedAnswerHard",
  },
  listenAudioUrls: {
    easy: "listenAudioUrl",
    medium: "listenAudioUrlMedium",
    hard: "listenAudioUrlHard",
  },
  listenAudioSources: {
    easy: "listenAudioSource",
    medium: "listenAudioSourceMedium",
    hard: "listenAudioSourceHard",
  },
  listenScripts: { easy: "listenScript", medium: "listenScriptMedium", hard: "listenScriptHard" },
};

const TIERED_DRAFT_FIELDS: TieredDraftField[] = [
  "imageUrls",
  "prompts",
  "vocabulary",
  "vocabularyPinyin",
  "vocabularyPos",
  "vocabularyTranslation",
  "phrases",
  "phrasesTranslation",
  "suggestedAnswers",
  "listenAudioUrls",
  "listenAudioSources",
  "listenScripts",
];

export function createCustomStory(
  draft: typeof emptyCustomStoryDraft,
  existingId?: string | null,
): CustomTeacherStory {
  return {
    id: existingId || `custom-story-${Date.now()}`,
    title: draft.title.trim() || "Untitled teacher story",
    frames: draft.imageUrls.easy.map((imageUrl, index) => {
      const frame: CustomStoryFrame = {
        imageUrl: imageUrl.trim(),
        prompt: draft.prompts.easy[index].trim(),
        vocabulary: draft.vocabulary.easy[index].trim(),
      };
      if (draft.vocabularyGroups[index]) {
        frame.vocabularyGroups = draft.vocabularyGroups[index]!;
      }
      if (draft.vocabularyDistractors[index]?.trim()) {
        frame.vocabularyDistractors = draft.vocabularyDistractors[index].trim();
      }
      TIERED_DRAFT_FIELDS.forEach((field) => {
        (["medium", "hard"] as const).forEach((level) => {
          const value = draft[field][level][index]?.trim();
          if (value) {
            (frame as any)[TIER_BACKEND_FIELD[field][level]] = value;
          }
        });
      });
      // Easy's optional fields (beyond prompt/vocabulary, always present)
      if (draft.phrases.easy[index]?.trim()) frame.phrases = draft.phrases.easy[index].trim();
      if (draft.phrasesTranslation.easy[index]?.trim())
        frame.phrasesTranslation = draft.phrasesTranslation.easy[index].trim();
      if (draft.vocabularyPinyin.easy[index]?.trim())
        frame.vocabularyPinyin = draft.vocabularyPinyin.easy[index].trim();
      if (draft.vocabularyPos.easy[index]?.trim())
        frame.vocabularyPos = draft.vocabularyPos.easy[index].trim();
      if (draft.vocabularyTranslation.easy[index]?.trim())
        frame.vocabularyTranslation = draft.vocabularyTranslation.easy[index].trim();
      if (draft.suggestedAnswers.easy[index]?.trim())
        frame.suggestedAnswer = draft.suggestedAnswers.easy[index].trim();
      if (draft.listenAudioUrls.easy[index]?.trim())
        frame.listenAudioUrl = draft.listenAudioUrls.easy[index].trim();
      if (draft.listenAudioSources.easy[index]?.trim())
        frame.listenAudioSource = draft.listenAudioSources.easy[index] as "teacher" | "tts";
      if (draft.listenScripts.easy[index]?.trim())
        frame.listenScript = draft.listenScripts.easy[index].trim();
      return frame;
    }),
    ...(draft.lessonNumber.trim() ? { lessonNumber: Number(draft.lessonNumber) } : {}),
    ...(draft.lessonSubOrder.trim() ? { lessonSubOrder: Number(draft.lessonSubOrder) } : {}),
  };
}

export function storyToDraft(story: CustomTeacherStory): typeof emptyCustomStoryDraft {
  // Preserve the story's actual saved frame count — it may have been
  // changed away from the mode's default via "Number of frames" — and only
  // fall back to the mode default if the story somehow has no frames at all.
  const frameCount = story.frames.length || 6;
  const frames = Array.from({ length: frameCount }, (_, index) => story.frames[index]);

  const tiersFor = (field: TieredDraftField): Record<StoryDifficultyLevel, string[]> => {
    const backendFields = TIER_BACKEND_FIELD[field];
    return {
      easy: frames.map((frame, index) => {
        const value = frame?.[backendFields.easy] as string | undefined;
        // The default prompt list only covers the 6 stock scenes, so a story
        // saved with more frames than that has no default to fall back on —
        // every tier array still has to come out as strings, not holes.
        const fallback =
          field === "prompts" ? emptyCustomStoryDraft.prompts.easy[index] ?? "" : "";
        return value || fallback;
      }),
      medium: frames.map((frame) => (frame?.[backendFields.medium] as string | undefined) || ""),
      hard: frames.map((frame) => (frame?.[backendFields.hard] as string | undefined) || ""),
    };
  };

  return {
    title: story.title,
    lessonNumber: story.lessonNumber != null ? String(story.lessonNumber) : "",
    lessonSubOrder: story.lessonSubOrder != null ? String(story.lessonSubOrder) : "",
    activeLevel: "easy",
    imageUrls: tiersFor("imageUrls"),
    prompts: tiersFor("prompts"),
    vocabulary: tiersFor("vocabulary"),
    vocabularyGroups: frames.map((frame) => frame?.vocabularyGroups || null),
    phrases: tiersFor("phrases"),
    phrasesTranslation: tiersFor("phrasesTranslation"),
    vocabularyPinyin: tiersFor("vocabularyPinyin"),
    vocabularyPos: tiersFor("vocabularyPos"),
    vocabularyTranslation: tiersFor("vocabularyTranslation"),
    vocabularyDistractors: frames.map((frame) => frame?.vocabularyDistractors || ""),
    suggestedAnswers: tiersFor("suggestedAnswers"),
    listenAudioUrls: tiersFor("listenAudioUrls"),
    listenAudioSources: tiersFor("listenAudioSources"),
    listenScripts: tiersFor("listenScripts"),
  };
}
