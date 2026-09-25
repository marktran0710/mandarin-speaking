import type { Topic } from "../../components/content/topic-selector/types";
import StudentPageHeader from "../primitives/StudentPageHeader";
import StudentSection from "../primitives/StudentSection";
import StudentButton from "../primitives/StudentButton";
import StudentIcon from "../primitives/StudentIcon";
import StudentStatusPill from "../primitives/StudentStatusPill";
import "../primitives/layout.css";
import "./CompletionPage.css";

interface CompletionPageProps {
  topic: Topic;
  sceneCount: number;
  hasConversation: boolean;
  /** null when this story runs no quiz at all (see topicHasQuiz). */
  quizStars: 0 | 1 | 2 | 3 | null;
  overallCompleted: number;
  overallTotal: number;
  nextTopic: Topic | null;
  nextTopicUnlocked: boolean;
  onStartNext: (topic: Topic) => void;
  onBackToStudy: () => void;
}

export default function CompletionPage({
  topic,
  sceneCount,
  hasConversation,
  quizStars,
  overallCompleted,
  overallTotal,
  nextTopic,
  nextTopicUnlocked,
  onStartNext,
  onBackToStudy,
}: CompletionPageProps) {
  const overallPercent = overallTotal === 0 ? 0 : Math.round((overallCompleted / overallTotal) * 100);

  return (
    <div className="sa-page-container sa-page-container--narrow">
      <StudentPageHeader
        eyebrowEn="Lesson Complete"
        titleZh="完成！"
        titleEn={topic.name}
      />

      <StudentSection variant="panel" className="sa-completion__stats">
        {quizStars !== null && (
          <span className="sa-completion__stat">
            <StudentIcon name="star" size={16} role="decorative" filled />
            {quizStars} / 3 星
          </span>
        )}
        <span className="sa-completion__stat">
          <StudentIcon name="check_circle" size={16} role="decorative" filled />
          {sceneCount} / {sceneCount} 場景
        </span>
        {hasConversation && (
          <span className="sa-completion__stat">
            <StudentIcon name="check_circle" size={16} role="decorative" filled />
            對話
          </span>
        )}
      </StudentSection>

      <StudentSection variant="tinted" className="sa-completion__overall">
        <div>
          <strong>學習進度: {overallCompleted} / {overallTotal} ({overallPercent}%)</strong>
          <span>持續學習，完成下一個課程單元</span>
        </div>
        <div className="sa-completion__overall-bar" aria-label={`${overallPercent}% of the course complete`}>
          <span style={{ width: `${overallPercent}%` }} />
        </div>
      </StudentSection>

      {nextTopic && (
        <StudentSection variant="panel" className="sa-completion__next">
          <p className="sa-completion__next-label">下一課 · Next lesson</p>
          <p className="sa-completion__next-title" lang="zh-Hant">{nextTopic.name}</p>
          {nextTopicUnlocked ? (
            <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={() => onStartNext(nextTopic)}>
              開始學習 Start
            </StudentButton>
          ) : (
            <StudentStatusPill tone="neutral">未開啟 Locked</StudentStatusPill>
          )}
        </StudentSection>
      )}

      <StudentButton variant="secondary" onClick={onBackToStudy}>
        回到課程目錄 Back to Study
      </StudentButton>
    </div>
  );
}
