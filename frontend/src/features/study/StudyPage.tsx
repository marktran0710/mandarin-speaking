import { useMemo } from "react";
import type { Topic } from "@entities/topic";
import {
  groupTopicsByLesson,
  lessonTitle,
  topicStoryId,
} from "../../utils/lessonGroups";
import { speakingVocabularyItems } from "@entities/vocabulary";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentPage from "@shared/ui/student/StudentPage";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill from "@shared/ui/student/StudentStatusPill";
import "./StudyPage.css";
export type LessonRowStatus =
  "completed" | "in-progress" | "not-started" | "locked";
export interface StudyTopicStatus {
  status: LessonRowStatus;
  phases?: {
    vocab: boolean;
    quiz: boolean;
    speaking: boolean;
    conversation: boolean;
  };
}
interface StudyPageProps {
  topics: Topic[];
  statusByStoryId: Record<string, StudyTopicStatus>;
  onOpenTopic: (topic: Topic) => void;
}
export function selectStudyHeroTopic(
  topics: Topic[],
  statuses: Record<string, StudyTopicStatus>,
): Topic | null {
  return (
    topics.find((t) => statuses[topicStoryId(t)]?.status === "in-progress") ??
    topics.find((t) => statuses[topicStoryId(t)]?.status === "not-started") ??
    null
  );
}
const phases = ["詞彙", "測驗", "口語", "對話"];
export default function StudyPage({
  topics,
  statusByStoryId,
  onOpenTopic,
}: StudyPageProps) {
  const groups = useMemo(() => groupTopicsByLesson(topics), [topics]);
  const hero = useMemo(
    () => selectStudyHeroTopic(topics, statusByStoryId),
    [topics, statusByStoryId],
  );
  const completed = topics.filter(
    (t) => statusByStoryId[topicStoryId(t)]?.status === "completed",
  ).length;
  const percent = topics.length
    ? Math.round((completed / topics.length) * 100)
    : 0;
  const heroStatus = hero && statusByStoryId[topicStoryId(hero)];
  const words = useMemo(
    () => (hero ? speakingVocabularyItems(hero).slice(0, 5) : []),
    [hero],
  );
  const header = (
    <StudentPageHeader
      eyebrowZh="學習"
      eyebrowEn="Study"
      titleZh="慢慢學，穩穩進步"
      titleEn="Your Mandarin course"
    />
  );
  if (!groups.length)
    return (
      <StudentPage
        layout="hub"
        header={header}
        state="empty"
        emptyTitle="目前沒有可學的課程"
        emptyText="課程發布後會出現在這裡。"
      />
    );
  const heroCard = (
    <StudentSection variant="tinted" className="study-hero-card">
      <span className="study-kicker">
        {hero ? (
          <>
            繼續你的學習 · <em>Continue learning</em>
          </>
        ) : (
          <>
            課程完成 · <em>Course complete</em>
          </>
        )}
      </span>
      {hero ? (
        <>
          <h2 lang="zh-Hant">{hero.name}</h2>
          {hero.description &&
            hero.description !== "Teacher published activity" && (
              <p>{hero.description}</p>
            )}
          <StudentButton
            variant="primary"
            iconTrailing="arrow_forward"
            onClick={() => onOpenTopic(hero)}
          >
            {heroStatus?.status === "in-progress" ? (
              <>
                繼續學習 · <span>Continue</span>
              </>
            ) : (
              <>
                開始學習 · <span>Start</span>
              </>
            )}
          </StudentButton>
        </>
      ) : (
        <>
          <h2>你已完成所有課程</h2>
          <p>回顧任何一課，保持你的學習節奏。</p>
        </>
      )}
    </StudentSection>
  );
  const rail = (
    <aside className="study-rail">
      <StudentSection variant="panel" className="study-focus-card">
        <div className="study-card-heading">
          <h2>
            <StudentIcon name="menu_book" size={17} role="decorative" />{" "}
            本課重點 <small>Focus words</small>
          </h2>
          <span>{words.length} 個詞 · words</span>
        </div>
        {words.length ? (
          words.map((word) => (
            <div className="study-word" key={word.wordId}>
              <span>
                <small>{word.pinyin}</small>
                <strong lang="zh-Hant">{word.word}</strong>
              </span>
              <StudentAudioControl
                audioUrl={word.audioUrl}
                label="聆聽 · Listen"
                compact
              />
            </div>
          ))
        ) : (
          <p>
            選擇一課後，重點詞彙會顯示在這裡。 Choose a lesson to see focus
            words.
          </p>
        )}
      </StudentSection>
      <StudentSection variant="tinted" className="study-progress">
        <div>
          <strong>學習進度 · Progress</strong>
          <span>{percent}% 完成 · Keep your steady pace</span>
        </div>
        <div className="study-progress-bar">
          <span style={{ width: `${percent}%` }} />
        </div>
      </StudentSection>
    </aside>
  );
  return (
    <StudentPage layout="hub" header={header} rail={rail}>
      <div className="study-hero-wide">{heroCard}</div>
      {groups.map((group) => (
        <section className="study-group" key={group.lessonNumber ?? "other"}>
          <div className="study-group-label">
            <strong>
              {group.lessonNumber == null
                ? "其他內容"
                : `第 ${group.lessonNumber} 課 · ${lessonTitle(group.lessonNumber).zh}`}
            </strong>
            <span>
              {group.lessonNumber == null
                ? "Other lessons"
                : lessonTitle(group.lessonNumber).en}{" "}
              · {group.topics.length} units
            </span>
          </div>
          <StudentSection variant="flat" className="study-list">
            {group.topics.map((topic, index) => {
              const entry = statusByStoryId[topicStoryId(topic)] ?? {
                status: "not-started" as LessonRowStatus,
              };
              const locked = entry.status === "locked";
              const current = entry.status === "in-progress";
              const description =
                topic.description &&
                topic.description !== "Teacher published activity"
                  ? topic.description
                  : "";
              return (
                <article
                  className={`study-row ${current ? "is-current" : ""} ${locked ? "is-locked" : ""}`}
                  key={topic.id}
                >
                  <span className="study-index">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div className="study-row-copy">
                    <span className="study-row-title" lang="zh-Hant">
                      {topic.name}
                    </span>
                    {description && (
                      <span className="study-row-desc">{description}</span>
                    )}
                  </div>
                  <div className="study-row-action">
                    {entry.status === "completed" && (
                      <StudentStatusPill tone="success">
                        已完成 · Complete
                      </StudentStatusPill>
                    )}
                    {locked && (
                      <StudentStatusPill tone="neutral">
                        尚未開放 · Locked
                      </StudentStatusPill>
                    )}
                    {!locked && (
                      <StudentButton
                        variant={current ? "primary" : "secondary"}
                        size={current ? "default" : "sm"}
                        iconTrailing={current ? "arrow_forward" : undefined}
                        onClick={() => onOpenTopic(topic)}
                      >
                        {entry.status === "completed"
                          ? "複習 · Review"
                          : current
                            ? "繼續 · Continue"
                            : "開始 · Start"}
                      </StudentButton>
                    )}
                  </div>
                  {current && (
                    <div
                      className="study-phases"
                      aria-label="學習階段 · Lesson phases"
                    >
                      {phases.map((label, i) => (
                        <span
                          className={
                            entry.phases && Object.values(entry.phases)[i]
                              ? "is-done"
                              : ""
                          }
                          key={label}
                        >
                          <StudentIcon
                            name={
                              entry.phases && Object.values(entry.phases)[i]
                                ? "check_circle"
                                : "radio_button_unchecked"
                            }
                            size={15}
                            role="decorative"
                          />
                          {label}
                          <small>
                            {
                              [
                                "Vocabulary",
                                "Quiz",
                                "Speaking",
                                "Conversation",
                              ][i]
                            }
                          </small>
                        </span>
                      ))}
                    </div>
                  )}
                </article>
              );
            })}
          </StudentSection>
        </section>
      ))}

    </StudentPage>
  );
}
