import { BiLabel, BiText } from "./BiLabel";
import { SkillFocusLabel } from "./TopicSelector";
import { toPinyin } from "../utils/pinyin";
import type { Topic } from "./StoryRecorder";

interface StoryOverviewSectionProps {
  topic: Topic;
  hasVocabQuiz: boolean;
  speakingLocked: boolean;
  allVocabulary: string[];
  enableSorting: boolean;
  /** Orientation choices hand control back to the parent's phase machine —
   * "vocabulary quiz" always goes to "vocabquiz"; "speaking practice" goes to
   * "sorting" when the picture-ordering minigame is enabled, else straight to
   * "practice". */
  onSelectPhase: (phase: "vocabquiz" | "sorting" | "practice") => void;
}

export default function StoryOverviewSection({
  topic,
  hasVocabQuiz,
  speakingLocked,
  allVocabulary,
  enableSorting,
  onSelectPhase,
}: StoryOverviewSectionProps) {
  return (
    <section className="story-overview">
      <div className="overview-hero">
        <p className="eyebrow">
          <BiLabel k="story_challenge" />
        </p>
        {topic.lessonNumber != null && (
          <span className="lesson-number-badge">
            <BiLabel
              zh={`第 ${topic.lessonNumber} 課`}
              pinyin={`Dì ${topic.lessonNumber} kè`}
              en={`Lesson ${topic.lessonNumber}`}
            />
          </span>
        )}
        <h1 className="overview-title">{topic.name}</h1>
        {topic.description && (
          <p className="overview-desc">{topic.description}</p>
        )}
        {(topic.level || topic.skillFocus) && (
          <div className="overview-meta">
            {topic.level && <span>{topic.level}</span>}
            {topic.skillFocus && (
              <span>
                <SkillFocusLabel skillFocus={topic.skillFocus} />
              </span>
            )}
          </div>
        )}
      </div>

      {allVocabulary.length > 0 && (
        <div className="overview-vocab-block">
          <h2>
            <BiLabel k="key_vocabulary" />
          </h2>
          {topic.images.map((_, si) => {
            const sceneWords = topic.vocabulary[si] || [];
            if (sceneWords.length === 0) return null;
            return (
              <div key={si} className="overview-vocab-scene">
                <span className="overview-vocab-scene-label">
                  <BiLabel zh={`場景 ${si + 1}`} pinyin={`Chǎngjǐng ${si + 1}`} en={`Scene ${si + 1}`} />
                </span>
                <div
                  className="overview-vocab-table"
                  role="table"
                  aria-label="Key vocabulary"
                >
                  {sceneWords.map((word, i) => {
                    const py =
                      topic.vocabularyPinyin?.[si]?.[i] || toPinyin(word);
                    const pos = topic.vocabularyPos?.[si]?.[i];
                    const translation =
                      topic.vocabularyTranslation?.[si]?.[i];
                    return (
                      <div
                        className="overview-vocab-row"
                        role="row"
                        key={`${word}-${i}`}
                      >
                        <span
                          className="overview-vocab-cell overview-vocab-hanzi"
                          role="cell"
                        >
                          {word}
                        </span>
                        <span
                          className="overview-vocab-cell overview-vocab-pinyin"
                          role="cell"
                        >
                          {py}
                        </span>
                        <span
                          className="overview-vocab-cell overview-vocab-pos"
                          role="cell"
                        >
                          {pos}
                        </span>
                        <span
                          className="overview-vocab-cell overview-vocab-meaning"
                          role="cell"
                        >
                          {translation}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="overview-steps-block">
        <h2>
          <BiLabel k="your_challenge" />
        </h2>
        <div className="overview-choice-grid">
          <button
            type="button"
            className="overview-choice-card"
            disabled={!hasVocabQuiz}
            onClick={() => onSelectPhase("vocabquiz")}
          >
            <span className="overview-choice-icon">❓</span>
            <strong>
              <BiLabel k="vocabulary_map" />
            </strong>
            <p>
              {hasVocabQuiz ? (
                <BiText k="match_key_words_to_each_story_scene" />
              ) : (
                <BiText
                  zh="老師還沒有詞彙翻譯"
                  pinyin="Lǎoshī hái méiyǒu cíhuì fānyì"
                  en="Your teacher hasn't added any word translations yet"
                />
              )}
            </p>
          </button>

          <button
            type="button"
            className="overview-choice-card"
            disabled={speakingLocked}
            onClick={() => onSelectPhase(enableSorting ? "sorting" : "practice")}
          >
            <span className="overview-choice-icon">🎙️</span>
            <strong>
              <BiLabel k="speaking_practice" />
            </strong>
            <p>
              {speakingLocked ? (
                <BiText
                  zh="請先完成詞彙測驗"
                  pinyin="Qǐng xiān wánchéng cíhuì cèyàn"
                  en="Complete the vocabulary quiz first"
                />
              ) : (
                <BiText k="record_your_mandarin_story_out_loud" />
              )}
            </p>
          </button>
        </div>
      </div>
    </section>
  );
}
