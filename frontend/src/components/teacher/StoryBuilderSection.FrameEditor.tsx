// @ts-nocheck
import React from "react";
import { resolveImageUrl } from "../../utils/teacherStories";
import { splitScriptIntoChunks } from "../../utils/scriptAlignment";
import VocabularyTable from "../VocabularyTable";
import PhraseTable from "../PhraseTable";
import VocabGroupEditor from "../VocabGroupEditor";
import { GRAMMAR_CANVAS_ENABLED, PHRASE_COUNT_BY_LEVEL, STORY_FRAME_GUIDES } from "./StoryBuilderSection.helpers";

function FramePreview({ draft, index, imageUrl, onPaste }) {
  const guide = draft.narrativeMode === "story" ? STORY_FRAME_GUIDES[index] : null;
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

function SentenceActionGroup({ draft, index, vocabFillLoadingIndex, phraseFillLoadingIndex, onFillVocab, onFillPhrases }) {
  const count = PHRASE_COUNT_BY_LEVEL[draft.activeLevel];
  const hasSentence = Boolean(draft.suggestedAnswers[draft.activeLevel][index]?.trim());
  return <div className="teacher-sentence-tools">
    <button type="button" className="btn-vocab-autofill-sm" disabled={!hasSentence || vocabFillLoadingIndex === index}
      title="Fill the vocabulary table from this sentence" onClick={() => onFillVocab(index)}>
      {vocabFillLoadingIndex === index ? "Filling…" : "✨ Fill vocab"}
    </button>
    <button type="button" className="btn-vocab-autofill-sm" disabled={!hasSentence || phraseFillLoadingIndex === index}
      title={`Generate ${count} phrase${count > 1 ? "s" : ""} from this sentence`} onClick={() => onFillPhrases(index)}>
      {phraseFillLoadingIndex === index ? "Generating…" : `✨ +${count} phrase${count > 1 ? "s" : ""}`}
    </button>
  </div>;
}

function StoryFrameFields(props) {
  const { draft, index, level, frameError, isExampleFrame, updateDraftFrame, updateDraftGroups,
    onUploadImage, onUploadAudio, onFillVocab, onFillPhrases, vocabDraftGeneration,
    phraseDraftGeneration, vocabFillLoadingIndex, phraseFillLoadingIndex, vocabFillError,
    phraseFillError, recordingFrameIndex, recordingSeconds, onStartRecording, onStopRecording } = props;
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
    <VocabularyTable key={`${vocabDraftGeneration}-${index}-${level}`} vocabulary={draft.vocabulary[level][index] ?? ""}
      vocabularyPinyin={draft.vocabularyPinyin[level][index] ?? ""} vocabularyPos={draft.vocabularyPos[level][index] ?? ""}
      vocabularyTranslation={draft.vocabularyTranslation[level][index] ?? ""} onChangeColumn={(field, value) => updateDraftFrame(field, index, value)} />
    <PhraseTable key={`${phraseDraftGeneration}-phrases-${index}-${level}`} phrases={draft.phrases[level][index] ?? ""}
      phrasesTranslation={draft.phrasesTranslation[level][index] ?? ""} onChangeColumn={(field, value) => updateDraftFrame(field, index, value)} />
    {draft.narrativeMode !== "listen_retell" ? <>
      <label>{isExampleFrame ? "Example script (shown to students as a model — helps them know how to start)" : "Script"}
        <textarea value={draft.suggestedAnswers[level][index] ?? ""} onChange={(event) => updateDraftFrame("suggestedAnswers", index, event.target.value)}
          rows={isExampleFrame ? 4 : 2} placeholder={isExampleFrame ? "Write the model story text students will read before recording their own…" : "Write the sentence students should say. Their voice transcript will be compared with this script."} />
      </label>
      {!isExampleFrame && chunks.length > 1 && <p className="script-chunk-preview"><span className="script-chunk-preview-lead">Auto-detected parts (edit punctuation above to adjust):</span>{chunks.map((chunk, chunkIndex) => <span key={chunkIndex} className="script-chunk-preview-chip">{chunk}</span>)}</p>}
      <SentenceActionGroup draft={draft} index={index} vocabFillLoadingIndex={vocabFillLoadingIndex} phraseFillLoadingIndex={phraseFillLoadingIndex} onFillVocab={onFillVocab} onFillPhrases={onFillPhrases} />
      {vocabFillError && vocabFillLoadingIndex === null && <span className="teacher-form-error">{vocabFillError}</span>}
      {phraseFillError && phraseFillLoadingIndex === null && <span className="teacher-form-error">{phraseFillError}</span>}
      <label className="teacher-file-upload">Upload teacher reference audio (optional)
        <input type="file" accept="audio/mpeg,audio/wav,audio/webm,audio/ogg" onChange={(event) => onUploadAudio(index, event.target.files?.[0])} />
      </label>
      {draft.listenAudioSources[level][index] === "teacher" && draft.listenAudioUrls[level][index]?.trim() && <span className="teacher-form-hint">Teacher reference ready — student scoring will use this recording.</span>}
    </> : <>
      <label>Listening audio for "Listen & Retell" (optional)
        <input value={draft.listenAudioUrls[level][index] ?? ""} onChange={(event) => updateDraftFrame("listenAudioUrls", index, event.target.value)} placeholder="https://... or upload below" />
      </label>
      <label className="teacher-file-upload">Upload audio from computer
        <input type="file" accept="audio/mpeg,audio/wav,audio/webm,audio/ogg" onChange={(event) => onUploadAudio(index, event.target.files?.[0])} />
      </label>
      {recordingFrameIndex === index ? <button type="button" className="btn-vocab-autofill" onClick={onStopRecording}>⏹ Stop recording ({recordingSeconds}s)</button> : <button type="button" className="btn-vocab-autofill" disabled={recordingFrameIndex !== null} onClick={() => onStartRecording(index)}>🎙️ Record my own voice</button>}
      <label>Listening script (read aloud by text-to-speech if no audio is uploaded — not shown to students)
        <textarea value={draft.listenScripts[level][index] ?? ""} onChange={(event) => updateDraftFrame("listenScripts", index, event.target.value)} rows={4} placeholder="The passage students should listen to before retelling the story" />
      </label>
    </>}
    {GRAMMAR_CANVAS_ENABLED && <VocabGroupEditor vocabulary={draft.vocabulary[level][index]} groups={draft.vocabularyGroups[index]} onChange={(groups) => updateDraftGroups(index, groups)} />}
  </div>;
}

export default function StoryBuilderFrameEditor(props) {
  const { draft, validationErrors, onPasteImage } = props;
  const level = draft.activeLevel;
  return <div className="teacher-frame-editor">{draft.imageUrls.easy.map((_, index) => {
    const frameError = validationErrors.frames?.[index];
    const isExampleFrame = index === 0 && draft.firstFrameIsExample;
    const imageUrl = draft.imageUrls[level][index];
    return <div className={`teacher-frame-card ${frameError ? "has-error" : ""}${isExampleFrame ? " is-example-frame" : ""}`} key={index}>
      {isExampleFrame && <div className="teacher-example-badge">🎯 Teacher Model Example — students watch this before recording</div>}
      <FramePreview draft={draft} index={index} imageUrl={imageUrl} onPaste={(event) => onPasteImage(index, event)} />
      <StoryFrameFields {...props} index={index} level={level} frameError={frameError} isExampleFrame={isExampleFrame} />
    </div>;
  })}</div>;
}
