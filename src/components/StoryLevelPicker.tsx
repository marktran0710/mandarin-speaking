import { storyHasTierContent, type CustomTeacherStory, type StoryDifficultyLevel } from "../utils/teacherStories";
import { isStoryLevelUnlocked } from "../utils/storyLevelProgress";
import { BiLabel, BiText } from "./BiLabel";
import "./StoryLevelPicker.css";

interface StoryLevelPickerProps {
  story: CustomTeacherStory;
  onSelectLevel: (level: StoryDifficultyLevel) => void;
  onBack: () => void;
}

const LEVEL_COPY: Record<
  StoryDifficultyLevel,
  { zh: string; pinyin: string; en: string; icon: string }
> = {
  easy: { zh: "簡單", pinyin: "Jiǎndān", en: "Easy", icon: "🌱" },
  medium: { zh: "中等", pinyin: "Zhōngděng", en: "Medium", icon: "🌿" },
  hard: { zh: "困難", pinyin: "Kùnnán", en: "Hard", icon: "🌳" },
};

/** Same story/scenes at three tiers of text complexity. Always shows Easy;
 * Medium/Hard only appear once a teacher has actually authored content for
 * them, and stay locked until the previous tier has been submitted once —
 * students always progress easy -> medium -> hard, never skip ahead. */
export default function StoryLevelPicker({ story, onSelectLevel, onBack }: StoryLevelPickerProps) {
  const levels: StoryDifficultyLevel[] = ["easy", "medium", "hard"].filter(
    (level): level is StoryDifficultyLevel =>
      level === "easy" || storyHasTierContent(story, level as "medium" | "hard"),
  );

  return (
    <section className="story-level-picker" aria-label="Choose a difficulty level">
      <button type="button" className="slp-back" onClick={onBack} aria-label="Back to topics">
        ← <BiLabel k="back_to_topics" />
      </button>
      <h1 className="slp-title">{story.title}</h1>
      <p className="slp-subtitle">
        <BiText
          zh="選一個難度開始"
          pinyin="Xuǎn yí ge nándù kāishǐ"
          en="Choose a difficulty level to begin"
        />
      </p>
      <div className="slp-grid">
        {levels.map((level) => {
          const unlocked = isStoryLevelUnlocked(story.id, level);
          const copy = LEVEL_COPY[level];
          return (
            <button
              key={level}
              type="button"
              className="slp-card"
              disabled={!unlocked}
              onClick={() => onSelectLevel(level)}
            >
              <span className="slp-card-icon">{unlocked ? copy.icon : "🔒"}</span>
              <strong>
                <BiLabel zh={copy.zh} pinyin={copy.pinyin} en={copy.en} />
              </strong>
              {!unlocked && (
                <p className="slp-card-locked-note">
                  <BiText
                    zh={`先完成${LEVEL_COPY[level === "medium" ? "easy" : "medium"].zh}`}
                    pinyin={`Xiān wánchéng ${LEVEL_COPY[level === "medium" ? "easy" : "medium"].pinyin}`}
                    en={`Finish ${LEVEL_COPY[level === "medium" ? "easy" : "medium"].en} first`}
                  />
                </p>
              )}
            </button>
          );
        })}
      </div>
    </section>
  );
}
