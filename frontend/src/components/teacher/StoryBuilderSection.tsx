// @ts-nocheck
import React, { useEffect, useState } from "react";
import {
  canUseDatabase,
  createCustomStory as saveCustomStoryToDatabase,
  deleteCustomStoryFromDatabase,
  listCustomStories,
} from "../../services/database";
import {
  CustomTeacherStory,
  type StoryDifficultyLevel,
  VocabGroup,
  loadCustomStories,
  saveCustomStories,
} from "../../utils/teacherStories";
import { storyQuizExclusions } from "../../utils/quizExclusions";
import { buildApprovedMaterial, storyQuizNeedsReview } from "../../utils/quizApprovedMaterial";
import { exportStoryFile, readStoryImportFile } from "../../utils/storyPortability";
import {
  clearFrameError,
  getAudioUploadError,
  getImageUploadError,
  hasCustomStoryErrors,
  resizeToCount,
} from "../../utils/myStoriesUtils";

import {
  BACKEND_URL,
  GRAMMAR_CANVAS_ENABLED,
  emptyCustomStoryDraft,
  type CustomStoryValidationErrors,
  type TieredDraftField,
  validateCustomStoryDraft,
} from "./StoryBuilderSection.helpers";
import { createCustomStory, storyToDraft } from "./StoryBuilderSection.model";
import StoryBuilderForm from "./StoryBuilderSection.Form";
import StoryBuilderLibrary from "./StoryBuilderSection.Library";
import { useStoryBuilderFrameActions } from "./StoryBuilderSection.frameActions";
export type { CustomStoryValidationErrors } from "./StoryBuilderSection.helpers";
export default function StoryBuilderSection({
  onStorySaved,
  onGoToQuizReview,
}: {
  onStorySaved?: () => void;
  /** Jumps the teacher shell to Materials → Quiz Review, pre-selecting the
   * lesson the just-saved story belongs to. */
  onGoToQuizReview?: (lessonNumber: number | null) => void;
}) {
  const [customStories, setCustomStories] = useState<CustomTeacherStory[]>(
    () => loadCustomStories(),
  );
  const [customDraft, setCustomDraft] = useState(emptyCustomStoryDraft);
  const [editingStoryId, setEditingStoryId] = useState<string | null>(null);
  // Shown after updating an existing story — quiz material may now be
  // stale against what's approved, and there was previously no prompt at
  // all telling a teacher to go check.
  const [savedReviewBanner, setSavedReviewBanner] = useState<{ lessonNumber: number | null } | null>(
    null,
  );
  const [vocabDraftGeneration, setVocabDraftGeneration] = useState(0);
  const [vocabFillLoadingIndex, setVocabFillLoadingIndex] = useState<number | null>(null);
  const [vocabFillError, setVocabFillError] = useState("");
  const [phraseDraftGeneration, setPhraseDraftGeneration] = useState(0);
  const [phraseFillLoadingIndex, setPhraseFillLoadingIndex] = useState<number | null>(null);
  const [phraseFillError, setPhraseFillError] = useState("");
  const [storyVocabDraftGeneration, setStoryVocabDraftGeneration] = useState(0);
  const [storyPhraseDraftGeneration, setStoryPhraseDraftGeneration] = useState(0);
  const [storyVocabFillLoading, setStoryVocabFillLoading] = useState(false);
  const [storyPhraseFillLoading, setStoryPhraseFillLoading] = useState(false);
  const [storyVocabFillError, setStoryVocabFillError] = useState("");
  const [storyPhraseFillError, setStoryPhraseFillError] = useState("");
  // Frame index currently being recorded via the mic (null when idle) — a
  // teacher's own reading of the listening passage, as an alternative to
  // uploading a file or falling back to TTS.
  const [recordingFrameIndex, setRecordingFrameIndex] = useState<number | null>(null);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [validationErrors, setValidationErrors] =
    useState<CustomStoryValidationErrors>({});
  const [customStoryNotice, setCustomStoryNotice] = useState("");
  const [importError, setImportError] = useState("");
  const [importNotice, setImportNotice] = useState("");
  const [lessonFilter, setLessonFilter] = useState<string>("all");
  const preparedFrameCount = customDraft.imageUrls.easy.filter((imageUrl, index) => {
    return imageUrl.trim() || customDraft.prompts.easy[index].trim();
  }).length;

  useEffect(() => {
    if (!canUseDatabase()) {
      return;
    }

    listCustomStories()
      .then((stories) => {
        setCustomStories(stories);
        saveCustomStories(stories);
      })
      .catch((error) => {
        console.error("Failed to load custom stories from database:", error);
      });
  }, []);

  const clearNotice = () => setCustomStoryNotice("");

  const updateDraftField = (
    field: "title" | "lessonNumber" | "lessonSubOrder",
    value: string,
  ) => {
    setCustomDraft((draft) => ({ ...draft, [field]: value }));
    setValidationErrors((errors) => ({ ...errors, [field]: undefined, form: undefined }));
    clearNotice();
  };

  const resizeTiers = (
    tiers: Record<StoryDifficultyLevel, string[]>,
    clamped: number,
  ): Record<StoryDifficultyLevel, string[]> => ({
    easy: resizeToCount(tiers.easy, clamped, ""),
    medium: resizeToCount(tiers.medium, clamped, ""),
    hard: resizeToCount(tiers.hard, clamped, ""),
  });

  const updateFrameCount = (count: number) => {
    const clamped = Math.min(12, Math.max(1, count));
    setCustomDraft((draft) => ({
      ...draft,
      imageUrls: resizeTiers(draft.imageUrls, clamped),
      prompts: resizeTiers(draft.prompts, clamped),
      vocabulary: resizeTiers(draft.vocabulary, clamped),
      vocabularyPinyin: resizeTiers(draft.vocabularyPinyin, clamped),
      vocabularyPos: resizeTiers(draft.vocabularyPos, clamped),
      vocabularyTranslation: resizeTiers(draft.vocabularyTranslation, clamped),
      vocabularyDistractors: resizeToCount(draft.vocabularyDistractors, clamped, ""),
      vocabularyGroups: resizeToCount(draft.vocabularyGroups, clamped, null),
      phrases: resizeTiers(draft.phrases, clamped),
      phrasesTranslation: resizeTiers(draft.phrasesTranslation, clamped),
      suggestedAnswers: resizeTiers(draft.suggestedAnswers, clamped),
      listenAudioUrls: resizeTiers(draft.listenAudioUrls, clamped),
      listenScripts: resizeTiers(draft.listenScripts, clamped),
    }));
    setValidationErrors((errors) => ({ ...errors, frames: undefined, form: undefined }));
  };

  const updateDraftGroups = (index: number, groups: VocabGroup[] | null) => {
    setCustomDraft((draft) => ({
      ...draft,
      vocabularyGroups: draft.vocabularyGroups.map((g, i) => i === index ? groups : g),
    }));
  };

  // Every tiered field, including images, is edited one tier at a time via
  // the level dropdown — a blank tier falls back to Easy for students (see
  // tierText in utils/teacherStories.ts).
  const updateDraftFrame = (
    field: TieredDraftField,
    index: number,
    value: string,
  ) => {
    setCustomDraft((draft) => {
      const level = draft.activeLevel;
      const tiers = draft[field];
      return {
        ...draft,
        [field]: {
          ...tiers,
          [level]: tiers[level].map((item, i) => (i === index ? value : item)),
        },
      };
    });
    setValidationErrors((errors) =>
      clearFrameError(
        errors,
        index,
        field === "listenAudioSources" ? "listenAudioUrls" : field,
      ),
    );
    clearNotice();
  };

  const updateStoryVocabulary = (field: string, value: string) => {
    setCustomDraft((draft) => ({
      ...draft,
      storyVocabulary: {
        ...draft.storyVocabulary,
        [draft.activeLevel]: {
          ...draft.storyVocabulary[draft.activeLevel],
          [field]: value,
        },
      },
    }));
    setStoryVocabFillError("");
    clearNotice();
  };

  const updateStoryPhrases = (field: string, value: string) => {
    setCustomDraft((draft) => ({
      ...draft,
      storyPhrases: {
        ...draft.storyPhrases,
        [draft.activeLevel]: {
          ...draft.storyPhrases[draft.activeLevel],
          [field]: value,
        },
      },
    }));
    setStoryPhraseFillError("");
    clearNotice();
  };

  const {
    handlePasteFrameImage,
    handleUploadFrameImage,
    handleUploadFrameAudio,
    handleStartFrameRecording,
    handleStopFrameRecording,
    handleFillVocabFromSentence,
    handleFillPhrasesFromSentence,
    handleFillStoryVocab,
    handleFillStoryPhrases,
  } = useStoryBuilderFrameActions({
    customDraft,
    updateDraftFrame,
    setValidationErrors,
    setCustomDraft,
    setVocabDraftGeneration,
    setPhraseDraftGeneration,
    setVocabFillError,
    setVocabFillLoadingIndex,
    setPhraseFillError,
    setPhraseFillLoadingIndex,
    setStoryVocabDraftGeneration,
    setStoryPhraseDraftGeneration,
    setStoryVocabFillError,
    setStoryVocabFillLoading,
    setStoryPhraseFillError,
    setStoryPhraseFillLoading,
    setRecordingFrameIndex,
    setRecordingSeconds,
  });

  const handleSaveCustomStory = async () => {
    const errors = validateCustomStoryDraft(customDraft, customStories, editingStoryId);
    if (hasCustomStoryErrors(errors)) {
      setValidationErrors(errors);
      setCustomStoryNotice("");
      return;
    }

    const existingStory = customStories.find((story) => story.id === editingStoryId);
    const savedStory: CustomTeacherStory = {
      ...createCustomStory(customDraft, editingStoryId),
      published: existingStory?.published ?? false,
      rubricScores: existingStory?.rubricScores ?? null,
    };

    // Persist to the backend first. It writes any uploaded data-URL images to
    // disk and returns the frames with lightweight /uploads/images/... URLs.
    // Caching the raw base64 in localStorage overflows its ~5MB quota, which
    // would otherwise abort the whole save and lose the uploaded image.
    let storyToStore = savedStory;
    if (canUseDatabase()) {
      try {
        const persisted = await saveCustomStoryToDatabase(savedStory);
        if (persisted) {
          storyToStore = {
            ...savedStory,
            ...persisted,
            frames: persisted.frames.map((persistedFrame, i) => ({
              ...savedStory.frames[i],
              ...persistedFrame,
            })),
          } as CustomTeacherStory;
        }
      } catch (error) {
        console.error("Failed to save custom story to database:", error);
        setValidationErrors({
          form: "The story could not be saved to the server. Check that the backend is running and try again.",
        });
        setCustomStoryNotice("");
        return;
      }
    }

    const nextStories = editingStoryId
      ? customStories.map((story) =>
          story.id === editingStoryId ? storyToStore : story,
        )
      : [storyToStore, ...customStories];

    setCustomStories(nextStories);
    try {
      saveCustomStories(nextStories);
    } catch {
      // localStorage is only a cache. If it overflows (e.g. data-URL images
      // while the backend is offline) the story is still saved server-side, so
      // keep going rather than failing the whole save.
      console.warn("Could not cache custom stories in localStorage (quota).");
    }
    setCustomStoryNotice(
      editingStoryId ? "Custom story updated." : "Custom story saved.",
    );
    if (editingStoryId) {
      setSavedReviewBanner({ lessonNumber: storyToStore.lessonNumber ?? null });
    }
    setEditingStoryId(null);
    setCustomDraft(emptyCustomStoryDraft);
    setVocabDraftGeneration((generation) => generation + 1);
    setValidationErrors({});
    onStorySaved?.();
  };

  const handleDeleteCustomStory = (id: string) => {
    const nextStories = customStories.filter((story) => story.id !== id);
    setCustomStories(nextStories);
    saveCustomStories(nextStories);
    if (canUseDatabase()) {
      deleteCustomStoryFromDatabase(id).catch((error) => {
        console.error("Failed to delete custom story from database:", error);
      });
    }
    if (editingStoryId === id) {
      handleCancelCustomStoryEdit();
    }
  };

  const handleExportStory = async (story: CustomTeacherStory) => {
    setImportError("");
    try {
      await exportStoryFile(story);
    } catch (error) {
      console.error("Failed to export story:", error);
      setImportError(
        error instanceof Error ? error.message : "Could not export this story.",
      );
    }
  };

  const handleImportStoryFile = async (file: File) => {
    setImportError("");
    setImportNotice("");
    let imported: CustomTeacherStory;
    try {
      imported = await readStoryImportFile(file);
    } catch (error) {
      setImportError(
        error instanceof Error ? error.message : "Could not read that story file.",
      );
      return;
    }

    let storyToStore = imported;
    if (canUseDatabase()) {
      try {
        const persisted = await saveCustomStoryToDatabase(imported);
        if (persisted) {
          storyToStore = {
            ...imported,
            ...persisted,
            frames: persisted.frames.map((persistedFrame, i) => ({
              ...imported.frames[i],
              ...persistedFrame,
            })),
          } as CustomTeacherStory;
        }
      } catch (error) {
        console.error("Failed to save imported story to database:", error);
        setImportError(
          "The story was read but could not be saved to the server. Check that the backend is running and try again.",
        );
        return;
      }
    }

    const nextStories = [storyToStore, ...customStories];
    setCustomStories(nextStories);
    try {
      saveCustomStories(nextStories);
    } catch {
      console.warn("Could not cache imported story in localStorage (quota).");
    }
    setImportNotice(`Imported "${storyToStore.title}" as a new draft.`);
  };

  const handleTogglePublishCustomStory = (id: string) => {
    const nextStories = customStories.map((story) =>
      story.id === id ? { ...story, published: !story.published } : story,
    );
    setCustomStories(nextStories);
    saveCustomStories(nextStories);
    const updatedStory = nextStories.find((story) => story.id === id);
    if (updatedStory && canUseDatabase()) {
      saveCustomStoryToDatabase(updatedStory).catch((error) => {
        console.error("Failed to update story publish state in database:", error);
      });
    }
    setCustomStoryNotice(
      updatedStory?.published
        ? "Story published for students."
        : "Story unpublished from student topics.",
    );
  };

  const handleEditCustomStory = (story: CustomTeacherStory) => {
    setEditingStoryId(story.id);
    setCustomDraft(storyToDraft(story));
    setVocabDraftGeneration((generation) => generation + 1);
    setValidationErrors({});
    setCustomStoryNotice("");
  };

  const handleCancelCustomStoryEdit = () => {
    setEditingStoryId(null);
    setCustomDraft(emptyCustomStoryDraft);
    setVocabDraftGeneration((generation) => generation + 1);
    setValidationErrors({});
    setCustomStoryNotice("");
  };

  const lessonNumbersInUse = Array.from(
    new Set(
      customStories
        .map((story) => story.lessonNumber)
        .filter((lessonNumber): lessonNumber is number => lessonNumber != null),
    ),
  ).sort((a, b) => a - b);
  const hasStoriesWithoutLesson = customStories.some((story) => story.lessonNumber == null);

  const filteredCustomStories = customStories.filter((story) => {
    if (lessonFilter === "all") return true;
    if (lessonFilter === "others") return story.lessonNumber == null;
    return story.lessonNumber === Number(lessonFilter);
  });

  return (
    <section className="teacher-panel teacher-content-builder">
      <div className="teacher-panel-header">
        <div>
          <p className="stories-kicker">Custom materials</p>
          <h2>{editingStoryId ? "Edit Story Activity" : "Create Story Activity"}</h2>
        </div>
        <span className="queue-count">{customStories.length}</span>
      </div>
      <div className="teacher-builder-layout">
        <StoryBuilderForm
          draft={customDraft}
          validationErrors={validationErrors}
          customStoryNotice={customStoryNotice}
          savedReviewBanner={savedReviewBanner}
          preparedFrameCount={preparedFrameCount}
          editingStoryId={editingStoryId}
          onSave={handleSaveCustomStory}
          onUpdateField={updateDraftField}
          onUpdateFrameCount={updateFrameCount}
          onSetDraft={setCustomDraft}
          onGoToQuizReview={onGoToQuizReview}
          onDismissReview={() => setSavedReviewBanner(null)}
          onCancel={handleCancelCustomStoryEdit}
          updateDraftFrame={updateDraftFrame}
          updateDraftGroups={updateDraftGroups}
          onPasteImage={handlePasteFrameImage}
          onUploadImage={handleUploadFrameImage}
          onUploadAudio={handleUploadFrameAudio}
          onFillVocab={handleFillVocabFromSentence}
          onFillPhrases={handleFillPhrasesFromSentence}
          onUpdateStoryVocabulary={updateStoryVocabulary}
          onUpdateStoryPhrases={updateStoryPhrases}
          onFillStoryVocab={handleFillStoryVocab}
          onFillStoryPhrases={handleFillStoryPhrases}
          storyVocabDraftGeneration={storyVocabDraftGeneration}
          storyPhraseDraftGeneration={storyPhraseDraftGeneration}
          storyVocabFillLoading={storyVocabFillLoading}
          storyPhraseFillLoading={storyPhraseFillLoading}
          storyVocabFillError={storyVocabFillError}
          storyPhraseFillError={storyPhraseFillError}
          vocabDraftGeneration={vocabDraftGeneration}
          phraseDraftGeneration={phraseDraftGeneration}
          vocabFillLoadingIndex={vocabFillLoadingIndex}
          phraseFillLoadingIndex={phraseFillLoadingIndex}
          vocabFillError={vocabFillError}
          phraseFillError={phraseFillError}
          recordingFrameIndex={recordingFrameIndex}
          recordingSeconds={recordingSeconds}
          onStartRecording={handleStartFrameRecording}
          onStopRecording={handleStopFrameRecording}
        />
        <StoryBuilderLibrary
          customStories={customStories}
          filteredCustomStories={filteredCustomStories}
          lessonNumbersInUse={lessonNumbersInUse}
          hasStoriesWithoutLesson={hasStoriesWithoutLesson}
          lessonFilter={lessonFilter}
          onLessonFilterChange={setLessonFilter}
          importError={importError}
          importNotice={importNotice}
          onImport={handleImportStoryFile}
          onTogglePublish={handleTogglePublishCustomStory}
          onEdit={handleEditCustomStory}
          onExport={handleExportStory}
          onDelete={handleDeleteCustomStory}
        />
      </div>
    </section>
  );
}
