import { useMemo } from "react";
import type { Topic } from "../../components/content/topic-selector/types";
import { groupTopicsByLesson, lessonTitle, topicStoryId } from "../../utils/lessonGroups";
import StudentPageHeader from "../primitives/StudentPageHeader";
import StudentSection from "../primitives/StudentSection";
import StudentButton from "../primitives/StudentButton";
import StudentStatusPill from "../primitives/StudentStatusPill";
import StudentIcon from "../primitives/StudentIcon";
import "../primitives/layout.css";
import "./StudyPage.css";

export type LessonRowStatus = "completed" | "in-progress" | "not-started" | "locked";

export interface StudyTopicStatus {
  status: LessonRowStatus;
  /** Which phases of this story the student has finished, for the inline
   * phase strip on the active row. */
  phases?: { vocab: boolean; quiz: boolean; speaking: boolean; conversation: boolean };
}

interface StudyPageProps {
  topics: Topic[];
  /** Status per story id — computed by the container from the real
   * progression gates, never derived inside this presentational page. */
  statusByStoryId: Record<string, StudyTopicStatus>;
  onOpenTopic: (topic: Topic) => void;
}

const PHASE_STRIP = [
  { key: "vocab", icon: "menu_book", label: "生詞" },
  { key: "quiz", icon: "edit_note", label: "測驗" },
  { key: "speaking", icon: "mic", label: "口語" },
  { key: "conversation", icon: "forum", label: "對話" },
] as const;

export default function StudyPage({ topics, statusByStoryId, onOpenTopic }: StudyPageProps) {
  const groups = useMemo(() => groupTopicsByLesson(topics), [topics]);

  return (
    <div className="sa-page-container">
      <StudentPageHeader
        eyebrowEn="Study"
        eyebrowZh="研讀"
        titleZh="課程目錄"
        titleEn="Your assigned lessons"
      />

      {groups.length === 0 && (
        <StudentSection variant="panel" className="sa-study__empty">
          <StudentIcon name="menu_book" size={22} role="decorative" />
          <p>No lessons have been assigned yet.</p>
        </StudentSection>
      )}

      {groups.map((group) => {
        const title = group.lessonNumber != null ? lessonTitle(group.lessonNumber) : null;
        return (
          <section key={group.lessonNumber ?? "other"} className="sa-study__group">
            <div className="sa-study__group-head">
              <h2 className="sa-study__group-title">
                <span lang="zh-Hant">
                  {group.lessonNumber != null ? `第 ${group.lessonNumber} 課` : "其他"}
                </span>
                {title && <span className="sa-study__group-title-en">{title.en}</span>}
              </h2>
              <span className="sa-study__group-count">
                {group.topics.length} {group.topics.length === 1 ? "story" : "stories"}
              </span>
            </div>

            <StudentSection variant="panel" className="sa-study__list">
              {group.topics.map((topic, index) => {
                const storyId = topicStoryId(topic);
                const entry = statusByStoryId[storyId] ?? { status: "not-started" as LessonRowStatus };
                const locked = entry.status === "locked";
                const subLabel =
                  group.lessonNumber != null && topic.lessonSubOrder != null
                    ? `${group.lessonNumber}-${topic.lessonSubOrder}`
                    : String(index + 1).padStart(2, "0");

                return (
                  <div
                    key={topic.id}
                    className={`sa-study__row ${entry.status === "in-progress" ? "is-current" : ""} ${locked ? "is-locked" : ""}`}
                  >
                    <div className="sa-study__row-main">
                      <span className="sa-study__row-index">{subLabel}</span>
                      <div className="sa-study__row-copy">
                        <span className="sa-study__row-title" lang="zh-Hant">{topic.name}</span>
                        {topic.description && (
                          <span className="sa-study__row-desc">{topic.description}</span>
                        )}
                      </div>
                    </div>

                    <div className="sa-study__row-actions">
                      {entry.status === "completed" && <StudentStatusPill tone="success">完成</StudentStatusPill>}
                      {entry.status === "in-progress" && <StudentStatusPill tone="info">進行中</StudentStatusPill>}
                      {entry.status === "not-started" && (
                        <span className="sa-study__row-hint">待開始</span>
                      )}
                      {locked && <StudentStatusPill tone="neutral">未開啟</StudentStatusPill>}

                      {!locked && (
                        <StudentButton
                          variant={entry.status === "in-progress" ? "primary" : "secondary"}
                          size={entry.status === "in-progress" ? "default" : "sm"}
                          iconTrailing={entry.status === "in-progress" ? "arrow_forward" : undefined}
                          onClick={() => onOpenTopic(topic)}
                        >
                          {entry.status === "completed" ? "複習" : entry.status === "in-progress" ? "繼續" : "開始"}
                        </StudentButton>
                      )}
                    </div>

                    {entry.status === "in-progress" && entry.phases && (
                      <div className="sa-study__phase-strip">
                        {PHASE_STRIP.map((phase) => {
                          const done = entry.phases![phase.key];
                          return (
                            <span
                              key={phase.key}
                              className={`sa-study__phase ${done ? "is-done" : ""}`}
                            >
                              <StudentIcon
                                name={done ? "check_circle" : phase.icon}
                                size={16}
                                role="decorative"
                              />
                              <span lang="zh-Hant">{phase.label}</span>
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </StudentSection>
          </section>
        );
      })}
    </div>
  );
}
