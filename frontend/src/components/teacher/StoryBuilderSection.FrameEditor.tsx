// @ts-nocheck
import React from "react";
import { resolveImageUrl } from "../../utils/teacherStories";
import { splitScriptIntoChunks } from "../../utils/scriptAlignment";
import { STORY_FRAME_GUIDES } from "./StoryBuilderSection.helpers";

function FramePreview({ draft, index, imageUrl, onPaste }) {
  const guide = STORY_FRAME_GUIDES[index];
  return <div className="teacher-frame-image-preview" tabIndex={0} role="button"
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
  </div>;
}

function StoryFrameFields(props) {
  const { draft, index, level, frameError, updateDraftFrame,
    onUploadImage, onUploadAudio, recordingFrameIndex, recordingSeconds, onStartRecording, onStopRecording } = props;
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
      <label className="teacher-file-upload">Upload teacher reference audio (optional)
        <input type="file" accept="audio/mpeg,audio/wav,audio/webm,audio/ogg" onChange={(event) => onUploadAudio(index, event.target.files?.[0])} />
      </label>
      {draft.listenAudioSources[level][index] === "teacher" && draft.listenAudioUrls[level][index]?.trim() && <span className="teacher-form-hint">Teacher reference ready — student scoring will use this recording.</span>}
    </>
  </div>;
}

export default function StoryBuilderFrameEditor(props) {
  const { draft, validationErrors, onPasteImage } = props;
  const level = draft.activeLevel;
  return <div className="teacher-frame-editor">{draft.imageUrls.easy.map((_, index) => {
    const frameError = validationErrors.frames?.[index];
    const isExampleFrame = false;
    const imageUrl = draft.imageUrls[level][index];
    return <div className={`teacher-frame-card ${frameError ? "has-error" : ""}${isExampleFrame ? " is-example-frame" : ""}`} key={index}>
      <FramePreview draft={draft} index={index} imageUrl={imageUrl} onPaste={(event) => onPasteImage(index, event)} />
      <StoryFrameFields {...props} index={index} level={level} frameError={frameError} isExampleFrame={isExampleFrame} />
    </div>;
  })}</div>;
}
