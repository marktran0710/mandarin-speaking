import { BiLabel, BiText } from "../BiLabel";
import Icon from "../../shared/ui/Icon";
import StudentIcon from "../StudentIcon";
import { SkillFocusLabel } from "../TopicSelector";
import type { Topic } from "./StoryRecorder";

interface StoryOverviewSectionProps {
  topic: Topic;
  hasVocabQuiz: boolean;
  speakingLocked: boolean;
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
  enableSorting,
  onSelectPhase,
}: StoryOverviewSectionProps) {
  return (
    <section className="story-overview">
      <div className="overview-hero">
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
            <span className="overview-choice-icon" aria-hidden="true">
              <StudentIcon name="stories" size={20} />
            </span>
            <strong>
              <BiLabel k="vocabulary_map" />
            </strong>
            <p>
              {hasVocabQuiz ? (
                <BiText k="match_key_words_to_each_story_scene" />
              ) : (
                <BiText
                  zh="老師還沒有生詞翻譯"
                  pinyin="Lǎoshī hái méiyǒu shēngcí fānyì"
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
            <span className="overview-choice-icon"><Icon name="microphone" size={20} /></span>
            <strong>
              <BiLabel k="speaking_practice" />
            </strong>
            <p>
              {speakingLocked ? (
                <BiText
                  zh="請先完成生詞測驗"
                  pinyin="Qǐng xiān wánchéng shēngcí cèyàn"
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
