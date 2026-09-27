import { useMemo } from "react";
import type { Topic } from "@entities/topic";
import { groupTopicsByLesson, lessonTitle, topicStoryId } from "../../utils/lessonGroups";
import { loadSubmittedStoryIds } from "../../utils/storyLevelProgress";
import StudentPage from "@shared/ui/student/StudentPage";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill from "@shared/ui/student/StudentStatusPill";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import "./ProgressPage.css";

interface ProgressPageProps {
  topics: Topic[];
}

type LessonStatus = "completed" | "current" | "not-started";

export default function ProgressPage({ topics }: ProgressPageProps) {
  const submittedIds = useMemo(() => loadSubmittedStoryIds(), [topics]);
  const groups = useMemo(() => groupTopicsByLesson(topics), [topics]);

  const lessonRows = useMemo(() => {
    let seenIncomplete = false;
    return groups.map((group) => {
      const total = group.topics.length;
      const done = group.topics.filter((t) => submittedIds.has(topicStoryId(t))).length;
      let status: LessonStatus;
      if (total > 0 && done === total) {
        status = "completed";
      } else if (!seenIncomplete) {
        status = "current";
        seenIncomplete = true;
      } else {
        status = "not-started";
      }
      const title = group.lessonNumber != null ? lessonTitle(group.lessonNumber) : null;
      return {
        key: group.lessonNumber ?? "other",
        label: group.lessonNumber != null ? `第 ${group.lessonNumber} 課` : "其他",
        titleZh: title?.zh,
        status,
        done,
        total,
      };
    });
  }, [groups, submittedIds]);

  const totalStories = topics.length;
  const totalDone = useMemo(
    () => topics.filter((t) => submittedIds.has(topicStoryId(t))).length,
    [topics, submittedIds],
  );

  return (
    <StudentPage
      layout="hub"
      header={<StudentPageHeader eyebrowKey="progress" titleKey="learningProgress" />}
    >
      <StudentSection variant="panel" className="sa-progress__list">
        {lessonRows.map((row) => (
          <div key={row.key} className="sa-progress__row">
            <div className="sa-progress__row-copy">
              <span lang="zh-Hant" className="sa-progress__row-title">{row.label}</span>
              {row.titleZh && <span className="sa-progress__row-subtitle">{row.titleZh}</span>}
            </div>
            {row.status === "completed" && <StudentStatusPill tone="success"><StudentSystemText k="completed" withinControl /></StudentStatusPill>}
            {row.status === "current" && <StudentStatusPill tone="info"><StudentSystemText k="current" withinControl /></StudentStatusPill>}
            {row.status === "not-started" && <StudentStatusPill tone="neutral" icon="schedule"><StudentSystemText k="notStarted" withinControl /></StudentStatusPill>}
          </div>
        ))}
      </StudentSection>

      <StudentSection variant="panel" className="sa-progress__stat-row">
        <span className="sa-progress__stat-label"><StudentSystemText k="sessionsCompleted" /></span>
        <span className="sa-progress__stat-value">{totalDone} / {totalStories}</span>
      </StudentSection>
    </StudentPage>
  );
}
