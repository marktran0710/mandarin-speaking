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
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import type { StudentUiCopyKey } from "../../i18n/student-ui-copy";
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
const phases: StudentUiCopyKey[] = ["phaseVocabulary", "phaseQuiz", "phaseSpeaking", "phaseConversation"];
const phaseIcons: Partial<Record<StudentUiCopyKey, string>> = {
  phaseVocabulary: "book",
  phaseQuiz: "quiz",
  phaseSpeaking: "microphone",
  phaseConversation: "message",
};
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
  const heroImage = hero?.images?.[0];
  const words = useMemo(
    () => (hero ? speakingVocabularyItems(hero).slice(0, 5) : []),
    [hero],
  );
  const header = (
    <StudentPageHeader
      eyebrowKey="study"
      titleKey="courseTitle"
    />
  );
  if (!groups.length)
    return (
      <StudentPage
        layout="hub"
        header={header}
        state="empty"
        emptyTitle={<StudentSystemText k="noCourses" />}
        emptyText={<StudentSystemText k="coursesPublished" />}
      />
    );
  const heroCard = (
    <StudentSection variant="tinted" className="study-hero-card">
      <span className="study-kicker">
        {hero ? (
          <>
            <StudentSystemText k="keepGoing" />
          </>
        ) : (
          <>
            <StudentSystemText k="courseComplete" />
          </>
        )}
      </span>
      {hero ? (
        <div className="study-hero-card__layout">
          <div className="study-hero-card__copy">
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
                <StudentSystemText k="continue" withinControl />
              </>
            ) : (
              <>
                <StudentSystemText k="start" withinControl />
              </>
            )}
          </StudentButton>
          </div>
          {heroImage && (
            <div className="study-hero-card__media">
              <img
                src={heroImage}
                alt={`${hero.name} lesson scene`}
                loading="lazy"
              />
            </div>
          )}
        </div>
      ) : (
        <>
          <h2><StudentSystemText k="allCoursesComplete" /></h2>
          <p><StudentSystemText k="reviewAnyLesson" /></p>
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
            <StudentSystemText k="focusWords" />
          </h2>
          <span>{words.length} <StudentSystemText k="wordsCount" /></span>
        </div>
        {words.length ? (
          words.map((word) => (
            <div className="study-word" key={word.wordId}>
              <span>
                <strong lang="zh-Hant">{word.word}</strong>
              </span>
              <StudentAudioControl
                audioUrl={word.audioUrl}
                labelKey="listen"
                compact
              />
            </div>
          ))
        ) : (
          <p>
            <StudentSystemText k="focusWordsEmpty" />
          </p>
        )}
      </StudentSection>
      <StudentSection variant="tinted" className="study-progress">
        <div>
          <strong><StudentSystemText k="learningProgress" /></strong>
          <span>{percent}% 完成 · <StudentSystemText k="steadyPace" /></span>
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
                ? <StudentSystemText k="otherLessons" />
                : `第 ${group.lessonNumber} 課 · ${lessonTitle(group.lessonNumber).zh}`}
            </strong>
            <span>
              {group.lessonNumber == null
                ? ""
                : lessonTitle(group.lessonNumber).zh}{" "}
              · {group.topics.length} <StudentSystemText k="unitsCount" />
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
                        <StudentSystemText k="completed" withinControl />
                      </StudentStatusPill>
                    )}
                    {locked && (
                      <StudentStatusPill tone="neutral">
                        <StudentSystemText k="locked" withinControl />
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
                          ? <StudentSystemText k="review" withinControl />
                          : current
                            ? <StudentSystemText k="continue" withinControl />
                            : <StudentSystemText k="start" withinControl />}
                      </StudentButton>
                    )}
                  </div>
                  {current && (
                    <div
                      className="study-phases"
                       aria-label="學習階段"
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
                                : (phaseIcons[label] ?? "book")
                            }
                            size={15}
                            role="decorative"
                          />
                          <StudentSystemText k={label} />
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
