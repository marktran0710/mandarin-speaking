// @ts-nocheck
import React from "react";
import StoryBuilderFrameEditor from "./StoryBuilderSection.FrameEditor";

function StoryDetailsFields({ draft, errors, onUpdateField, onUpdateFrameCount, onSetDraft }) {
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
    <label>Learning goal
      <textarea aria-invalid={Boolean(errors.learningGoal)} value={draft.learningGoal} onChange={(event) => onUpdateField("learningGoal", event.target.value)} rows={3} placeholder="What should students practice in this story?" />
      {errors.learningGoal && <span className="teacher-form-error">{errors.learningGoal}</span>}
    </label>
    {draft.narrativeMode === "story" && draft.imageUrls.easy.length > 1 && <label className="teacher-checkbox-field"><input type="checkbox" checked={draft.firstFrameIsExample} onChange={(event) => onSetDraft((current) => ({ ...current, firstFrameIsExample: event.target.checked }))} />First frame is a teacher model example — students see it before recording (frame 1 becomes a read-only demo)</label>}
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

function StoryFormActionGroup({ preparedFrameCount, frameCount, editingStoryId, onCancel }) {
  return <div className="teacher-builder-actions"><p>{preparedFrameCount}/{frameCount} frames prepared</p><div className="teacher-builder-buttons">
    {editingStoryId && <button type="button" className="btn-cancel-custom-story" onClick={onCancel}>Cancel edit</button>}
    <button type="submit" className="btn-save-custom-story">{editingStoryId ? "Update custom story" : "Save custom story"}</button>
  </div></div>;
}

export default function StoryBuilderForm(props) {
  const { draft, validationErrors, customStoryNotice, savedReviewBanner, preparedFrameCount, editingStoryId,
    onSave, onUpdateField, onUpdateFrameCount, onSetDraft, onGoToQuizReview, onDismissReview, onCancel } = props;
  return <form className="custom-story-form" onSubmit={(event) => { event.preventDefault(); onSave(); }}>
    <StoryDetailsFields draft={draft} errors={validationErrors} onUpdateField={onUpdateField} onUpdateFrameCount={onUpdateFrameCount} onSetDraft={onSetDraft} />
    <StoryStatusMessages errors={validationErrors} notice={customStoryNotice} savedReviewBanner={savedReviewBanner} onGoToQuizReview={onGoToQuizReview} onDismissReview={onDismissReview} />
    <StoryBuilderFrameEditor {...props} />
    <StoryFormActionGroup preparedFrameCount={preparedFrameCount} frameCount={draft.imageUrls.easy.length} editingStoryId={editingStoryId} onCancel={onCancel} />
  </form>;
}
