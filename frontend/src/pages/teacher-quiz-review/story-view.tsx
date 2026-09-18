// @ts-nocheck
import { BiLabel } from "../../components/BiLabel";
import { diffWord } from "../../utils/quizMaterialDiff";
import { isExcluded } from "../../utils/quizExclusions";
import { translationFieldForLevel, pinyinFieldForLevel, reviewOptions } from "./model-core";
import StudentIcon from "../../components/StudentIcon";
import { ReviewActionRail, ReviewIcon, diffBadge } from "./review-chrome";
import { useQuizReviewContext } from "./context";
import { useQuizReviewActions } from "./review-actions";
import { useQuizReviewUi } from "./review-ui";
import { useQuizReviewStoryState } from "./story-state";

export function QuizReviewStory({ story }) {
  const ctx = useQuizReviewContext();
  const actions = useQuizReviewActions();
  const ui = useQuizReviewUi();
  const state = useQuizReviewStoryState(story);
  const { level, addQuestionTarget } = ctx;
  const { onSave, onApprove, onApproveAll, onStartTranslationEdit, onStartAddQuestion, onExport, triggerImport, triggerMaterialUpload } = actions;
  const { trashButton, isEditing, editForm, addQuestionForm, questionRow, builtInQuestionRow } = ui;
  const { topic, exclusions, dirty, status, snapshot, importNote, uploadNote, approveStatus, approvedCount, hasAnyMaterial, isPublishing, isSavingMarks, canApproveAll, showActionRail, renderedWords, builtInWords, builtInByWord } = state;
          return (
            <section className="tqr-story" key={story.id}>
              <div className={`tqr-workspace${showActionRail ? "" : " is-single"}`}>
                <div className="tqr-review-panel">
                  <header className="tqr-story-actions">
                    <div className="tqr-toolbar-primary">
                      <h2 className="tqr-panel-story-title">{story.title}</h2>
                      <button
                        type="button"
                        className="tqr-generate"
                        title="Upload a CSV of quiz questions for this story (word, kind, text, distractors)."
                        onClick={() => triggerMaterialUpload(story.id)}
                      >
                        <ReviewIcon name="upload" />
                        <BiLabel zh="上傳題目" en="Upload Questions" />
                      </button>
                      <details className="tqr-more-tools tqr-toolbar-more">
                        <summary><BiLabel zh="更多" en="More" /></summary>
                        <div className="tqr-rail-utilities">
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
                  {uploadNote && <p className="tqr-import-note" role="status">{uploadNote}</p>}

                  <div className="tqr-table-head" aria-hidden="true">
                    <span />
                    <span><BiLabel zh="題型" en="Type" /></span>
                    <span><BiLabel zh="題目內容／答案" en="Question / answer" /></span>
                    <span />
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
                            </div>
                          )}
                        </article>
                      );
                    })}
                  </section>
                );
              })}
                </div>

                {showActionRail && <ReviewActionRail
                  storyTitle={story.title}
                  checkedCount={approvedCount}
                  markedCount={exclusions.length}
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
                    <button type="button" className="tqr-rail-button" onClick={() => onApproveAll(story, topic)}>
                      <ReviewIcon name="accept" />
                      <BiLabel zh="核准全部題目" en="Approve all" />
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

                </ReviewActionRail>}
              </div>
            </section>
          );
}
