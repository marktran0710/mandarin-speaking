// @ts-nocheck
import React, { useEffect, useRef, useState } from "react";
import StoryBuilderFrameEditor from "./StoryBuilderSection.FrameEditor";
import VocabularyTable from "../VocabularyTable";
import PhraseTable from "../PhraseTable";
import { PHRASE_COUNT_BY_LEVEL } from "./StoryBuilderSection.helpers";

function StoryDetailsFields({ draft, errors, onUpdateField, onUpdateFrameCount, onSetDraft, onOpenLearningContent, learningContentTriggerRef }) {
  return <>
    <div className="teacher-form-grid">
      <label className="teacher-field-span2">Story title
        <input aria-invalid={Boolean(errors.title)} value={draft.title} onChange={(event) => onUpdateField("title", event.target.value)} placeholder="e.g. A Rainy Day at Taipei Station" />
        {errors.title && <span className="teacher-form-error">{errors.title}</span>}
      </label>
      <label>Lesson number<input type="number" min={1} value={draft.lessonNumber} onChange={(event) => onUpdateField("lessonNumber", event.target.value)} placeholder="e.g. 3" /></label>
      <label>Story order in lesson<input type="number" min={1} disabled={!draft.lessonNumber.trim()} value={draft.lessonSubOrder} onChange={(event) => onUpdateField("lessonSubOrder", event.target.value)} placeholder="e.g. 1 for 5-1, 2 for 5-2…" /></label>
      <p className="teacher-form-note">Students must finish this story before the next order number in the same lesson unlocks. Leave blank to keep this story unordered — every story in the lesson needs an order number before locking applies to any of them.</p>
      <label>Number of frames<input type="number" min={1} max={12} value={draft.imageUrls.easy.length} onChange={(event) => onUpdateFrameCount(Number(event.target.value) || 1)} /></label>
      <label>Level<select value={draft.activeLevel} onChange={(event) => onSetDraft((current) => ({ ...current, activeLevel: event.target.value }))}>
        <option value="easy">Easy (required — students always see this)</option><option value="medium">Medium (optional)</option><option value="hard">Hard (optional)</option>
      </select></label>
    </div>
    {draft.activeLevel !== "easy" && <p className="teacher-tier-hint">Editing the {draft.activeLevel === "medium" ? "Medium" : "Hard"} version of each scene below — frame count stays shared with Easy. Any image or text left blank here falls back to its Easy version for students.</p>}
    <div className="story-learning-launcher">
      <div>
        <strong>Story-wide vocabulary & phrases</strong>
        <span>Shared across every scene in the selected level</span>
      </div>
      <button ref={learningContentTriggerRef} type="button" className="story-learning-open-btn" onClick={onOpenLearningContent}>
        Edit learning content <span aria-hidden="true">↗</span>
      </button>
    </div>
  </>;
}

function StoryStatusMessages({ errors, notice, savedReviewBanner, onGoToQuizReview, onDismissReview }) {
  return <>
    {errors.form && <div className="teacher-form-alert" role="alert">{errors.form}</div>}
    {notice && <div className="teacher-form-success" role="status">{notice}</div>}
    {savedReviewBanner && <div className="quiz-review-nudge-banner" role="status"><span>⚙️ Quiz material may need review before students see it.</span><div className="quiz-review-nudge-actions">
      <button type="button" className="quiz-review-nudge-go" onClick={() => { onGoToQuizReview?.(savedReviewBanner.lessonNumber); onDismissReview(); }}>Go to Quiz Review →</button>
      <button type="button" className="quiz-review-nudge-dismiss" aria-label="Dismiss" onClick={onDismissReview}>✕</button>
    </div></div>}
  </>;
}

function StoryLearningContent({
  draft,
  onUpdateStoryVocabulary,
  onUpdateStoryPhrases,
  onFillStoryVocab,
  onFillStoryPhrases,
  storyVocabDraftGeneration,
  storyPhraseDraftGeneration,
  storyVocabFillLoading,
  storyPhraseFillLoading,
  storyVocabFillError,
  storyPhraseFillError,
  onClose,
  closeButtonRef,
}) {
  const level = draft.activeLevel;
  const vocabulary = draft.storyVocabulary[level];
  const phrases = draft.storyPhrases[level];
  const phraseCount = PHRASE_COUNT_BY_LEVEL[level];
  const hasScripts = draft.suggestedAnswers[level].some((script) => script.trim());
  return <div className="story-learning-content" aria-labelledby="story-learning-content-title">
    <div className="story-learning-content-header">
      <div>
        <p className="stories-kicker">Shared learning content</p>
        <h3 id="story-learning-content-title">Vocabulary & phrases for the whole story</h3>
        <p className="teacher-form-note">These lists are shared across every scene in the {level} version. Add them once here instead of repeating them scene by scene.</p>
      </div>
      <div className="story-learning-content-header-actions">
        <div className="story-learning-content-actions">
          <button type="button" className="btn-vocab-autofill-sm" disabled={!hasScripts || storyVocabFillLoading} onClick={onFillStoryVocab}>
            {storyVocabFillLoading ? "Filling…" : "✨ Fill vocab from story scripts"}
          </button>
          <button type="button" className="btn-vocab-autofill-sm" disabled={!hasScripts || storyPhraseFillLoading} onClick={onFillStoryPhrases}>
            {storyPhraseFillLoading ? "Generating…" : `✨ +${phraseCount} phrase${phraseCount > 1 ? "s" : ""}`}
          </button>
        </div>
        <button ref={closeButtonRef} type="button" className="story-learning-close-btn" aria-label="Close learning content" onClick={onClose}>×</button>
      </div>
    </div>
    {storyVocabFillError && <p className="teacher-form-error" role="alert">{storyVocabFillError}</p>}
    {storyPhraseFillError && <p className="teacher-form-error" role="alert">{storyPhraseFillError}</p>}
    <div className="story-learning-content-grid">
      <div className="story-learning-table-block">
        <div className="story-learning-table-heading"><h4>Vocabulary</h4><span>One row per word</span></div>
        <VocabularyTable key={`${storyVocabDraftGeneration}-${level}`} vocabulary={vocabulary.vocabulary}
          vocabularyPinyin={vocabulary.vocabularyPinyin} vocabularyPos={vocabulary.vocabularyPos}
          vocabularyTranslation={vocabulary.vocabularyTranslation}
          onChangeColumn={onUpdateStoryVocabulary} />
      </div>
      <div className="story-learning-table-block">
        <div className="story-learning-table-heading"><h4>Reusable phrases</h4><span>One row per phrase</span></div>
        <PhraseTable key={`${storyPhraseDraftGeneration}-${level}`} phrases={phrases.phrases}
          phrasesTranslation={phrases.phrasesTranslation}
          onChangeColumn={onUpdateStoryPhrases} />
      </div>
    </div>
  </div>;
}

function StoryFormActionGroup({ preparedFrameCount, frameCount, editingStoryId, onCancel }) {
  return <div className="teacher-builder-actions"><p>{preparedFrameCount}/{frameCount} frames prepared</p><div className="teacher-builder-buttons">
    {editingStoryId && <button type="button" className="btn-cancel-custom-story" onClick={onCancel}>Cancel edit</button>}
    <button type="submit" className="btn-save-custom-story">{editingStoryId ? "Update custom story" : "Save custom story"}</button>
  </div></div>;
}

export default function StoryBuilderForm(props) {
  const { draft, validationErrors, customStoryNotice, savedReviewBanner, preparedFrameCount, editingStoryId,
    onSave, onUpdateField, onUpdateFrameCount, onSetDraft, onGoToQuizReview, onDismissReview, onCancel } = props;
  const [learningContentOpen, setLearningContentOpen] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const learningContentTriggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!learningContentOpen) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>("[data-story-learning-dialog]");
    const getFocusable = () => dialog
      ? Array.from(dialog.querySelectorAll<HTMLElement>("button, input, select, textarea, [tabindex]:not([tabindex='-1'])"))
      : [];
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setLearningContentOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = getFocusable();
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [learningContentOpen]);

  const closeLearningContent = () => {
    setLearningContentOpen(false);
    requestAnimationFrame(() => learningContentTriggerRef.current?.focus());
  };

  return <form className="custom-story-form" onSubmit={(event) => { event.preventDefault(); onSave(); }}>
    <StoryDetailsFields draft={draft} errors={validationErrors} onUpdateField={onUpdateField} onUpdateFrameCount={onUpdateFrameCount} onSetDraft={onSetDraft} onOpenLearningContent={() => setLearningContentOpen(true)} learningContentTriggerRef={learningContentTriggerRef} />
    <StoryStatusMessages errors={validationErrors} notice={customStoryNotice} savedReviewBanner={savedReviewBanner} onGoToQuizReview={onGoToQuizReview} onDismissReview={onDismissReview} />
    <StoryBuilderFrameEditor {...props} />
    <StoryFormActionGroup preparedFrameCount={preparedFrameCount} frameCount={draft.imageUrls.easy.length} editingStoryId={editingStoryId} onCancel={onCancel} />
    {learningContentOpen && <div className="story-learning-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeLearningContent(); }}>
      <div className="story-learning-modal" data-story-learning-dialog role="dialog" aria-modal="true" aria-labelledby="story-learning-content-title" onMouseDown={(event) => event.stopPropagation()}>
        <StoryLearningContent {...props} onClose={closeLearningContent} closeButtonRef={closeButtonRef} />
      </div>
    </div>}
  </form>;
}
