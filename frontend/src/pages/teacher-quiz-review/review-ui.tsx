// @ts-nocheck
import { BiLabel } from "../../components/BiLabel";
import { isExcluded } from "../../utils/quizExclusions";
import { isApproved } from "../../utils/quizPendingApprovals";
import { pendingKeyFor } from "./model-core";
import { PENDING_ORIGIN_LABELS, pendingDecisionCopy } from "./constants";
import { useQuizReviewContext } from "./context";
import { useQuizReviewActions } from "./review-actions";
import { useQuizGenerationActions } from "./generation-actions";
import { ReviewIcon, diffBadge, findValidation, questionStatusBadge, renderPendingDiff } from "./review-chrome";

export function useQuizReviewUi() {
  const ctx = useQuizReviewContext();
  const actions = useQuizReviewActions();
  const generation = useQuizGenerationActions();
  const { stories, level, exclusionsByStory, pendingApprovalsByKey, validationByStory, editTarget, setEditTarget, editDraft, setEditDraft, editStatus, addQuestionTarget, addQuestionDraft, setAddQuestionDraft, addQuestionStatus } = ctx;
  const { onToggle, canCheck, onToggleApproval, onStartEdit, onStartTranslationEdit, onCancelEdit, onSaveEdit, addDraftForKind, onCancelAddQuestion, onSaveAddQuestion, onDecideCandidate, onUndoDecision } = { ...actions, ...generation };
  const trashButton = (
    storyId: string,
    word: string,
    kind: QuizExclusionKind,
    index?: number,
  ) => {
    const exclusions = exclusionsByStory[storyId] ?? [];
    const marked = isExcluded(exclusions, word, kind, index);
    return (
      <button
        type="button"
        className={`tqr-trash${marked ? " is-marked" : ""}`}
        aria-pressed={marked}
        aria-label={`${marked ? "Restore" : "Exclude"} ${kind} for ${word}`}
        onClick={() => onToggle(storyId, index === undefined ? { word, kind } : { word, kind, index })}
      >
        <ReviewIcon name={marked ? "restore" : "trash"} size={16} />
      </button>
    );
  };

  const approvalCheckbox = (storyId: string, word: string, kind: QuizApprovalKind, poolIndex?: number) => {
    const approvals = pendingApprovalsByKey[pendingKeyFor(storyId, level)] ?? [];
    const checked = isApproved(approvals, word, kind, poolIndex);
    // A prior selection must not bypass a later failed validation. This can
    // happen when a teacher re-checks an item after its AI pool changed.
    const checkable = canCheck(storyId, word, kind, poolIndex);
    // The disabled reason must match reality: a question can be blocked
    // either because Validate hasn't run yet, or because it ran and flagged
    // the question suspicious — those need different guidance, not the same
    // generic "Validate first" for both.
    const result = findValidation(
      validationByStory[storyId],
      word,
      kind === "distractors" ? "translation" : kind,
      poolIndex,
    );
    if (!result) return null;
    const disabledTitle = checkable
      ? undefined
      : result
        ? "Suspicious — fix this question before approving it"
        : "Validate this question first";
    return (
      <input
        type="checkbox"
        className="tqr-approve-checkbox"
        checked={checked}
        disabled={!checkable}
        title={disabledTitle}
        aria-label={`Approve ${kind} for ${word}`}
        onChange={() => {
          const story = stories.find((s) => s.id === storyId);
          if (story) onToggleApproval(story, { word, kind, index: poolIndex });
        }}
      />
    );
  };

  const editButton = (target: EditTarget, current: { distractors: string[]; sentence?: string; synonym?: string }) => (
    <button type="button" className="tqr-edit" onClick={() => onStartEdit(target, current)}>
      <ReviewIcon name="edit" size={15} />
      <BiLabel zh="編輯" en="Edit" />
    </button>
  );

  const editForm = () => {
    if (!editDraft) return null;
    return (
      <div className="tqr-edit-form">
        {editDraft.kind === "translation" && (
          <label>
            <BiLabel zh="正確答案" en="Correct answer" />
            <input
              type="text"
              value={editDraft.translation}
              onChange={(e) => setEditDraft({ kind: "translation", translation: e.target.value })}
            />
          </label>
        )}
        {editDraft.kind === "distractors" && editDraft.correctAnswer !== undefined && (
          <label>
            <BiLabel zh="正確答案" en="Correct answer" />
            <input type="text" value={editDraft.correctAnswer} onChange={(e) => setEditDraft({ ...editDraft, correctAnswer: e.target.value })} />
          </label>
        )}
        {editDraft.kind === "cloze" && (
          <label>
            <BiLabel zh="句子" en="Sentence" />
            <input
              type="text"
              lang="zh-Hant"
              value={editDraft.sentence}
              onChange={(e) => setEditDraft({ ...editDraft, sentence: e.target.value })}
            />
          </label>
        )}
        {editDraft.kind === "synonym" && (
          <label>
            <BiLabel zh="同義詞" en="Synonym" />
            <input
              type="text"
              lang="zh-Hant"
              value={editDraft.synonym}
              onChange={(e) => setEditDraft({ ...editDraft, synonym: e.target.value })}
            />
          </label>
        )}
        {editDraft.kind === "pinyin" && (
          <label>
            <BiLabel zh="拼音" en="Pinyin" />
            <input
              type="text"
              value={editDraft.pinyin}
              onChange={(e) => setEditDraft({ kind: "pinyin", pinyin: e.target.value })}
            />
          </label>
        )}
        {editDraft.kind !== "translation" && editDraft.kind !== "pinyin" && <label>
          <BiLabel zh="錯誤選項（逗號分隔）" en="Wrong options (comma-separated)" />
          <input
            type="text"
            value={editDraft.distractors}
            onChange={(e) => setEditDraft({ ...editDraft, distractors: e.target.value })}
          />
        </label>}
        <div className="tqr-edit-actions">
          <button type="button" className="tqr-io" onClick={onCancelEdit}>
            <BiLabel zh="取消" en="Cancel" />
          </button>
          {editStatus !== "saving" ? (
            <button type="button" className="tqr-save" onClick={onSaveEdit}>
              <BiLabel zh="儲存並重新驗證" en="Save (needs re-validation)" />
            </button>
          ) : (
            <span className="tqr-status-progress"><BiLabel zh="儲存中…" en="Saving…" /></span>
          )}
        </div>
        {editStatus === "error" && (
          <span className="tqr-status-error" role="alert">
            <BiLabel zh="儲存失敗" en="Save failed" />
          </span>
        )}
      </div>
    );
  };

  const isEditing = (target: Omit<EditTarget, "storyId" | "frameIndex" | "wordIndex">, storyId: string) =>
    editTarget?.storyId === storyId &&
    editTarget.word === target.word &&
    editTarget.kind === target.kind &&
    (editTarget.poolIndex ?? undefined) === (target.poolIndex ?? undefined);

  /** Renders one assembled question — prompt, options with the correct
   * answer highlighted, status badge, checkbox, and Edit — instead of the
   * raw pool text a teacher would otherwise have to parse themselves. The
   * first entry in `options` is always the correct answer. */
  const questionRow = (spec: {
    storyId: string;
    frameIndex: number;
    wordIndex: number;
    word: string;
    kind: QuizApprovalKind;
    poolIndex?: number;
    kindLabel: { zh: string; en: string };
    promptZh: string;
    promptEn: string;
    options: string[];
    translationField?: TranslationField;
    editValue: { distractors: string[]; sentence?: string; synonym?: string; correctAnswer?: string };
    diffStatus: MaterialDiffStatus | undefined;
  }) => {
    const result = findValidation(
      validationByStory[spec.storyId],
      spec.word,
      spec.kind === "distractors" ? "translation" : spec.kind,
      spec.poolIndex,
    );
    return (
      <div className="tqr-qrow diff-row row-ctx" key={`${spec.kind}-${spec.poolIndex ?? 0}`}>
        <span className="gutter tqr-q-select">
          {approvalCheckbox(spec.storyId, spec.word, spec.kind, spec.poolIndex)}
        </span>
        <span className="tqr-qkind">
          {diffBadge(spec.diffStatus)}
          <BiLabel zh={spec.kindLabel.zh} en={spec.kindLabel.en} />
          {spec.poolIndex !== undefined && ` #${spec.poolIndex + 1}`}
        </span>
        <div className="diff-content tqr-qbody">
          <p className="tqr-qprompt" lang="zh-Hant">
            {spec.promptZh}
            <br />
            <span className="tqr-qprompt-en">{spec.promptEn}</span>
          </p>
          <div className="tqr-qoptions">
            {spec.options.map((opt, i) => (
              <span key={i} className={`tqr-opt${i === 0 ? " is-correct" : ""}`}>
                {opt}
              </span>
            ))}
          </div>
        </div>
        <div className="tqr-q-status">
          {questionStatusBadge(result)}
        </div>
        <div className="diff-actions tqr-q-actions">
          {questionDeleteButton(spec.storyId, spec.word, spec.kind, spec.poolIndex)}
          {editButton(
            {
              storyId: spec.storyId,
              frameIndex: spec.frameIndex,
              wordIndex: spec.wordIndex,
              word: spec.word,
              kind: spec.kind,
              poolIndex: spec.poolIndex,
              translationField: spec.translationField,
            },
            spec.editValue,
          )}
        </div>
        {isEditing({ word: spec.word, kind: spec.kind, poolIndex: spec.poolIndex }, spec.storyId) && editForm()}
      </div>
    );
  };

  const addQuestionForm = () => {
    if (!addQuestionTarget || !addQuestionDraft) return null;
    return (
      <div className="tqr-add-form" aria-label="Add quiz question">
        <div className="tqr-add-form-heading">
          <ReviewIcon name="add" size={16} />
          <BiLabel zh="新增題目" en="Add question" />
        </div>
        <label>
          <BiLabel zh="題型" en="Question type" />
          <select
            value={addQuestionDraft.kind}
            onChange={(event) => setAddQuestionDraft(addDraftForKind(event.target.value as AddQuestionKind))}
          >
            {addQuestionTarget.availableKinds.map((kind) => (
              <option key={kind} value={kind}>
                {kind === "distractors" ? "翻譯 Translation" : kind === "cloze" ? "填空 Cloze" : "同義詞 Synonym"}
              </option>
            ))}
          </select>
        </label>
        {addQuestionDraft.kind === "cloze" && (
          <label>
            <BiLabel zh="句子（必須包含目標詞）" en="Sentence (must include the word)" />
            <input
              type="text"
              lang="zh-Hant"
              value={addQuestionDraft.sentence}
              onChange={(event) => setAddQuestionDraft({ ...addQuestionDraft, sentence: event.target.value })}
            />
          </label>
        )}
        {addQuestionDraft.kind === "synonym" && (
          <label>
            <BiLabel zh="同義詞" en="Synonym" />
            <input
              type="text"
              lang="zh-Hant"
              value={addQuestionDraft.synonym}
              onChange={(event) => setAddQuestionDraft({ ...addQuestionDraft, synonym: event.target.value })}
            />
          </label>
        )}
        <label>
          <BiLabel zh="錯誤選項（逗號分隔）" en="Wrong options (comma-separated)" />
          <input
            type="text"
            value={addQuestionDraft.distractors}
            onChange={(event) => setAddQuestionDraft({ ...addQuestionDraft, distractors: event.target.value })}
          />
        </label>
        <div className="tqr-edit-actions">
          <button type="button" className="tqr-io" onClick={onCancelAddQuestion}>
            <BiLabel zh="取消" en="Cancel" />
          </button>
          {addQuestionStatus !== "saving" ? (
            <button type="button" className="tqr-save" onClick={onSaveAddQuestion}>
              <ReviewIcon name="add" size={15} />
              <BiLabel zh="新增題目" en="Add question" />
            </button>
          ) : (
            <span className="tqr-status-progress"><BiLabel zh="新增中…" en="Adding…" /></span>
          )}
        </div>
        {addQuestionStatus === "error" && (
          <span className="tqr-status-error" role="alert">
            <BiLabel zh="請填寫完整題目內容與錯誤選項" en="Complete the question and add at least one wrong option" />
          </span>
        )}
      </div>
    );
  };

  const onStartPinyinEdit = (target: EditTarget, pinyin: string) => {
    setEditTarget(target);
    setEditDraft({ kind: "pinyin", pinyin });
    setEditStatus("idle");
  };

  const questionDeleteButton = (
    storyId: string,
    word: string,
    kind: QuizApprovalKind | BuiltInQuestionKind,
    index?: number,
  ) => {
    const exclusions = exclusionsByStory[storyId] ?? [];
    const exclusionKind: QuizExclusionKind = kind === "distractors" ? "distractors" : kind;
    const marked = isExcluded(exclusions, word, exclusionKind, index);
    const questionName = kind === "distractors" ? "translation" : kind;
    const exclusion = index === undefined
      ? { word, kind: exclusionKind }
      : { word, kind: exclusionKind, index };

    return (
      <button
        type="button"
        className={`tqr-trash tqr-question-delete${marked ? " is-marked" : ""}`}
        aria-pressed={marked}
        aria-label={`${marked ? "Restore" : "Delete"} ${questionName} question for ${word}`}
        title={`${marked ? "Restore" : "Delete"} this ${questionName} question`}
        onClick={() => {
          if (!marked && typeof window !== "undefined") {
            const confirmed = window.confirm(
              `Delete this ${questionName} question for ${word}? You can restore it before saving.`,
            );
            if (!confirmed) return;
          }
          onToggle(storyId, exclusion);
        }}
      >
        <ReviewIcon name={marked ? "restore" : "trash"} size={16} />
      </button>
    );
  };

  /** Renders a deterministic question preview. Built-in questions use the
   * same row actions as generated questions: teachers can edit their source
   * value or exclude/restore the question before saving. */
  const builtInQuestionRow = (spec: {
    key: string;
    storyId: string;
    frameIndex: number;
    wordIndex: number;
    word: string;
    kind: BuiltInQuestionKind;
    kindLabel: { zh: string; en: string };
    promptZh: string;
    promptEn: string;
    options: string[];
    pinyin?: string;
    pinyinField?: PinyinField;
    translation?: string;
    translationField?: TranslationField;
  }) => (
    <div className="tqr-qrow diff-row row-ctx" key={spec.key}>
      <span className="gutter tqr-q-select" aria-hidden="true" />
      <span className="tqr-qkind">
        <BiLabel zh={spec.kindLabel.zh} en={spec.kindLabel.en} />
      </span>
      <div className="diff-content tqr-qbody">
        <p className="tqr-qprompt" lang="zh-Hant">
          {spec.promptZh}
          <br />
          <span className="tqr-qprompt-en">{spec.promptEn}</span>
        </p>
        <div className="tqr-qoptions">
          {spec.options.map((opt, i) => (
            <span key={i} className={`tqr-opt${i === 0 ? " is-correct" : ""}`}>
              {i === 0 ? "✓ " : "· "}{opt}
            </span>
          ))}
        </div>
      </div>
      <div className="tqr-q-status" aria-hidden="true" />
      <div className="diff-actions tqr-q-actions">
        {questionDeleteButton(spec.storyId, spec.word, spec.kind)}
        <button
          type="button"
          className="tqr-edit"
          onClick={() => {
            if (spec.kind === "pinyin") {
              onStartPinyinEdit(
                {
                  storyId: spec.storyId,
                  frameIndex: spec.frameIndex,
                  wordIndex: spec.wordIndex,
                  word: spec.word,
                  kind: "pinyin",
                  pinyinField: spec.pinyinField,
                },
                spec.pinyin ?? "",
              );
            } else {
              onStartTranslationEdit(
                {
                  storyId: spec.storyId,
                  frameIndex: spec.frameIndex,
                  wordIndex: spec.wordIndex,
                  word: spec.word,
                  kind: "translation",
                  translationField: spec.translationField,
                },
                spec.translation ?? "",
              );
            }
          }}
        >
          <ReviewIcon name="edit" size={15} />
          <BiLabel zh="編輯" en="Edit" />
        </button>
      </div>
      {spec.kind === "pinyin" && isEditing({ word: spec.word, kind: "pinyin" }, spec.storyId) && editForm()}
    </div>
  );

  const pendingDecisionActions = (storyId: string, candidate: PendingCandidate, index: number) => {
    if (candidate.decision === "pending") {
      return (
        <div className="tqr-pending-decide">
          <button
            type="button"
            className="tqr-icon-btn accept"
            aria-label="Accept"
            title="Accept"
            onClick={() => onDecideCandidate(storyId, index, "accept")}
          >
            <ReviewIcon name="accept" size={16} />
          </button>
          <button
            type="button"
            className="tqr-icon-btn reject"
            aria-label="Reject"
            title="Reject"
            onClick={() => onDecideCandidate(storyId, index, "reject")}
          >
            <ReviewIcon name="reject" size={16} />
          </button>
        </div>
      );
    }
    return (
      <div className="tqr-pending-decided">
        <span className={`tqr-decision-tag ${candidate.decision === "accept" ? "is-accept" : "is-reject"}`}>
          {candidate.decision === "accept" ? "✓ " : "× "}
          <BiLabel
            zh={pendingDecisionCopy(candidate.origin, candidate.decision).zh}
            en={pendingDecisionCopy(candidate.origin, candidate.decision).en}
          />
        </span>
        <button type="button" className="undo-link" onClick={() => onUndoDecision(storyId, index)}>
          <BiLabel zh="復原" en="Undo" />
        </button>
      </div>
    );
  };

  const pendingCandidateRows = (storyId: string, entries: IndexedPendingCandidate[]) =>
    entries.map(({ candidate, index }) => (
      <div
        className={`tqr-pending-change is-${candidate.origin}${candidate.decision === "reject" ? " is-rejected" : ""}`}
        key={`${candidate.word}-${candidate.kind}-${index}`}
      >
        {renderPendingDiff(candidate, pendingDecisionActions(storyId, candidate, index))}
      </div>
    ));

  const changeChip = (count: number, hasRemoved = false) => (
    count > 0 ? (
      <span className={`tqr-change-chip ${hasRemoved ? "is-mix" : "is-add"}`}>
        <BiLabel zh={`${count} 項變更`} en={`${count} ${count === 1 ? "change" : "changes"}`} />
      </span>
    ) : null
  );
  return { trashButton, approvalCheckbox, editButton, editForm, isEditing, questionRow, addQuestionForm, builtInQuestionRow, pendingCandidateRows, changeChip };
}
