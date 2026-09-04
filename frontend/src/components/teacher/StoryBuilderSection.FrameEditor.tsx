// @ts-nocheck
import React, { useEffect, useState } from "react";
import { resolveImageUrl } from "../../utils/teacherStories";
import { splitScriptIntoChunks } from "../../utils/scriptAlignment";
import { STORY_FRAME_GUIDES } from "./StoryBuilderSection.helpers";

function FramePreview({ draft, index, imageUrl, onPaste }) {
  const guide = STORY_FRAME_GUIDES[index];
  return <button type="button" className="teacher-frame-image-preview"
    aria-label={`Paste an image for frame ${index + 1}`} onPaste={onPaste}
    title="Click here, then paste (Ctrl+V) an image from your clipboard">
    {imageUrl ? <img src={resolveImageUrl(imageUrl)} alt={`Custom story frame ${index + 1}`} /> : guide ? (
      <svg viewBox="0 0 180 130" xmlns="http://www.w3.org/2000/svg" className="teacher-frame-guide-svg">
        <rect width="180" height="130" fill={guide.accent} />{guide.renderIcon()}
        <rect x="0" y="96" width="180" height="34" fill={guide.color} />
        <text x="90" y="110" textAnchor="middle" fill="white" fontSize="9" fontWeight="700" fontFamily="sans-serif">{guide.zh}</text>
        <text x="90" y="122" textAnchor="middle" fill="white" fontSize="7.5" fontFamily="sans-serif" opacity="0.9">{guide.tip}</text>
        <text x="8" y="14" fill={guide.color} fontSize="8" fontWeight="700" fontFamily="sans-serif">{guide.en}</text>
        <text x="172" y="92" textAnchor="end" fill={guide.color} fontSize="7" fontFamily="sans-serif" opacity="0.6">📋 paste image here</text>
      </svg>
    ) : <span>Frame {index + 1}<br /><small className="teacher-frame-paste-hint">📋 Click + paste (Ctrl+V)</small></span>}
  </button>;
}

function StoryFrameFields(props) {
  const { draft, index, level, frameError, updateDraftFrame, onUploadImage } = props;
  const imageUrl = draft.imageUrls[level][index];
  const chunks = splitScriptIntoChunks(draft.suggestedAnswers[level][index]);
  return <div className="teacher-frame-fields">
    <label>{level === "easy" ? "Image URL or uploaded file" : "Image URL or uploaded file (optional — falls back to Easy's image)"}
      <input aria-invalid={level === "easy" && Boolean(frameError?.imageUrl)} value={imageUrl}
        onChange={(event) => updateDraftFrame("imageUrls", index, event.target.value)} placeholder="Paste an image link for this scene" />
      {level === "easy" && frameError?.imageUrl && <span className="teacher-form-error">{frameError.imageUrl}</span>}
    </label>
    <label className="teacher-file-upload">Upload from computer
      <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={(event) => onUploadImage(index, event.target.files?.[0])} />
    </label>
    <>
      <label>Script
        <textarea value={draft.suggestedAnswers[level][index] ?? ""} onChange={(event) => updateDraftFrame("suggestedAnswers", index, event.target.value)}
          rows={2} placeholder="Write the sentence students should say. Their voice transcript will be compared with this script." />
      </label>
      {chunks.length > 1 && <p className="script-chunk-preview"><span className="script-chunk-preview-lead">Auto-detected parts (edit punctuation above to adjust):</span>{chunks.map((chunk, chunkIndex) => <span key={chunkIndex} className="script-chunk-preview-chip">{chunk}</span>)}</p>}
    </>
  </div>;
}

export default function StoryBuilderFrameEditor(props) {
  const { draft, editingStoryId, validationAttemptGeneration, validationErrors, onPasteImage } = props;
  const level = draft.activeLevel;
  const frameCount = draft.imageUrls.easy.length;
  const [openFrameIndex, setOpenFrameIndex] = useState(0);
  const frameErrors = validationErrors.frames;

  useEffect(() => {
    setOpenFrameIndex((current) => Math.min(current, Math.max(frameCount - 1, 0)));
  }, [frameCount]);

  useEffect(() => {
    setOpenFrameIndex(0);
  }, [editingStoryId]);

  useEffect(() => {
    const firstInvalidFrame = Object.keys(frameErrors ?? {}).find((index) => Boolean(frameErrors?.[index]));
    if (firstInvalidFrame !== undefined) setOpenFrameIndex(Number(firstInvalidFrame));
  }, [validationAttemptGeneration]);

  if (frameCount === 0) return null;

  const selectFrame = (index) => setOpenFrameIndex(index);
  const completionForFrame = (index) => [
    Boolean(draft.imageUrls[level][index]?.trim() || draft.prompts[level][index]?.trim()),
    Boolean(draft.suggestedAnswers[level][index]?.trim()),
  ];
  const openFrameError = frameErrors?.[openFrameIndex];

  return <section className="teacher-frame-editor" aria-labelledby="teacher-frame-editor-title">
    <div className="teacher-frame-editor-heading">
      <div>
        <h3 id="teacher-frame-editor-title">Scenes</h3>
        <p>Build one scene at a time.</p>
      </div>
      <span>Scene {openFrameIndex + 1} of {frameCount}</span>
    </div>
    <div className="teacher-frame-editor-layout">
      <div className="teacher-frame-rail" role="tablist" aria-label="Story scenes">
        {draft.imageUrls.easy.map((_, index) => {
          const completion = completionForFrame(index);
          const preparedCount = completion.filter(Boolean).length;
          const isFilled = preparedCount > 0;
          return <button key={index} type="button" role="tab"
          id={`teacher-scene-tab-${index}`} aria-controls={`teacher-scene-panel-${index}`} aria-selected={openFrameIndex === index}
          aria-label={`Scene ${index + 1}: ${preparedCount} of 2 items prepared`}
          className={`${openFrameIndex === index ? "is-active" : ""}${isFilled ? " is-filled" : ""}${frameErrors?.[index] ? " has-error" : ""}`}
          onClick={() => selectFrame(index)}><span>{index + 1}</span><span className="teacher-frame-rail-progress" aria-hidden="true">{completion.map((isComplete, partIndex) => <i className={isComplete ? "is-complete" : ""} key={partIndex} />)}</span></button>;
        })}
      </div>
      <div className="teacher-frame-stage" id={`teacher-scene-panel-${openFrameIndex}`} role="tabpanel" aria-labelledby={`teacher-scene-tab-${openFrameIndex}`}>
          <div className={`teacher-frame-card ${openFrameError ? "has-error" : ""}`}>
            <FramePreview draft={draft} index={openFrameIndex} imageUrl={draft.imageUrls[level][openFrameIndex]} onPaste={(event) => onPasteImage(openFrameIndex, event)} />
            <StoryFrameFields {...props} index={openFrameIndex} level={level} frameError={openFrameError} isExampleFrame={false} />
          </div>
          <nav className="teacher-frame-navigation" aria-label="Scene navigation">
          <button type="button" onClick={() => selectFrame(openFrameIndex - 1)} disabled={openFrameIndex === 0}>Previous scene</button>
          <button type="button" onClick={() => selectFrame(openFrameIndex + 1)} disabled={openFrameIndex === frameCount - 1}>Next scene</button>
          </nav>
      </div>
    </div>
  </section>;
}
