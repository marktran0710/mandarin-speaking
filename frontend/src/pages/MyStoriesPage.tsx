import { useEffect, useState } from "react";
import {
  canUseDatabase,
  HelpRequest,
  listAudioRecords,
  listStorySubmissions,
  listVocabQuizAttempts,
  type StorySubmission,
} from "../services/database";
import { BiLabel, BiText } from "../components/BiLabel";
import StudentIcon from "../components/StudentIcon";
import "../components/BiLabel.css";
import "./MyStoriesPage.css";
import "./MyStoriesStudent.css";
import StudentHelpCard from "../components/student/StudentHelpCard";
import MyStoryFeedbackHistory from "../components/MyStoryFeedbackHistory";
import {
  getAverageMetric,
  getStudentTopics,
} from "../utils/myStoriesUtils";
import { getStudentId, getStudentName } from "../utils/studentSession";
import {
  groupTopicsByLesson,
  isLessonGroupUnlocked,
  isStoryFinished,
  lessonCompletion,
  lessonTitle,
  topicStoryId,
  type LessonGroup,
} from "../utils/lessonGroups";
import { loadBestLocalStars, starsByStory } from "../utils/quizTiers";
import { loadSubmittedStoryIds } from "../utils/storyLevelProgress";
import { topicHasQuiz } from "../utils/topicQuiz";
import type { Topic } from "../components/TopicSelector";

export interface AudioRecord {
  id: string;
  timestamp: string;
  duration: number;
  transcription: string;
  model: string;
  topicId?: string;
  studentId?: string | null;
  imageUrl?: string;
  imageIndex?: number;
  audioUrl?: string;
  praatMetrics?: any;
}

export interface WordProsody {
  token: string;
  index: number;
  pitch_contour: Array<[number, number]>;
  reference_contour?: Array<[number, number]>;
  mean_pitch: number;
  pitch_range: number;
  contour_shape: string;
  feedback: string;
}

interface MyStoriesPageProps {
  records: AudioRecord[];
  helpRequests?: HelpRequest[];
  onRaiseHand?: (message: string) => void;
  publishedTopics?: import("../components/TopicSelector").Topic[];
  /** Sends the student back to the lesson list (table of contents) to
   * actually practice — this page is an overview only, no per-picture
   * recording detail lives here anymore. */
  onBrowsePractice?: () => void;
}

type ProfileTab = "lesson" | "story";

// Same four-color rotation as TopicSelector's lesson tiles (kept as a
// separate copy here rather than a shared import, so each page's tile
// styling can drift independently — see design_system_ink_and_seal memory).
const LESSON_TILE_CLASSES = [
  "profile-tile-seal",
  "profile-tile-jade",
  "profile-tile-tone1",
  "profile-tile-celadon",
];

function lessonTileClass(group: LessonGroup, unlocked: boolean): string {
  if (!unlocked) return "profile-tile-locked";
  if (group.lessonNumber === null) return "profile-tile-other";
  return LESSON_TILE_CLASSES[(group.lessonNumber - 1) % LESSON_TILE_CLASSES.length];
}

/** The personal story list only includes stories the learner has touched.
 * Topic ids can be tier-suffixed while completion records keep the raw
 * teacher-story id, so accept either form. */
export function topicWasStarted(
  topic: Pick<Topic, "id" | "sourceStory">,
  activityStoryIds: ReadonlySet<string>,
): boolean {
  const topicIds = [topic.id, topicStoryId(topic)];
  return topicIds.some((topicId) =>
    Array.from(activityStoryIds).some(
      (activityId) =>
        activityId === topicId ||
        activityId.startsWith(`${topicId}-`) ||
        topicId.startsWith(`${activityId}-`),
    ),
  );
}

export default function MyStoriesPage({
  records,
  helpRequests = [],
  onRaiseHand,
  publishedTopics,
  onBrowsePractice,
}: MyStoriesPageProps) {
  const [mySubmissions, setMySubmissions] = useState<StorySubmission[]>([]);
  const [persistedRecords, setPersistedRecords] = useState<AudioRecord[]>([]);
  const [quizAttemptStoryIds, setQuizAttemptStoryIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [serverStarsByStory, setServerStarsByStory] = useState<Record<string, 0 | 1 | 2 | 3>>({});
  const [profileTab, setProfileTab] = useState<ProfileTab>("lesson");

  useEffect(() => {
    if (!canUseDatabase()) return;
    let cancelled = false;
    const studentId = getStudentId();
    const studentName = getStudentName();
    void Promise.allSettled([
      listStorySubmissions(undefined, { studentId, studentName }),
      listVocabQuizAttempts(undefined, { studentId, studentName }),
      listAudioRecords({ limit: 1000, studentId }),
    ])
      .then(([subsResult, quizResult, audioResult]) => {
        if (cancelled) return;
        if (subsResult.status === "fulfilled") {
          const mine = subsResult.value
          .filter((s) => (studentId ? s.studentId === studentId : s.studentName === studentName))
          .sort((a, b) => b.submittedAt.localeCompare(a.submittedAt));
          setMySubmissions(mine);
        }
        if (quizResult.status === "fulfilled") {
          setQuizAttemptStoryIds(new Set(quizResult.value.map((attempt) => attempt.storyId)));
          setServerStarsByStory(starsByStory(quizResult.value));
        }
        if (audioResult.status === "fulfilled") {
          setPersistedRecords(audioResult.value as AudioRecord[]);
        }
      })
      .catch(() => {
        // Silently skip — the overview above is still fully usable.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const studentTopics = publishedTopics ?? getStudentTopics();
  const recordsById = new Map<string, AudioRecord>();
  for (const record of [...records, ...persistedRecords]) recordsById.set(record.id, record);
  const allRecords = Array.from(recordsById.values());
  const analyzedRecords = allRecords.filter((record) => record.praatMetrics);
  const averageFluency = getAverageMetric(analyzedRecords, "fluency_score");
  const averageToneAccuracy = getAverageMetric(analyzedRecords, "tone_accuracy");

  const submittedIds = new Set([
    ...loadSubmittedStoryIds(),
    ...mySubmissions.map((submission) => submission.storyId),
  ]);
  const starsForTopic = (topic: Topic): 0 | 1 | 2 | 3 => {
    const suffixes = ["", "-medium", "-hard"];
    const serverBest = suffixes.reduce<0 | 1 | 2 | 3>((best, suffix) => {
      const value = serverStarsByStory[`${topic.id}${suffix}`] ?? 0;
      return value > best ? value : best;
    }, 0);
    const localBest = loadBestLocalStars(topic.id);
    return Math.max(localBest, serverBest) as 0 | 1 | 2 | 3;
  };
  const groups = groupTopicsByLesson(studentTopics);
  const numberedGroups = groups.filter((group) => group.lessonNumber !== null);

  const quizTopics = studentTopics.filter((topic) => topicHasQuiz(topic));
  const totalStars = quizTopics.reduce(
    (sum, topic) => sum + starsForTopic(topic),
    0,
  );
  const maxStars = quizTopics.length * 3;

  const activityStoryIds = new Set<string>([
    ...submittedIds,
    ...allRecords.map((record) => record.topicId).filter((id): id is string => Boolean(id)),
    ...mySubmissions.map((submission) => submission.storyId),
    ...quizAttemptStoryIds,
    ...quizTopics
      .filter((topic) => starsForTopic(topic) > 0)
      .map((topic) => topic.id),
  ]);
  const activeStoryTopics = studentTopics.filter((topic) =>
    topicWasStarted(topic, activityStoryIds),
  );

  const lessonsDone = numberedGroups.filter((group) => {
    const { done, total } = lessonCompletion(group, submittedIds, starsForTopic);
    return total > 0 && done === total;
  }).length;
  const lessonsTotal = numberedGroups.length;

  return (
    <div className="my-stories-page">
      <div className="stories-header">
        <p className="stories-kicker">
          <BiLabel zh="我的學習" pinyin="Wǒ de xuéxí" en="My learning" />
        </p>
        <h1>
          <BiLabel zh="我的學習" pinyin="Wǒ de xuéxí" en="My learning" align="left" />
        </h1>
        <p className="stories-subtitle">
          <BiText
            zh="看看你學到哪裡了。想再練習，就回課程列表。"
            pinyin="Kànkan nǐ xué dào nǎlǐ le. Xiǎng zài liànxí, jiù huí kèchéng lièbiǎo."
            en="See your overall progress and stars — go back to the lesson list to practice."
          />
        </p>
      </div>

      <section className="profile-stats" aria-label="Overall progress">
        <div className="profile-stat-card">
          <span className="profile-stat-icon" aria-hidden="true"><StudentIcon name="star" /></span>
          <span className="profile-stat-label">
            <BiLabel zh="總星星" en="Total stars" align="center" />
          </span>
          <strong className="profile-stat-value profile-stat-stars">
            {totalStars}
            <span className="profile-stat-max"> / {maxStars}</span>
          </strong>
        </div>

        <div className="profile-stat-card">
          <span className="profile-stat-icon" aria-hidden="true"><StudentIcon name="check" /></span>
          <span className="profile-stat-label">
            <BiLabel zh="課程完成" en="Lessons complete" align="center" />
          </span>
          <strong className="profile-stat-value">
            {lessonsDone}
            <span className="profile-stat-max"> / {lessonsTotal}</span>
          </strong>
          <div className="summary-progress">
            <span
              style={{
                width: `${
                  lessonsTotal === 0 ? 0 : Math.round((lessonsDone / lessonsTotal) * 100)
                }%`,
              }}
            />
          </div>
        </div>

        <div className="profile-stat-card">
          <span className="profile-stat-icon" aria-hidden="true"><StudentIcon name="voice" /></span>
          <span className="profile-stat-label">
            <BiLabel zh="發音表現" en="Tone accuracy (avg)" align="center" />
          </span>
          <strong className="profile-stat-value">
            {averageToneAccuracy === null ? "—" : `${averageToneAccuracy}%`}
          </strong>
        </div>

        <div className="profile-stat-card">
          <span className="profile-stat-icon" aria-hidden="true"><StudentIcon name="chart" /></span>
          <span className="profile-stat-label">
            <BiLabel zh="說得順不順" en="Fluency (avg)" align="center" />
          </span>
          <strong className="profile-stat-value">
            {averageFluency === null ? "—" : `${averageFluency}/100`}
          </strong>
        </div>
      </section>

      <StudentHelpCard helpRequests={helpRequests} onRaiseHand={onRaiseHand} />

      <MyStoryFeedbackHistory submissions={mySubmissions} />

      <section className="profile-overview" aria-label="Progress overview">
        <div className="profile-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={profileTab === "lesson"}
            className={`profile-tab-btn ${profileTab === "lesson" ? "active" : ""}`}
            onClick={() => setProfileTab("lesson")}
          >
            <BiLabel zh="按課程" en="By lesson" align="center" />
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={profileTab === "story"}
            className={`profile-tab-btn ${profileTab === "story" ? "active" : ""}`}
            onClick={() => setProfileTab("story")}
          >
            <BiLabel zh="按故事" en="By story" align="center" />
          </button>
        </div>

        {profileTab === "lesson" ? (
          <div className="profile-lesson-list">
            {groups.map((group, index) => {
              const unlocked = isLessonGroupUnlocked(groups, index, submittedIds, starsForTopic);
              const { done, total } = lessonCompletion(group, submittedIds, starsForTopic);
              const finished = total > 0 && done === total;
              const groupQuizTopics = group.topics.filter((topic) => topicHasQuiz(topic));
              const groupStars = groupQuizTopics.reduce(
                (sum, topic) => sum + starsForTopic(topic),
                0,
              );
              const title =
                group.lessonNumber !== null
                  ? lessonTitle(group.lessonNumber)
                  : { zh: "其他練習", pinyin: "Qítā liànxí", en: "Extra practice" };

              return (
                <div
                  key={group.lessonNumber ?? "other"}
                  className={`profile-lesson-row ${unlocked ? "" : "is-locked"}`}
                >
                  <div className={`profile-lesson-tile ${lessonTileClass(group, unlocked)}`}>
                    {group.lessonNumber !== null ? (
                      <>
                        <span>LESSON</span>
                        <strong>{group.lessonNumber}</strong>
                      </>
                    ) : (
                      <StudentIcon name="spark" size={23} />
                    )}
                  </div>

                  <div className="profile-lesson-main">
                    <p className="profile-lesson-title">
                      <BiLabel {...title} block align="left" />
                    </p>
                    {groupQuizTopics.length > 0 && (
                      <p
                        className="profile-lesson-stars"
                        aria-label={`${groupStars} of ${groupQuizTopics.length * 3} quiz stars earned`}
                      >
                        {Array.from({ length: groupQuizTopics.length * 3 }, (_, starIndex) => (
                          <StudentIcon
                            key={starIndex}
                            name="star"
                            size={14}
                            aria-hidden="true"
                            className={starIndex < groupStars ? "is-earned" : "is-empty"}
                          />
                        ))}
                      </p>
                    )}
                  </div>

                  <div className="profile-lesson-side">
                    {unlocked ? (
                      <>
                        <span className={`profile-chip ${finished ? "profile-chip-done" : ""}`}>
                          {done}/{total} 完成
                        </span>
                        <button
                          type="button"
                          className="btn-profile-practice"
                          onClick={onBrowsePractice}
                        >
                          {finished ? (
                            <BiLabel zh="複習" en="Review" />
                          ) : (
                            <BiLabel zh="去練習" en="Practice" />
                          )} <StudentIcon name="arrow-right" size={16} aria-hidden="true" />
                        </button>
                      </>
                    ) : (
                      <span className="profile-chip profile-chip-locked">
                        <StudentIcon name="lock" size={14} aria-hidden="true" />
                        <BiLabel
                          zh="先完成上一課"
                          en="finish the previous lesson"
                        />
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="profile-story-list">
            {activeStoryTopics.length === 0 ? (
              <p className="profile-story-empty">
                <BiLabel
                  zh="你還沒有開始任何故事。先到課程列表練習吧！"
                  pinyin="Nǐ hái méiyǒu kāishǐ rènhé gùshì. Xiān dào kèchéng lièbiǎo liànxí ba!"
                  en="No stories started yet. Start one from the lesson list and it will appear here."
                  align="center"
                />
              </p>
            ) : activeStoryTopics.map((topic) => {
              const hasQuiz = topicHasQuiz(topic);
              const stars = hasQuiz ? starsForTopic(topic) : null;
              const finished = isStoryFinished(topic, submittedIds, starsForTopic);
              const started = topicWasStarted(topic, activityStoryIds);
              const previewImage = topic.images[0];

              return (
                <div key={topic.id} className="profile-story-row">
                  <div className="profile-story-thumb">
                    {previewImage ? <img src={previewImage} alt="" /> : <StudentIcon name="image" size={20} aria-hidden="true" />}
                  </div>

                  <div className="profile-story-main">
                    <p className="profile-story-name">{topic.name}</p>
                    <p className="profile-story-tag">
                      {topic.lessonNumber != null ? (
                        <BiLabel
                          zh={`第 ${topic.lessonNumber} 課`}
                          en={`Lesson ${topic.lessonNumber}`}
                        />
                      ) : (
                        <BiLabel zh="其他" en="Extra" />
                      )}
                    </p>
                  </div>

                  {stars !== null && (
                    <span className="profile-story-stars" aria-label={`${stars} of 3 quiz stars earned`}>
                      {Array.from({ length: 3 }, (_, starIndex) => (
                        <StudentIcon
                          key={starIndex}
                          name="star"
                          size={14}
                          aria-hidden="true"
                          className={starIndex < stars ? "is-earned" : "is-empty"}
                        />
                      ))}
                    </span>
                  )}

                  <span
                    className={`profile-chip ${
                      finished ? "profile-chip-done" : started ? "" : "profile-chip-todo"
                    }`}
                  >
                    {finished ? (
                      <BiLabel zh="完成" en="Done" />
                    ) : started ? (
                      <BiLabel zh="練習中" en="In progress" />
                    ) : (
                      <BiLabel zh="還沒開始" en="Not started" />
                    )}
                  </span>

                  <button
                    type="button"
                    className="btn-profile-practice ghost"
                    onClick={onBrowsePractice}
                  >
                    {finished ? (
                      <BiLabel zh="複習" en="Review" />
                    ) : started ? (
                      <BiLabel zh="繼續" en="Continue" />
                    ) : (
                      <BiLabel zh="練習" en="Practice" />
                    )} <StudentIcon name="arrow-right" size={16} aria-hidden="true" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
