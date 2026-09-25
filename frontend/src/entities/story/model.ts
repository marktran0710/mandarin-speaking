import type { Topic } from "@entities/topic";
import { numericToToneMarked } from "../../utils/pinyin";
import { resolveImageUrl, splitCsvField, tierText, TIER_SUFFIX } from "./storyText";
import type { CustomStoryFrame, CustomTeacherStory, StoryDifficultyLevel, VocabGroup } from "./types";

/** Map a stored teacher story to the runtime topic shape.
 *
 * Vocabulary metadata is used for speaking presentation. Quiz questions come
 * exclusively from story.vocabAssessment and are intentionally not rebuilt
 * from frame fields here.
 */
export function storyToTopic(
  story: CustomTeacherStory,
  difficultyLevel: StoryDifficultyLevel = "easy",
): Topic {
  const vocabulary: Record<number, string[]> = {};
  const vocabularyGroups: Record<number, VocabGroup[]> = {};
  const phrases: Record<number, string[]> = {};
  const phrasesTranslation: Record<number, string[]> = {};
  const vocabularyPinyin: Record<number, string[]> = {};
  const vocabularyPos: Record<number, string[]> = {};
  const vocabularyTranslation: Record<number, string[]> = {};
  const suggestedAnswers: Record<number, string> = {};
  const listenAudioUrls: Record<number, string> = {};
  const listenAudioSources: Record<number, "teacher"> = {};
  const listenScripts: Record<number, string> = {};
  const vocabularyAudioUrls: Record<number, (string | null)[]> = {};
  const vocabularyReferenceCurves: Record<number, number[][]> = {};
  const sentenceReferenceCurves: Record<number, Record<string, number[]>> = {};

  story.frames.forEach((frame, index) => {
    const words = splitCsvField(tierText(frame, "vocabulary", difficultyLevel));
    vocabulary[index] = words;
    if (frame.vocabularyGroups?.length) vocabularyGroups[index] = frame.vocabularyGroups;

    const framePhrases = splitCsvField(tierText(frame, "phrases", difficultyLevel));
    if (framePhrases.length) phrases[index] = framePhrases;
    const framePhraseTranslations = splitCsvField(tierText(frame, "phrasesTranslation", difficultyLevel));
    if (framePhraseTranslations.length) phrasesTranslation[index] = framePhraseTranslations;

    const pinyin = splitCsvField(tierText(frame, "vocabularyPinyin", difficultyLevel)).map(numericToToneMarked);
    if (pinyin.length) vocabularyPinyin[index] = pinyin;
    const pos = splitCsvField(tierText(frame, "vocabularyPos", difficultyLevel));
    if (pos.length) vocabularyPos[index] = pos;
    const translations = splitCsvField(tierText(frame, "vocabularyTranslation", difficultyLevel));
    if (translations.length) vocabularyTranslation[index] = translations;

    const suggestedAnswer = (tierText(frame, "suggestedAnswer", difficultyLevel) || "").trim();
    if (suggestedAnswer) suggestedAnswers[index] = suggestedAnswer;

    const suffix = TIER_SUFFIX[difficultyLevel];
    const listenAudioSource = frame[`listenAudioSource${suffix}` as keyof CustomStoryFrame] as "teacher" | undefined;
    const listenAudioUrl = (tierText(frame, "listenAudioUrl", difficultyLevel) || "").trim();
    // Legacy generated references are not student-playable. Do not expose them to the
    // student app; only explicitly uploaded teacher recordings are playable.
    if (listenAudioUrl && (listenAudioSource === undefined || listenAudioSource === "teacher")) {
      listenAudioUrls[index] = resolveImageUrl(listenAudioUrl);
    }
    if (listenAudioSource === "teacher") listenAudioSources[index] = listenAudioSource;
    const listenScript = (tierText(frame, "listenScript", difficultyLevel) || "").trim();
    if (listenScript) listenScripts[index] = listenScript;

    const audioUrls = parseJson(frame[`vocabularyAudioUrls${suffix}` as keyof CustomStoryFrame]);
    if (Array.isArray(audioUrls)) {
      vocabularyAudioUrls[index] = audioUrls.map((url) => typeof url === "string" && url ? resolveImageUrl(url) : null);
    }
    const referenceCurves = parseJson(frame[`vocabularyReferenceCurves${suffix}` as keyof CustomStoryFrame]);
    if (Array.isArray(referenceCurves)) {
      vocabularyReferenceCurves[index] = referenceCurves.map((curve) =>
        Array.isArray(curve) ? curve.filter((value): value is number => typeof value === "number") : [],
      );
    }
    const sentenceCurves = parseJson(frame[`sentenceReferenceCurves${suffix}` as keyof CustomStoryFrame]);
    if (sentenceCurves && typeof sentenceCurves === "object" && !Array.isArray(sentenceCurves)) {
      const safeCurves: Record<string, number[]> = {};
      Object.entries(sentenceCurves).forEach(([token, curve]) => {
        if (Array.isArray(curve)) {
          const numbers = curve.filter((value): value is number => typeof value === "number");
          if (numbers.length) safeCurves[token] = numbers;
        }
      });
      if (Object.keys(safeCurves).length) sentenceReferenceCurves[index] = safeCurves;
    }
  });

  // Story-wide learning content is represented by one logical scene so the
  // existing speaking UI can display it without duplicating the rows.
  const storyVocabulary = story.storyVocabulary?.[difficultyLevel];
  if (storyVocabulary) {
    vocabulary[0] = splitCsvField(storyVocabulary.vocabulary);
    const pinyin = splitCsvField(storyVocabulary.vocabularyPinyin).map(numericToToneMarked);
    const pos = splitCsvField(storyVocabulary.vocabularyPos);
    const translations = splitCsvField(storyVocabulary.vocabularyTranslation);
    if (pinyin.length) vocabularyPinyin[0] = pinyin;
    if (pos.length) vocabularyPos[0] = pos;
    if (translations.length) vocabularyTranslation[0] = translations;
  }
  const storyPhrases = story.storyPhrases?.[difficultyLevel];
  if (storyPhrases) {
    const storyPhraseList = splitCsvField(storyPhrases.phrases);
    const storyPhraseTranslations = splitCsvField(storyPhrases.phrasesTranslation);
    if (storyPhraseList.length) phrases[0] = storyPhraseList;
    if (storyPhraseTranslations.length) phrasesTranslation[0] = storyPhraseTranslations;
  }

  const vocabAssessment = Array.isArray(story.vocabAssessment)
    ? story.vocabAssessment.map((question) => ({
      ...question,
      ...(question.audioUrl ? { audioUrl: resolveImageUrl(question.audioUrl) } : {}),
    }))
    : undefined;

  return {
    id: `teacher-${story.id}`,
    name: story.title,
    ...(story.conversationTurns ? { conversationTurns: story.conversationTurns } : {}),
    ...(vocabAssessment ? { vocabAssessment } : {}),
    description: "Teacher published activity",
    skillFocus: "Teacher published activity",
    images: story.frames.map((frame) => resolveImageUrl(tierText(frame, "imageUrl", difficultyLevel) || "")),
    prompts: story.frames.map((frame) => tierText(frame, "prompt", difficultyLevel) || ""),
    vocabulary,
    ...(Object.keys(vocabularyGroups).length ? { vocabularyGroups } : {}),
    ...(Object.keys(phrases).length ? { phrases } : {}),
    ...(Object.keys(phrasesTranslation).length ? { phrasesTranslation } : {}),
    ...(Object.keys(vocabularyPinyin).length ? { vocabularyPinyin } : {}),
    ...(Object.keys(vocabularyPos).length ? { vocabularyPos } : {}),
    ...(Object.keys(vocabularyTranslation).length ? { vocabularyTranslation } : {}),
    ...(Object.keys(suggestedAnswers).length ? { suggestedAnswers } : {}),
    ...(Object.keys(listenAudioUrls).length ? { listenAudioUrls } : {}),
    ...(Object.keys(listenAudioSources).length ? { listenAudioSources } : {}),
    ...(Object.keys(listenScripts).length ? { listenScripts } : {}),
    ...(Object.keys(vocabularyAudioUrls).length ? { vocabularyAudioUrls } : {}),
    ...(Object.keys(vocabularyReferenceCurves).length ? { vocabularyReferenceCurves } : {}),
    ...(Object.keys(sentenceReferenceCurves).length ? { sentenceReferenceCurves } : {}),
    ...(story.lessonNumber != null ? { lessonNumber: story.lessonNumber } : {}),
    ...(story.lessonSubOrder != null ? { lessonSubOrder: story.lessonSubOrder } : {}),
    difficultyLevel,
    sourceStory: story,
  };
}

function parseJson(value: unknown): unknown {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}
