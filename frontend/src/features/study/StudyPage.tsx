import { useMemo } from "react";
import type { Topic } from "@entities/topic";
import { groupTopicsByLesson, lessonTitle, topicStoryId } from "../../utils/lessonGroups";
import { speakingVocabularyItems } from "@entities/vocabulary";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill from "@shared/ui/student/StudentStatusPill";
import "@shared/ui/student/layout.css";
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

const CHAPTER_FIVE_TITLE = {
  zh: "日常會話",
  pinyin: "rì cháng huì huà",
  en: "Everyday Conversation",
};

function titleForLesson(lessonNumber: number | null) {
  if (lessonNumber === 5) return CHAPTER_FIVE_TITLE;
  return lessonNumber == null ? null : lessonTitle(lessonNumber);
}

function lessonCode(lessonNumber: number | null, lessonSubOrder: number | null | undefined, index: number) {
  if (lessonNumber != null && lessonSubOrder != null) return `${lessonNumber}-${lessonSubOrder}`;
  return String(index + 1).padStart(2, "0");
}

export default function StudyPage({ topics, statusByStoryId, onOpenTopic }: StudyPageProps) {
  const groups = useMemo(() => groupTopicsByLesson(topics), [topics]);
  const totalUnits = useMemo(() => groups.reduce((total, group) => total + group.topics.length, 0), [groups]);
  const completedUnits = useMemo(
    () => topics.filter((topic) => statusByStoryId[topicStoryId(topic)]?.status === "completed").length,
    [statusByStoryId, topics],
  );
  const completionPercent = totalUnits === 0 ? 0 : Math.round((completedUnits / totalUnits) * 100);
  const currentGroup = groups[0];
  const currentTitle = titleForLesson(currentGroup?.lessonNumber ?? null);
  const focusWords = useMemo(
    () => topics.flatMap((topic) => speakingVocabularyItems(topic)).slice(0, 5),
    [topics],
  );

  return (
    <div className="sa-page-container sa-page-container--study-hub">
      <header className="sa-study__hub-header">
        <div className="sa-study__hub-heading">
          <p className="sa-study__hub-pinyin">
            {currentGroup?.lessonNumber != null ? `dì-wǔ kè　 ${currentTitle?.pinyin ?? ""}` : "mandarin study hub"}
          </p>
          <h1>
            <span lang="zh-Hant">{currentGroup?.lessonNumber != null ? `第${currentGroup.lessonNumber}課` : "學習中心"}</span>
            <span className="sa-study__hub-dot" aria-hidden="true">•</span>
            <span lang="zh-Hant">{currentTitle?.zh ?? "課程目錄"}</span>
            <span className="sa-study__hub-muted" lang="zh-Hant">研讀</span>
          </h1>
        </div>
        <div className="sa-study__hub-summary" aria-label="Study summary">
          <span><StudentIcon name="bolt" size={16} role="decorative" /> 3/wk</span>
          <span><StudentIcon name="local_fire_department" size={16} role="decorative" /> 5d</span>
          <span><StudentIcon name="track_changes" size={16} role="decorative" /> 94%</span>
        </div>
      </header>

      {groups.length === 0 ? (
        <StudentSection variant="panel" className="sa-study__empty">
          <StudentIcon name="menu_book" size={22} role="decorative" />
          <p>No lessons have been assigned yet.</p>
        </StudentSection>
      ) : (
        <div className="sa-study__hub-grid">
          <div className="sa-study__catalogue">
            <div className="sa-study__catalogue-head">
              <h2>課程目錄 <span>{totalUnits} 課元</span></h2>
              <span className="sa-study__level-badge">HSK 2</span>
            </div>

            {groups.map((group) => {
              const groupTitle = titleForLesson(group.lessonNumber);
              return (
                <section key={group.lessonNumber ?? "other"} className="sa-study__group">
                  {groups.length > 1 && (
                    <div className="sa-study__group-label">
                      <span lang="zh-Hant">{group.lessonNumber != null ? `第${group.lessonNumber}課` : "其他課程"}</span>
                      {groupTitle && <span>{groupTitle.zh}</span>}
                    </div>
                  )}
                  <StudentSection variant="panel" className="sa-study__list">
                    {group.topics.map((topic, index) => {
                      const storyId = topicStoryId(topic);
                      const entry = statusByStoryId[storyId] ?? { status: "not-started" as LessonRowStatus };
                      const locked = entry.status === "locked";
                      const isCurrent = entry.status === "in-progress";
                      const code = lessonCode(group.lessonNumber, topic.lessonSubOrder, index);
                      const description = topic.description === "Teacher published activity" ? "" : topic.description;

                      return (
                        <article
                          key={topic.id}
                          className={`sa-study__row ${isCurrent ? "is-current" : ""} ${locked ? "is-locked" : ""}`}
                        >
                          <span className="sa-study__row-index">{String(index + 1).padStart(2, "0")}</span>
                          <div className="sa-study__row-copy">
                            <div className="sa-study__row-titleline">
                              <span className="sa-study__row-code">{code}</span>
                              <span className="sa-study__row-title" lang="zh-Hant">{topic.name}</span>
                            </div>
                            {description && <span className="sa-study__row-desc">{description}</span>}
                          </div>
                          <div className="sa-study__row-actions">
                            {entry.status === "completed" && <StudentStatusPill tone="success">完成</StudentStatusPill>}
                            {isCurrent && <StudentStatusPill tone="info">進行中</StudentStatusPill>}
                            {entry.status === "not-started" && <span className="sa-study__row-hint">待解鎖</span>}
                            {locked && <StudentStatusPill tone="neutral">未開啟</StudentStatusPill>}
                            {locked ? (
                              <StudentIcon name="lock" size={18} role="meaningful" label="Locked" />
                            ) : (
                              <StudentButton
                                variant={isCurrent ? "primary" : "secondary"}
                                size={isCurrent ? "default" : "sm"}
                                iconTrailing={isCurrent ? "arrow_forward" : undefined}
                                onClick={() => onOpenTopic(topic)}
                              >
                                {entry.status === "completed" ? "複習" : isCurrent ? "繼續" : "預覽"}
                              </StudentButton>
                            )}
                          </div>
                          {isCurrent && (
                            <div className="sa-study__phase-strip" aria-label="Lesson phases">
                              {PHASE_STRIP.map((phase) => {
                                const done = entry.phases?.[phase.key] ?? false;
                                return (
                                  <span key={phase.key} className={`sa-study__phase ${done ? "is-done" : ""}`}>
                                    <StudentIcon name={done ? "check_circle" : phase.icon} size={16} role="decorative" />
                                    <span lang="zh-Hant">{phase.label}</span>
                                  </span>
                                );
                              })}
                            </div>
                          )}
                        </article>
                      );
                    })}
                  </StudentSection>
                </section>
              );
            })}

            <StudentSection variant="tinted" className="sa-study__progress-card">
              <span className="sa-study__progress-icon"><StudentIcon name="schedule" size={20} role="decorative" /></span>
              <div>
                <strong>學習進度: {completedUnits} / {totalUnits} ({completionPercent}%)</strong>
                <span>持續學習，完成下一個課程單元</span>
              </div>
              <div className="sa-study__progress-bar" aria-label={`${completionPercent}% complete`}><span style={{ width: `${completionPercent}%` }} /></div>
            </StudentSection>
          </div>

          <aside className="sa-study__rail" aria-label="Study aids">
            <StudentSection variant="panel" className="sa-study__focus-card">
              <div className="sa-study__rail-heading">
                <h2><StudentIcon name="menu_book" size={17} role="decorative" /> 重點生詞</h2>
                <span>{focusWords.length} 詞</span>
              </div>
              <div className="sa-study__focus-list">
                {focusWords.length > 0 ? focusWords.map((word) => (
                  <div className="sa-study__focus-word" key={word.wordId}>
                    <div>
                      {word.pinyin && <span className="sa-study__focus-pinyin">{word.pinyin}</span>}
                      <strong lang="zh-Hant">{word.word}</strong>
                    </div>
                    <span className="sa-study__word-audio">
                      <StudentAudioControl audioUrl={word.audioUrl} label="Listen" compact />
                    </span>
                  </div>
                )) : <p className="sa-study__rail-empty">Vocabulary will appear here after the lesson is loaded.</p>}
              </div>
            </StudentSection>

            <StudentSection variant="tinted" className="sa-study__rail-note">
              <StudentIcon name="campaign" size={17} role="decorative" />
              <div><span>學習提示</span><strong>聽一次 · 說一次 · 用一次</strong></div>
            </StudentSection>
            <StudentSection variant="panel" className="sa-study__rail-note sa-study__rail-note--quiet">
              <StudentIcon name="lightbulb" size={18} role="decorative" />
              <div><span>文化常識</span><strong>{currentTitle?.zh ?? "日常會話"} · 課程筆記</strong></div>
            </StudentSection>
            <StudentSection variant="panel" className="sa-study__rail-schedule">
              <StudentIcon name="calendar_month" size={18} role="decorative" />
              <strong>本週 {totalUnits} 個課程單元</strong>
              <span>依序完成即可</span>
            </StudentSection>
          </aside>
        </div>
      )}
    </div>
  );
}
