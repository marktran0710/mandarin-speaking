// @ts-nocheck
import type {
  CustomStoryFrame,
  CustomTeacherStory,
  StoryDifficultyLevel,
  StoryPhrasesByLevel,
  StoryVocabularyByLevel,
} from "../../utils/teacherStories";
import type { ConversationTurn } from "../story-recorder/StoryRecorder/conversation";
import { buildPhraseRows, buildVocabRows } from "../../utils/myStoriesUtils";
import {
  blankStoryPhrases,
  blankStoryVocabulary,
  emptyCustomStoryDraft,
  type ConversationExchangeDraft,
} from "./StoryBuilderSection.helpers";

/** Epic 3: one exchange draft -> one system turn + one student turn. Skips
 * an exchange with no content at all (a freshly-added blank row that was
 * never filled in), so an untouched "+ Add exchange" click doesn't block
 * saving via validateCustomStoryDraft's completeness check. */
export function exchangesToConversationTurns(
  exchanges: ConversationExchangeDraft[],
): ConversationTurn[] | undefined {
  const meaningful = exchanges.filter(
    (exchange) => exchange.characterText.trim() || exchange.studentText.trim(),
  );
  if (meaningful.length === 0) return undefined;

  const turns: ConversationTurn[] = [];
  meaningful.forEach((exchange) => {
    turns.push({
      id: `system-${exchange.id}`,
      speaker: "system",
      text: exchange.characterText.trim(),
      ...(exchange.characterPinyin.trim() ? { pinyin: exchange.characterPinyin.trim() } : {}),
      ...(exchange.characterTranslation.trim() ? { translation: exchange.characterTranslation.trim() } : {}),
      ...(exchange.characterAudioUrl.trim() ? { audioUrl: exchange.characterAudioUrl.trim() } : {}),
    });
    turns.push({
      id: `student-${exchange.id}`,
      speaker: "student",
      text: exchange.studentText.trim(),
      targetText: exchange.studentText.trim(),
      ...(exchange.studentPinyin.trim() ? { pinyin: exchange.studentPinyin.trim() } : {}),
      ...(exchange.studentTranslation.trim() ? { translation: exchange.studentTranslation.trim() } : {}),
      ...(exchange.studentModelAudioUrl.trim() ? { targetAudioUrl: exchange.studentModelAudioUrl.trim() } : {}),
    });
  });
  return turns;
}

/** The inverse, for loading an existing story back into the builder.
 * Pairs turns positionally (system, student, system, student, ...) rather
 * than trusting id prefixes, so it tolerates turns authored outside the
 * builder too. An unpaired trailing turn (malformed data) is dropped. */
export function conversationTurnsToExchanges(
  turns: ConversationTurn[] | undefined,
): ConversationExchangeDraft[] {
  if (!turns || turns.length === 0) return [];
  const exchanges: ConversationExchangeDraft[] = [];
  for (let index = 0; index + 1 < turns.length; index += 2) {
    const system = turns[index];
    const student = turns[index + 1];
    exchanges.push({
      id: system.id.replace(/^system-/, "") || `exchange-${index / 2 + 1}`,
      characterText: system.text || "",
      characterPinyin: system.pinyin || "",
      characterTranslation: system.translation || "",
      characterAudioUrl: system.audioUrl || "",
      studentText: student.targetText || student.text || "",
      studentPinyin: student.pinyin || "",
      studentTranslation: student.translation || "",
      studentModelAudioUrl: student.targetAudioUrl || "",
    });
  }
  return exchanges;
}

const TIER_BACKEND_FIELD: Record<TieredDraftField, { easy: keyof CustomStoryFrame }> = {
  imageUrls: { easy: "imageUrl" },
  prompts: { easy: "prompt" },
  vocabulary: { easy: "vocabulary" },
  vocabularyPinyin: { easy: "vocabularyPinyin" },
  vocabularyPos: { easy: "vocabularyPos" },
  vocabularyTranslation: { easy: "vocabularyTranslation" },
  phrases: { easy: "phrases" },
  phrasesTranslation: { easy: "phrasesTranslation" },
  suggestedAnswers: { easy: "suggestedAnswer" },
  listenAudioUrls: { easy: "listenAudioUrl" },
  listenAudioSources: { easy: "listenAudioSource" },
  listenScripts: { easy: "listenScript" },
};

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
      // Optional fields (beyond prompt/vocabulary, always present)
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
    storyVocabulary: draft.storyVocabulary,
    storyPhrases: draft.storyPhrases,
    ...(draft.lessonNumber.trim() ? { lessonNumber: Number(draft.lessonNumber) } : {}),
    ...(draft.lessonSubOrder.trim() ? { lessonSubOrder: Number(draft.lessonSubOrder) } : {}),
    // Disabling the toggle and saving intentionally clears conversationTurns
    // (undefined here -> the request omits the field -> the backend writes
    // NULL) rather than leaving stale exchanges a teacher just turned off.
    conversationTurns: draft.conversationEnabled
      ? exchangesToConversationTurns(draft.conversationExchanges)
      : undefined,
  };
}

export function storyToDraft(story: CustomTeacherStory): typeof emptyCustomStoryDraft {
  // Preserve the story's actual saved frame count — it may have been
  // changed away from the mode's default via "Number of frames" — and only
  // fall back to the mode default if the story somehow has no frames at all.
  const frameCount = story.frames.length || 6;
  const frames = Array.from({ length: frameCount }, (_, index) => story.frames[index]);

  const aggregateVocabulary = (): StoryVocabularyByLevel => {
    const result = blankStoryVocabulary();
    (['easy'] as const).forEach((level) => {
      const seen = new Set<string>();
      const rows = frames.flatMap((frame) => {
        return buildVocabRows(
          frame?.vocabulary || '',
          frame?.vocabularyPinyin || '',
          frame?.vocabularyPos || '',
          frame?.vocabularyTranslation || '',
        );
      }).filter((row) => {
        const key = row.word.trim();
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      result[level] = {
        vocabulary: rows.map((row) => row.word).join(', '),
        vocabularyPinyin: rows.map((row) => row.pinyin).join(', '),
        vocabularyPos: rows.map((row) => row.pos).join(', '),
        vocabularyTranslation: rows.map((row) => row.translation).join(', '),
      };
    });
    return result;
  };

  const aggregatePhrases = (): StoryPhrasesByLevel => {
    const result = blankStoryPhrases();
    (['easy'] as const).forEach((level) => {
      const seen = new Set<string>();
      const rows = frames.flatMap((frame) => {
        return buildPhraseRows(
          frame?.phrases || '',
          frame?.phrasesTranslation || '',
        );
      }).filter((row) => {
        const key = row.phrase.trim();
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      result[level] = {
        phrases: rows.map((row) => row.phrase).join(', '),
        phrasesTranslation: rows.map((row) => row.translation).join(', '),
      };
    });
    return result;
  };

  const aggregatedVocabulary = aggregateVocabulary();
  const storyVocabulary = story.storyVocabulary
    ? (Object.fromEntries(
        (['easy'] as const).map((level) => [
          level,
          { ...aggregatedVocabulary[level], ...(story.storyVocabulary?.[level] || {}) },
        ]),
      ) as StoryVocabularyByLevel)
    : aggregatedVocabulary;
  const aggregatedPhrases = aggregatePhrases();
  const storyPhrases = story.storyPhrases
    ? (Object.fromEntries(
        (['easy'] as const).map((level) => [
          level,
          { ...aggregatedPhrases[level], ...(story.storyPhrases?.[level] || {}) },
        ]),
      ) as StoryPhrasesByLevel)
    : aggregatedPhrases;

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
    };
  };

  return {
    title: story.title,
    lessonNumber: story.lessonNumber != null ? String(story.lessonNumber) : "",
    lessonSubOrder: story.lessonSubOrder != null ? String(story.lessonSubOrder) : "",
    activeLevel: "easy",
    storyVocabulary,
    storyPhrases,
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
    conversationEnabled: Boolean(story.conversationTurns?.length),
    conversationExchanges: conversationTurnsToExchanges(story.conversationTurns),
  };
}
