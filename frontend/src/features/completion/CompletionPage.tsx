import type { Topic } from "@entities/topic";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentStatusPill from "@shared/ui/student/StudentStatusPill";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import "@shared/ui/student/layout.css";
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
    <div className="sa-page-container sa-page sa-page-container--narrow">
      <StudentPageHeader
        eyebrowKey="lessonComplete"
        context={<span lang="zh-Hant">{topic.name}</span>}
        titleKey="finished"
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
          <span><StudentSystemText k="keepLearning" /></span>
        </div>
        <div className="sa-completion__overall-bar" aria-label={`課程完成 ${overallPercent}%`}>
          <span style={{ width: `${overallPercent}%` }} />
        </div>
      </StudentSection>

      {nextTopic && (
        <StudentSection variant="panel" className="sa-completion__next">
          <p className="sa-completion__next-label"><StudentSystemText k="nextLesson" /></p>
          <p className="sa-completion__next-title" lang="zh-Hant">{nextTopic.name}</p>
          {nextTopicUnlocked ? (
            <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={() => onStartNext(nextTopic)}>
              <StudentSystemText k="start" withinControl />
            </StudentButton>
          ) : (
            <StudentStatusPill tone="neutral"><StudentSystemText k="locked" withinControl /></StudentStatusPill>
          )}
        </StudentSection>
      )}

      <StudentButton variant="secondary" onClick={onBackToStudy}>
        <StudentSystemText k="backToStudy" withinControl />
      </StudentButton>
    </div>
  );
}
