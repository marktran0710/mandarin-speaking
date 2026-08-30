// @ts-nocheck
import { BiLabel } from "../../components/BiLabel";
import { buildApprovedMaterial } from "../../utils/quizApprovedMaterial";
import { diffWord } from "../../utils/quizMaterialDiff";
import { isExcluded } from "../../utils/quizExclusions";
import { translationFieldForLevel, pinyinFieldForLevel, reviewOptions } from "./model-core";
import { PENDING_KIND_LABELS } from "./constants";
import StudentIcon from "../../components/StudentIcon";
import { ReviewActionRail, ReviewIcon, diffBadge, findValidation, questionStatusBadge } from "./review-chrome";
import { useQuizReviewContext } from "./context";
import { useQuizReviewActions } from "./review-actions";
import { useQuizGenerationActions } from "./generation-actions";
import { useQuizReviewUi } from "./review-ui";
import { useQuizReviewStoryState } from "./story-state";

export function QuizReviewStory({ story }) {
  const ctx = useQuizReviewContext();
  const actions = useQuizReviewActions();
  const generation = useQuizGenerationActions();
  const ui = useQuizReviewUi();
  const state = useQuizReviewStoryState(story);
  const { level, generationGateNoteByStory, validationByStory, addQuestionTarget } = ctx;
  const { onSave, onValidate, onApprove, onApproveAll, onStartTranslationEdit, onStartAddQuestion } = actions;
  const { onGenerate, onExport, triggerImport, onApplyPendingCandidates, onAcceptAllPending } = generation;
  const { trashButton, isEditing, editForm, addQuestionForm, questionRow, builtInQuestionRow, pendingCandidateRows, changeChip } = ui;
  const { topic, exclusions, dirty, status, snapshot, importNote, validateStatus, approveStatus, validation, approvals, approvedCount, generateStatus, pendingCandidates, revealedCount, pendingByWord, removedPendingGroups, hasAnyMaterial, pendingDecidedCount, pendingAcceptedCount, isGenerating, isValidating, isPublishing, isSavingMarks, canApproveAll, canApplyPending, hasSuspiciousQuestions, canGenerate, canValidate, showActionRail, renderedWords, builtInWords, builtInByWord } = state;
          return (
            <section className="tqr-story" key={story.id}>
              <div className={`tqr-workspace${showActionRail ? "" : " is-single"}`}>
                <div className="tqr-review-panel">
                  <header className="tqr-story-actions">
                    <div className="tqr-toolbar-primary">
                      <h2 className="tqr-panel-story-title">{story.title}</h2>
                      {canGenerate && !isGenerating ? (
                        <button
                          type="button"
                          className="tqr-generate"
                          title="Create a new draft, or refresh only questions affected by story changes. Students cannot see a draft."
                          onClick={() => onGenerate(story, topic)}
                        >
                          <ReviewIcon name="generate" />
                          {hasAnyMaterial ? (
                            <BiLabel zh="更新題目" en="Update Questions" />
                          ) : (
                            <BiLabel zh="生成題目" en="Generate Questions" />
                          )}
                        </button>
                      ) : isGenerating ? (
                        <span className="tqr-status-progress" role="status">
                          {generateStatus === "applying" ? <BiLabel zh="套用中…" en="Applying…" /> : <BiLabel zh="生成中…" en="Generating…" />}
                        </span>
                      ) : null}
                      <div className="tqr-toolbar-status" aria-live="polite">
                        {generateStatus === "error" && (
                          <span className="tqr-status-error" role="alert">
                            <BiLabel zh="生成失敗，請稍後再試" en="Generate failed. Try again in a moment" />
                          </span>
                        )}
                        {validateStatus === "error" && (
                          <span className="tqr-status-error" role="alert">
                            <BiLabel zh="檢查失敗" en="Validate failed" />
                          </span>
                        )}
                      </div>
                      <details className="tqr-more-tools tqr-toolbar-more">
                        <summary><BiLabel zh="更多" en="More" /></summary>
                        <div className="tqr-rail-utilities">
                          {canValidate && !isValidating && (
                            <button
                              type="button"
                              className="tqr-io"
                              title="Validate the current draft for duplicate or unsafe answers before selecting questions to publish."
                              onClick={() => onValidate(story, topic)}
                            >
                              <ReviewIcon name="validate" />
                              <BiLabel zh="驗證題目" en="Validate Questions" />
                            </button>
                          )}
                          {isValidating && (
                            <span className="tqr-status-progress" role="status">
                              <BiLabel zh="驗證中…" en="Validating…" />
                            </span>
                          )}
                          <button type="button" className="tqr-io" onClick={() => onExport(story)}>
                            <ReviewIcon name="export" />
                            <BiLabel zh="匯出" en="Export" />
                          </button>
                          <button type="button" className="tqr-io" onClick={() => triggerImport(story.id)}>
                            <ReviewIcon name="import" />
                            <BiLabel zh="匯入" en="Import" />
                          </button>
                        </div>
                      </details>
                    </div>
                  </header>
                  {importNote && <p className="tqr-import-note" role="status">{importNote}</p>}
                  {generationGateNoteByStory[story.id] && (
                    <p className="tqr-import-note" role="status">
                      {generationGateNoteByStory[story.id]}
                    </p>
                  )}

                  {generateStatus === "generating" && (
                    <div className="tqr-generate-spinner" role="status">
                      <span className="tqr-spinner" aria-hidden="true" />
                      <BiLabel zh="正在生成題目…" en="Generating questions…" />
                    </div>
                  )}

                  <div className="tqr-table-head" aria-hidden="true">
                    <span />
                    <span><BiLabel zh="題型" en="Type" /></span>
                    <span><BiLabel zh="題目內容／答案" en="Question / answer" /></span>
                    <span><BiLabel zh="驗證狀態" en="Validation" /></span>
                    <span><BiLabel zh="操作" en="Actions" /></span>
                  </div>

              {topic.images.map((_, si) => {
                const words = (topic.vocabulary[si] || [])
                  .map((word, wordIndex) => ({ word, wordIndex }))
                  .filter(({ word }) => {
                    if (renderedWords.has(word)) return false;
                    renderedWords.add(word);
                    return true;
                  });
                if (words.length === 0) return null;
                return (
                  <section className="tqr-scene" key={si}>
                    <h3 className="tqr-scene-title">
                      <BiLabel zh={`部分 ${si + 1}`} en={`Scene ${si + 1}`} />
                    </h3>
                    {words.map(({ word, wordIndex: wi }) => {
                      const wordGone = isExcluded(exclusions, word, "word");
                      const pinyin = topic.vocabularyPinyin?.[si]?.[wi];
                      const pos = topic.vocabularyPos?.[si]?.[wi];
                      const translation = topic.vocabularyTranslation?.[si]?.[wi];
                      const translationField = translationFieldForLevel(story.frames[si], level);
                      const translationCheck = findValidation(validationByStory[story.id], word, "translation");
                      const distractors = topic.vocabularyDistractors?.[si]?.[wi] ?? [];
                      const cloze = (topic.vocabularyCloze?.[si]?.[wi] ?? []).slice(0, 1);
                      const synonyms = (topic.vocabularySynonym?.[si]?.[wi] ?? []).slice(0, 1);
                      const availableAddKinds: AddQuestionKind[] = [
                        ...(distractors.length === 0 ? ["distractors" as const] : []),
                        ...(cloze.length === 0 ? ["cloze" as const] : []),
                        ...(synonyms.length === 0 ? ["synonym" as const] : []),
                      ];
                      const builtIn = builtInByWord.get(word);
                      const pinyinOptions = builtIn
                        ? reviewOptions(
                            builtIn.pinyin,
                            builtInWords
                              .filter((entry) => entry.word !== word && entry.pinyin !== builtIn.pinyin)
                              .map((entry) => entry.pinyin),
                          )
                        : [];
                      const reverseOptions = builtIn
                        ? reviewOptions(
                            builtIn.word,
                            builtInWords
                              .filter(
                                (entry) =>
                                  entry.word !== word &&
                                  entry.translation.toLowerCase() !== builtIn.translation.toLowerCase(),
                              )
                              .map((entry) => entry.word),
                          )
                        : [];
                      const diff = diffWord(word, { distractors, cloze, synonym: synonyms }, snapshot);
                      const wordPending = (pendingByWord.get(word) ?? []).filter(
                        ({ candidate, index }) => candidate.origin !== "removed" && index < revealedCount,
                      );
                      return (
                        <article
                          className={`tqr-word-file${wordGone ? " is-word-gone" : ""}`}
                          key={`${word}-${wi}`}
                        >
                          <header className="tqr-word-head">
                            <span className="tqr-word-chev"><ReviewIcon name="chevron" size={15} /></span>
                            <strong lang="zh-Hant">{word}</strong>
                            {pinyin && <span className="tqr-pinyin">{pinyin}</span>}
                            {pos && <span className="tqr-pos">{pos}</span>}
                            {translation ? (
                              <span className="tqr-translation"><StudentIcon name="arrow-right" size={14} aria-hidden="true" /> {translation}</span>
                            ) : (
                              <span className="tqr-no-quiz">
                                <BiLabel zh="沒有翻譯，不會出題" en="No translation — never quizzed" />
                              </span>
                            )}
                            {translation && distractors.length === 0 && (
                              <button
                                type="button"
                                className="tqr-edit tqr-edit-answer"
                                onClick={() =>
                                  onStartTranslationEdit(
                                    {
                                      storyId: story.id,
                                      frameIndex: si,
                                      wordIndex: wi,
                                      word,
                                      kind: "translation",
                                      translationField,
                                    },
                                    translation,
                                  )
                                }
                              >
                                <BiLabel zh="編輯答案" en="Edit answer" />
                              </button>
                            )}
                            {translation && distractors.length === 0 && translationCheck && (
                              <span className="tqr-answer-check">
                                <BiLabel zh="答案檢查" en="Answer check" />
                                {questionStatusBadge(translationCheck)}
                              </span>
                            )}
                            {translation && !wordGone && availableAddKinds.length > 0 && (
                              <button
                                type="button"
                                className="tqr-add-question"
                                aria-label={`Add question for ${word}`}
                                onClick={() =>
                                  onStartAddQuestion({
                                    storyId: story.id,
                                    frameIndex: si,
                                    wordIndex: wi,
                                    word,
                                    availableKinds: availableAddKinds,
                                  })
                                }
                              >
                                <ReviewIcon name="add" size={15} />
                                <BiLabel zh="新增題目" en="Add question" />
                              </button>
                            )}
                            {translation && trashButton(story.id, word, "word")}
                            <span className="tqr-word-head-spacer" />
                            {diffBadge(diff?.status)}
                            {changeChip(wordPending.length)}
                          </header>
                          {isEditing({ word, kind: "translation" }, story.id) && editForm()}
                          {addQuestionTarget?.storyId === story.id &&
                            addQuestionTarget.frameIndex === si &&
                            addQuestionTarget.wordIndex === wi &&
                            addQuestionForm()}
                          {!wordGone && translation && (
                            <div className="tqr-pools">
                              {distractors.length > 0 &&
                                questionRow({
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "distractors",
                                  kindLabel: { zh: "翻譯", en: "Translation" },
                                  promptZh: `「${word}」是什麼意思？`,
                                  promptEn: `What does "${word}" mean?`,
                                  options: [translation, ...distractors],
                                  translationField,
                                  editValue: { distractors, correctAnswer: translation },
                                  diffStatus: diff?.distractorsStatus,
                                })}
                              {cloze.map((c, ci) =>
                                questionRow({
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "cloze",
                                  poolIndex: ci,
                                  kindLabel: { zh: "填空", en: "Cloze" },
                                  promptZh: c.sentence.replace(word, "＿＿＿"),
                                  promptEn: "Which word fills the blank?",
                                  options: [word, ...c.distractors],
                                  editValue: { sentence: c.sentence, distractors: c.distractors },
                                  diffStatus: diff?.clozeStatus[ci],
                                }),
                              )}
                              {synonyms.map((s, syi) =>
                                questionRow({
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "synonym",
                                  poolIndex: syi,
                                  kindLabel: { zh: "同義詞", en: "Synonym" },
                                  promptZh: `哪一個字跟「${word}」意思一樣？`,
                                  promptEn: `Which word means the same as "${word}"?`,
                                  options: [s.synonym, ...s.distractors],
                                  editValue: { synonym: s.synonym, distractors: s.distractors },
                                  diffStatus: diff?.synonymStatus[syi],
                                }),
                              )}
                              {pinyinOptions.length > 1 &&
                                builtInQuestionRow({
                                  key: "pinyin",
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "pinyin",
                                  kindLabel: { zh: "拼音", en: "Pinyin" },
                                  promptZh: `「${word}」的拼音是什麼？`,
                                  promptEn: `What is the pinyin for "${word}"?`,
                                  options: pinyinOptions,
                                  pinyin: builtIn?.pinyin,
                                  pinyinField: pinyinFieldForLevel(story.frames[si], level),
                                })}
                              {reverseOptions.length > 1 &&
                                builtInQuestionRow({
                                  key: "reverse",
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "reverse",
                                  kindLabel: { zh: "反向翻譯", en: "Reverse translation" },
                                  promptZh: `哪一個詞是「${builtIn?.translation ?? translation}」？`,
                                  promptEn: `Which word means "${builtIn?.translation ?? translation}"?`,
                                  options: reverseOptions,
                                  translation: builtIn?.translation ?? translation,
                                  translationField,
                                })}
                              {pendingCandidateRows(story.id, wordPending)}
                            </div>
                          )}
                        </article>
                      );
                    })}
                  </section>
                );
              })}
              {removedPendingGroups.some(({ entries }) => entries.some(({ index }) => index < revealedCount)) && (
                <section className="tqr-removed-section">
                  <h3 className="tqr-scene-title">
                    <BiLabel zh="已從場景移除" en="Removed from scene" />
                  </h3>
                  {removedPendingGroups.map(({ word, entries }) => {
                    const visibleEntries = entries.filter(({ index }) => index < revealedCount);
                    if (visibleEntries.length === 0) return null;
                    return (
                      <article className="tqr-word-file is-removed-word" key={`removed-${word}`}>
                        <header className="tqr-word-head">
                          <span className="tqr-word-chev"><ReviewIcon name="chevron" size={15} /></span>
                          <strong lang="zh-Hant">{word}</strong>
                          <span className="tqr-no-quiz">
                            <BiLabel zh="已從場景移除" en="removed from scene" />
                          </span>
                          <span className="tqr-word-head-spacer" />
                          {changeChip(visibleEntries.length, true)}
                        </header>
                        <div className="tqr-pools">{pendingCandidateRows(story.id, visibleEntries)}</div>
                      </article>
                    );
                  })}
                </section>
              )}
                </div>

                {showActionRail && <ReviewActionRail
                  storyTitle={story.title}
                  checkedCount={approvedCount}
                  markedCount={exclusions.length}
                  changeCount={pendingCandidates.length}
                >
                  <div className="tqr-rail-primary" aria-live="polite">
                    {approvedCount > 0 && !isPublishing && (
                      <button
                        type="button"
                        className="tqr-approve"
                        title="Publish the checked questions as the version students receive."
                        onClick={() => onApprove(story, topic)}
                      >
                        <ReviewIcon name="publish" size={20} />
                        <BiLabel zh="核准並發佈" en="Approve & Publish" />
                      </button>
                    )}
                    {isPublishing && (
                      <span className="tqr-status-progress" role="status">
                        <BiLabel zh="發佈中…" en="Publishing…" />
                      </span>
                    )}
                    {approveStatus === "approved" && (
                      <span className="tqr-status-ok">
                        <ReviewIcon name="accept" size={16} />
                        <BiLabel zh="已發佈" en="Published" />
                      </span>
                    )}
                    {approveStatus === "error" && (
                      <span className="tqr-status-error" role="alert">
                        <BiLabel zh="發佈失敗" en="Publish failed" />
                      </span>
                    )}
                  </div>

                  {canApproveAll && (
                    <button type="button" className="tqr-rail-button" onClick={() => onApproveAll(story)}>
                      <ReviewIcon name="accept" />
                      <BiLabel zh="核准全部乾淨題目" en="Approve all clean" />
                    </button>
                  )}

                  {dirty && !isSavingMarks && (
                    <button
                      type="button"
                      className="tqr-save tqr-rail-button"
                      onClick={() => onSave(story, topic)}
                    >
                      <ReviewIcon name="save" />
                      <BiLabel zh="儲存標記" en="Save marks" />
                    </button>
                  )}
                  {isSavingMarks && (
                    <span className="tqr-status-progress" role="status">
                      <BiLabel zh="儲存中…" en="Saving…" />
                    </span>
                  )}
                  {status === "saved" && !dirty && (
                    <span className="tqr-status-ok">
                      <ReviewIcon name="accept" size={16} />
                      <BiLabel zh="已儲存" en="Saved" />
                    </span>
                  )}
                  {status === "error" && (
                    <span className="tqr-status-error" role="alert">
                      <BiLabel zh="儲存失敗" en="Save failed" />
                    </span>
                  )}

                  {pendingCandidates.length > 0 && (
                    <div className="tqr-decision-bar">
                      <span>
                        {pendingDecidedCount === pendingCandidates.length ? (
                          <BiLabel
                            zh={`已決定全部 ${pendingCandidates.length} 項`}
                            en={`All ${pendingCandidates.length} changes decided`}
                          />
                        ) : (
                          <BiLabel
                            zh={`已決定 ${pendingDecidedCount} / ${pendingCandidates.length} 項`}
                            en={`${pendingDecidedCount} of ${pendingCandidates.length} changes decided`}
                          />
                        )}
                      </span>
                      <span className="tqr-decision-actions">
                        {pendingDecidedCount < pendingCandidates.length && (
                          <button type="button" className="tqr-io" onClick={() => onAcceptAllPending(story.id)}>
                            <BiLabel zh="全部接受" en="Accept All" />
                          </button>
                        )}
                        {canApplyPending && generateStatus !== "applying" && (
                          <button
                            type="button"
                            className="tqr-approve"
                            onClick={() => onApplyPendingCandidates(story)}
                          >
                            <BiLabel zh={`套用變更（${pendingAcceptedCount}）`} en={`Apply Changes (${pendingAcceptedCount})`} />
                          </button>
                        )}
                        {generateStatus === "applying" && (
                          <span className="tqr-status-progress" role="status">
                            <BiLabel zh="套用中…" en="Applying…" />
                          </span>
                        )}
                      </span>
                    </div>
                  )}

                </ReviewActionRail>}
              </div>
            </section>
          );
}
