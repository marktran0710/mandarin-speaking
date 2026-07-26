import { useEffect, useMemo, useState } from "react";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";
import "./TeacherQuizReviewPage.css";
import {
  canUseDatabase,
  listCustomStories,
  updateQuizExclusions,
} from "../services/database";
import {
  loadCustomStories,
  storyHasTierContent,
  storyToTopic,
  type CustomTeacherStory,
  type StoryDifficultyLevel,
} from "../utils/teacherStories";
import {
  isExcluded,
  storyQuizExclusions,
  toggleExclusion,
  type QuizExclusion,
  type QuizExclusionKind,
} from "../utils/quizExclusions";

/** Teacher quiz review: every piece of material the vocab quiz can build
 * questions from, per story and difficulty tier, with a 🗑 toggle to mark
 * bad items. Marks persist per story (custom_stories.quiz_exclusions) and
 * the quiz never builds questions from marked material.
 *
 * Reached from the teacher shell: Materials → Quiz Review. */
export default function TeacherQuizReviewPage() {
  const [stories, setStories] = useState<CustomTeacherStory[]>([]);
  const [storyId, setStoryId] = useState<string>("");
  const [level, setLevel] = useState<StoryDifficultyLevel>("easy");
  const [exclusions, setExclusions] = useState<QuizExclusion[]>([]);
  const [dirty, setDirty] = useState(false);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );

  useEffect(() => {
    const local = loadCustomStories();
    const apply = (list: CustomTeacherStory[]) => {
      const published = list.filter((s) => s.published);
      setStories(published);
      if (published.length > 0) {
        setStoryId((current) => current || published[0].id);
      }
    };
    apply(local);
    if (canUseDatabase()) {
      listCustomStories().then((db) => apply(db as CustomTeacherStory[])).catch(() => {});
    }
  }, []);

  const story = stories.find((s) => s.id === storyId);

  // Reload the saved marks whenever the story changes.
  useEffect(() => {
    if (!story) return;
    setExclusions(storyQuizExclusions(story));
    setDirty(false);
    setStatus("idle");
    setLevel("easy");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storyId, stories.length]);

  const levels: StoryDifficultyLevel[] = useMemo(() => {
    if (!story) return ["easy"];
    const out: StoryDifficultyLevel[] = ["easy"];
    if (storyHasTierContent(story, "medium")) out.push("medium");
    if (storyHasTierContent(story, "hard")) out.push("hard");
    return out;
  }, [story]);

  const topic = useMemo(
    () => (story ? storyToTopic(story, level) : null),
    [story, level],
  );

  const onToggle = (mark: QuizExclusion) => {
    setExclusions((current) => toggleExclusion(current, mark));
    setDirty(true);
    setStatus("idle");
  };

  const onSave = async () => {
    if (!story) return;
    setStatus("saving");
    try {
      await updateQuizExclusions(story.id, exclusions);
      setDirty(false);
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  };

  const trashButton = (
    word: string,
    kind: QuizExclusionKind,
    index?: number,
  ) => {
    const marked = isExcluded(exclusions, word, kind, index);
    return (
      <button
        type="button"
        className={`tqr-trash${marked ? " is-marked" : ""}`}
        aria-pressed={marked}
        aria-label={`${marked ? "Restore" : "Exclude"} ${kind} for ${word}`}
        onClick={() => onToggle(index === undefined ? { word, kind } : { word, kind, index })}
      >
        {marked ? "↩" : "🗑"}
      </button>
    );
  };

  return (
    <main className="teacher-quiz-review">
      <header className="tqr-header">
        <div>
          <p className="tqr-kicker">
            <BiLabel zh="測驗檢查" pinyin="Cèyàn jiǎnchá" en="Quiz review" />
          </p>
          <h1>
            <BiLabel
              zh="檢查測驗題目和答案"
              pinyin="Jiǎnchá cèyàn tímù hé dá'àn"
              en="Verify quiz questions and answers"
            />
          </h1>
          <p className="tqr-lede">
            <BiText
              zh="標記不好的題目材料，學生的測驗就不會再出這些題。"
              pinyin="Biāojì bù hǎo de tímù cáiliào, xuéshēng de cèyàn jiù bú huì zài chū zhèxiē tí."
              en="Mark bad material and the student quiz will never build questions from it."
            />
          </p>
        </div>
        <div className="tqr-controls">
          <label>
            <BiLabel zh="故事" pinyin="Gùshì" en="Story" />
            <select value={storyId} onChange={(e) => setStoryId(e.target.value)}>
              {stories.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          </label>
          {levels.length > 1 && (
            <label>
              <BiLabel zh="難度" pinyin="Nándù" en="Level" />
              <select
                value={level}
                onChange={(e) => setLevel(e.target.value as StoryDifficultyLevel)}
              >
                {levels.map((l) => (
                  <option key={l} value={l}>
                    {l === "easy" ? "簡單" : l === "medium" ? "中等" : "困難"}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button
            type="button"
            className="tqr-save"
            disabled={!dirty || status === "saving"}
            onClick={onSave}
          >
            {status === "saving" ? (
              <BiLabel zh="儲存中…" pinyin="Chǔcún zhōng…" en="Saving…" />
            ) : (
              <BiLabel zh="儲存標記" pinyin="Chǔcún biāojì" en="Save marks" />
            )}
          </button>
          {status === "saved" && !dirty && (
            <span className="tqr-status-ok">✓ <BiLabel zh="已儲存" en="Saved" /></span>
          )}
          {status === "error" && (
            <span className="tqr-status-error" role="alert">
              <BiLabel zh="儲存失敗" en="Save failed" />
            </span>
          )}
          <span className="tqr-count">
            <BiLabel
              zh={`已標記 ${exclusions.length} 項`}
              en={`${exclusions.length} marked`}
            />
          </span>
        </div>
      </header>

      {!topic && (
        <p className="tqr-empty">
          <BiText
            zh="還沒有已發佈的故事。"
            pinyin="Hái méiyǒu yǐ fābù de gùshì."
            en="No published stories yet."
          />
        </p>
      )}

      {topic &&
        topic.images.map((_, si) => {
          const words = topic.vocabulary[si] || [];
          if (words.length === 0) return null;
          return (
            <section className="tqr-scene" key={si}>
              <h2 className="tqr-scene-title">
                <BiLabel zh={`部分 ${si + 1}`} en={`Scene ${si + 1}`} />
              </h2>
              {words.map((word, wi) => {
                const wordGone = isExcluded(exclusions, word, "word");
                const pinyin = topic.vocabularyPinyin?.[si]?.[wi];
                const pos = topic.vocabularyPos?.[si]?.[wi];
                const translation = topic.vocabularyTranslation?.[si]?.[wi];
                const distractors = topic.vocabularyDistractors?.[si]?.[wi] ?? [];
                const cloze = topic.vocabularyCloze?.[si]?.[wi] ?? [];
                const synonyms = topic.vocabularySynonym?.[si]?.[wi] ?? [];
                return (
                  <article
                    className={`tqr-word${wordGone ? " is-word-gone" : ""}`}
                    key={`${word}-${wi}`}
                  >
                    <header className="tqr-word-head">
                      <strong lang="zh-Hant">{word}</strong>
                      {pinyin && <span className="tqr-pinyin">{pinyin}</span>}
                      {pos && <span className="tqr-pos">{pos}</span>}
                      {translation ? (
                        <span className="tqr-translation">→ {translation}</span>
                      ) : (
                        <span className="tqr-no-quiz">
                          <BiLabel zh="沒有翻譯，不會出題" en="No translation — never quizzed" />
                        </span>
                      )}
                      {translation && trashButton(word, "word")}
                    </header>
                    {!wordGone && translation && (
                      <div className="tqr-pools">
                        {distractors.length > 0 && (
                          <div className="tqr-pool">
                            <span className="tqr-pool-label">
                              <BiLabel zh="干擾選項" en="Distractors" />
                              {trashButton(word, "distractors")}
                            </span>
                            <span className="tqr-pool-items">{distractors.join(" · ")}</span>
                          </div>
                        )}
                        {cloze.map((c, ci) => (
                          <div
                            className={`tqr-pool${isExcluded(exclusions, word, "cloze", ci) ? " is-marked" : ""}`}
                            key={`cloze-${ci}`}
                          >
                            <span className="tqr-pool-label">
                              <BiLabel zh="填空" en="Cloze" /> #{ci + 1}
                              {trashButton(word, "cloze", ci)}
                            </span>
                            <span className="tqr-pool-items" lang="zh-Hant">
                              {c.sentence}（{c.distractors.join(" / ")}）
                            </span>
                          </div>
                        ))}
                        {synonyms.map((s, syi) => (
                          <div
                            className={`tqr-pool${isExcluded(exclusions, word, "synonym", syi) ? " is-marked" : ""}`}
                            key={`syn-${syi}`}
                          >
                            <span className="tqr-pool-label">
                              <BiLabel zh="同義詞" en="Synonym" /> #{syi + 1}
                              {trashButton(word, "synonym", syi)}
                            </span>
                            <span className="tqr-pool-items" lang="zh-Hant">
                              {word} ≈ {s.synonym}（{s.distractors.join(" / ")}）
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </article>
                );
              })}
            </section>
          );
        })}
    </main>
  );
}
