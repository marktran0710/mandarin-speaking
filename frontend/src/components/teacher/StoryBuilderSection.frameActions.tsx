// @ts-nocheck
import {
  buildPhraseRows, buildVocabRows, getImageUploadError,
  mergePhraseSuggestions, mergeVocabSuggestions,
} from "../../utils/myStoriesUtils";
import { BACKEND_URL, PHRASE_COUNT_BY_LEVEL } from "./StoryBuilderSection.helpers";

export function useStoryBuilderFrameActions(deps) {
  const {
    customDraft, updateDraftFrame, setValidationErrors, setCustomDraft,
    setVocabDraftGeneration, setPhraseDraftGeneration, setVocabFillError, setVocabFillLoadingIndex,
    setPhraseFillError, setPhraseFillLoadingIndex,
    setStoryVocabDraftGeneration, setStoryPhraseDraftGeneration,
    setStoryVocabFillError, setStoryVocabFillLoading, setStoryPhraseFillError,
    setStoryPhraseFillLoading,
  } = deps;
  const handlePasteFrameImage = (index: number, event: React.ClipboardEvent) => {
    const items = event.clipboardData?.items;
    if (!items) {
      return;
    }
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        event.preventDefault();
        handleUploadFrameImage(index, item.getAsFile() ?? undefined);
        return;
      }
    }
  };

  const handleUploadFrameImage = (index: number, file?: File) => {
    if (!file) {
      return;
    }

    const error = getImageUploadError(file);
    if (error) {
      setValidationErrors((errors) => ({ ...errors, form: error }));
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        updateDraftFrame("imageUrls", index, reader.result);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleFillVocabFromSentence = async (index: number) => {
    const level = customDraft.activeLevel;
    const sentence = customDraft.suggestedAnswers[level][index]?.trim();
    if (!sentence) return;

    setVocabFillError("");
    setVocabFillLoadingIndex(index);
    try {
      const response = await fetch(`${BACKEND_URL}/api/vocab-from-sentence`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sentence }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Could not extract vocabulary from that sentence.");
      }
      const { words } = (await response.json()) as { words: VocabWordSuggestion[] };

      const existingRows = buildVocabRows(
        customDraft.vocabulary[level][index] ?? "",
        customDraft.vocabularyPinyin[level][index] ?? "",
        customDraft.vocabularyPos[level][index] ?? "",
        customDraft.vocabularyTranslation[level][index] ?? "",
      );
      const mergedRows = mergeVocabSuggestions(existingRows, words);

      setCustomDraft((draft) => ({
        ...draft,
        vocabulary: {
          ...draft.vocabulary,
          [level]: draft.vocabulary[level].map((v, i) => (i === index ? mergedRows.map((r) => r.word).join(", ") : v)),
        },
        vocabularyPinyin: {
          ...draft.vocabularyPinyin,
          [level]: draft.vocabularyPinyin[level].map((v, i) => (i === index ? mergedRows.map((r) => r.pinyin).join(", ") : v)),
        },
        vocabularyPos: {
          ...draft.vocabularyPos,
          [level]: draft.vocabularyPos[level].map((v, i) => (i === index ? mergedRows.map((r) => r.pos).join(", ") : v)),
        },
        vocabularyTranslation: {
          ...draft.vocabularyTranslation,
          [level]: draft.vocabularyTranslation[level].map((v, i) => (i === index ? mergedRows.map((r) => r.translation).join(", ") : v)),
        },
      }));
      setVocabDraftGeneration((generation) => generation + 1);
    } catch (error) {
      setVocabFillError(
        error instanceof Error ? error.message : "Could not extract vocabulary from that sentence.",
      );
    } finally {
      setVocabFillLoadingIndex(null);
    }
  };

  const handleFillStoryVocab = async () => {
    const level = customDraft.activeLevel;
    const sentence = customDraft.suggestedAnswers[level].filter((item) => item.trim()).join("\n");
    if (!sentence) return;
    setStoryVocabFillError("");
    setStoryVocabFillLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/vocab-from-sentence`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sentence }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Could not extract vocabulary from the story scripts.");
      }
      const { words } = (await response.json()) as { words: VocabWordSuggestion[] };
      const current = customDraft.storyVocabulary[level];
      const mergedRows = mergeVocabSuggestions(
        buildVocabRows(current.vocabulary, current.vocabularyPinyin, current.vocabularyPos, current.vocabularyTranslation),
        words,
      );
      const next = {
        vocabulary: mergedRows.map((row) => row.word).join(", "),
        vocabularyPinyin: mergedRows.map((row) => row.pinyin).join(", "),
        vocabularyPos: mergedRows.map((row) => row.pos).join(", "),
        vocabularyTranslation: mergedRows.map((row) => row.translation).join(", "),
      };
      setCustomDraft((draft) => ({
        ...draft,
        storyVocabulary: { ...draft.storyVocabulary, [level]: next },
      }));
      setStoryVocabDraftGeneration((generation) => generation + 1);
    } catch (error) {
      setStoryVocabFillError(error instanceof Error ? error.message : "Could not extract vocabulary from the story scripts.");
    } finally {
      setStoryVocabFillLoading(false);
    }
  };

  const handleFillStoryPhrases = async () => {
    const level = customDraft.activeLevel;
    const sentence = customDraft.suggestedAnswers[level].filter((item) => item.trim()).join("\n");
    if (!sentence) return;
    setStoryPhraseFillError("");
    setStoryPhraseFillLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/api/phrases-from-sentence`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sentence, count: PHRASE_COUNT_BY_LEVEL[level] }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Could not extract phrases from the story scripts.");
      }
      const { phrases } = (await response.json()) as { phrases: PhraseSuggestion[] };
      const current = customDraft.storyPhrases[level];
      const mergedRows = mergePhraseSuggestions(
        buildPhraseRows(current.phrases, current.phrasesTranslation),
        phrases,
      );
      const next = {
        phrases: mergedRows.map((row) => row.phrase).join(", "),
        phrasesTranslation: mergedRows.map((row) => row.translation).join(", "),
      };
      setCustomDraft((draft) => ({
        ...draft,
        storyPhrases: { ...draft.storyPhrases, [level]: next },
      }));
      setStoryPhraseDraftGeneration((generation) => generation + 1);
    } catch (error) {
      setStoryPhraseFillError(error instanceof Error ? error.message : "Could not extract phrases from the story scripts.");
    } finally {
      setStoryPhraseFillLoading(false);
    }
  };

  const handleFillPhrasesFromSentence = async (index: number) => {
    const level = customDraft.activeLevel;
    const sentence = customDraft.suggestedAnswers[level][index]?.trim();
    if (!sentence) return;

    setPhraseFillError("");
    setPhraseFillLoadingIndex(index);
    try {
      const response = await fetch(`${BACKEND_URL}/api/phrases-from-sentence`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sentence, count: PHRASE_COUNT_BY_LEVEL[level] }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Could not extract phrases from that sentence.");
      }
      const { phrases } = (await response.json()) as { phrases: PhraseSuggestion[] };

      const existingRows = buildPhraseRows(
        customDraft.phrases[level][index] ?? "",
        customDraft.phrasesTranslation[level][index] ?? "",
      );
      const mergedRows = mergePhraseSuggestions(existingRows, phrases);

      setCustomDraft((draft) => ({
        ...draft,
        phrases: {
          ...draft.phrases,
          [level]: draft.phrases[level].map((v, i) => (i === index ? mergedRows.map((r) => r.phrase).join(", ") : v)),
        },
        phrasesTranslation: {
          ...draft.phrasesTranslation,
          [level]: draft.phrasesTranslation[level].map((v, i) => (i === index ? mergedRows.map((r) => r.translation).join(", ") : v)),
        },
      }));
      setPhraseDraftGeneration((generation) => generation + 1);
    } catch (error) {
      setPhraseFillError(
        error instanceof Error ? error.message : "Could not extract phrases from that sentence.",
      );
    } finally {
      setPhraseFillLoadingIndex(null);
    }
  };


  return {
    handlePasteFrameImage, handleUploadFrameImage,
    handleFillVocabFromSentence, handleFillPhrasesFromSentence,
    handleFillStoryVocab, handleFillStoryPhrases,
  };
}
