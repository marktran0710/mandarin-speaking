import { useEffect, useState } from "react";
import {
  canUseDatabase,
  HelpRequest,
  listStorySubmissions,
  type StorySubmission,
} from "../services/database";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";
import "./MyStoriesPage.css";
import StudentHelpCard from "../components/StudentHelpCard";
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
import { loadBestLocalStars } from "../utils/quizTiers";
import { loadSubmittedStoryIds } from "../utils/storyLevelProgress";
import { topicHasQuiz } from "../utils/topicQuiz";

export interface AudioRecord {
  id: string;
  timestamp: string;
  duration: number;
  transcription: string;
  model: string;
  topicId?: string;
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

export default function MyStoriesPage({
  records,
  helpRequests = [],
  onRaiseHand,
  publishedTopics,
  onBrowsePractice,
}: MyStoriesPageProps) {
  const [mySubmissions, setMySubmissions] = useState<StorySubmission[]>([]);
  const [profileTab, setProfileTab] = useState<ProfileTab>("lesson");

  useEffect(() => {
    if (!canUseDatabase()) return;
    let cancelled = false;
    listStorySubmissions()
      .then((subs) => {
        if (cancelled) return;
        const studentId = getStudentId();
        const studentName = getStudentName();
        const mine = subs
          .filter((s) => (studentId ? s.studentId === studentId : s.studentName === studentName))
          .sort((a, b) => b.submittedAt.localeCompare(a.submittedAt));
        setMySubmissions(mine);
      })
      .catch(() => {
        // Silently skip — the overview above is still fully usable.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const studentTopics = publishedTopics ?? getStudentTopics();
  const analyzedRecords = records.filter((record) => record.praatMetrics);
  const averageFluency = getAverageMetric(analyzedRecords, "fluency_score");
  const averageToneAccuracy = getAverageMetric(analyzedRecords, "tone_accuracy");

  const submittedIds = loadSubmittedStoryIds();
  const groups = groupTopicsByLesson(studentTopics);
  const numberedGroups = groups.filter((group) => group.lessonNumber !== null);

  const quizTopics = studentTopics.filter((topic) => topicHasQuiz(topic));
  const totalStars = quizTopics.reduce(
    (sum, topic) => sum + loadBestLocalStars(topic.id),
    0,
  );
  const maxStars = quizTopics.length * 3;

  const lessonsDone = numberedGroups.filter((group) => {
    const { done, total } = lessonCompletion(group, submittedIds);
    return total > 0 && done === total;
  }).length;
  const lessonsTotal = numberedGroups.length;

  return (
    <div className="my-stories-page">
      <div className="stories-header">
        <p className="stories-kicker">
          <BiLabel zh="我的練習" pinyin="Wǒ de liànxí" en="My practice" />
        </p>
        <h1>
          <BiLabel zh="我的成績" pinyin="Wǒ de chéngjì" en="My Profile" />
        </h1>
        <p className="stories-subtitle">
          <BiText
            zh="看看你學了多少、拿了幾顆星。想練習就回課程列表。"
            pinyin="Kànkan nǐ xué le duōshǎo, ná le jǐ kē xīng. Xiǎng liànxí jiù huí kèchéng lièbiǎo."
            en="See your overall progress and stars — go back to the lesson list to practice."
          />
        </p>
      </div>

      <section className="profile-stats" aria-label="Overall progress">
        <div className="profile-stat-card">
          <span className="profile-stat-label">
            <BiLabel zh="總星星" pinyin="Zǒng xīngxīng" en="Total stars" />
          </span>
          <strong className="profile-stat-value profile-stat-stars">
            {totalStars}
            <span className="profile-stat-max"> / {maxStars}</span> ⭐
          </strong>
        </div>

        <div className="profile-stat-card">
          <span className="profile-stat-label">
            <BiLabel zh="課程完成" pinyin="Kèchéng wánchéng" en="Lessons complete" />
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
          <span className="profile-stat-label">
            <BiLabel zh="發音準確度" pinyin="Fāyīn zhǔnquèdù" en="Tone accuracy (avg)" />
          </span>
          <strong className="profile-stat-value">
            {averageToneAccuracy === null ? "—" : `${averageToneAccuracy}%`}
          </strong>
        </div>

        <div className="profile-stat-card">
          <span className="profile-stat-label">
            <BiLabel zh="流暢度" pinyin="Liúchàng dù" en="Fluency (avg)" />
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
            <BiLabel zh="按課程" pinyin="Àn kèchéng" en="By lesson" />
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={profileTab === "story"}
            className={`profile-tab-btn ${profileTab === "story" ? "active" : ""}`}
            onClick={() => setProfileTab("story")}
          >
            <BiLabel zh="按故事" pinyin="Àn gùshì" en="By story" />
          </button>
        </div>

        {profileTab === "lesson" ? (
          <div className="profile-lesson-list">
            {groups.map((group, index) => {
              const unlocked = isLessonGroupUnlocked(groups, index, submittedIds);
              const { done, total } = lessonCompletion(group, submittedIds);
              const finished = total > 0 && done === total;
              const groupQuizTopics = group.topics.filter((topic) => topicHasQuiz(topic));
              const groupStars = groupQuizTopics.reduce(
                (sum, topic) => sum + loadBestLocalStars(topic.id),
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
                      <strong>✦</strong>
                    )}
                  </div>

                  <div className="profile-lesson-main">
                    <p className="profile-lesson-title">
                      {title.zh} <span className="profile-lesson-pin">{title.pinyin}</span>
                    </p>
                    {groupQuizTopics.length > 0 && (
                      <p className="profile-lesson-stars">
                        {"⭐".repeat(groupStars)}
                        {"☆".repeat(groupQuizTopics.length * 3 - groupStars)}
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
                            <BiLabel zh="複習" pinyin="Fùxí" en="Review" />
                          ) : (
                            <BiLabel zh="去練習" pinyin="Qù liànxí" en="Practice" />
                          )}{" "}
                          →
                        </button>
                      </>
                    ) : (
                      <span className="profile-chip profile-chip-locked">
                        🔒{" "}
                        <BiLabel
                          zh="先完成上一課"
                          pinyin="Xiān wánchéng shàng yí kè"
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
            {studentTopics.map((topic) => {
              const hasQuiz = topicHasQuiz(topic);
              const stars = hasQuiz ? loadBestLocalStars(topic.id) : null;
              const submitted = submittedIds.has(topicStoryId(topic));
              const finished = isStoryFinished(topic, submittedIds);
              const previewImage = topic.images[0];

              return (
                <div key={topic.id} className="profile-story-row">
                  <div className="profile-story-thumb">
                    {previewImage ? <img src={previewImage} alt="" /> : "🖼️"}
                  </div>

                  <div className="profile-story-main">
                    <p className="profile-story-name">{topic.name}</p>
                    <p className="profile-story-tag">
                      {topic.lessonNumber != null ? (
                        <BiLabel
                          zh={`第 ${topic.lessonNumber} 課`}
                          pinyin={`Dì ${topic.lessonNumber} kè`}
                          en={`Lesson ${topic.lessonNumber}`}
                        />
                      ) : (
                        <BiLabel zh="其他" pinyin="Qítā" en="Extra" />
                      )}
                    </p>
                  </div>

                  {stars !== null && (
                    <span className="profile-story-stars">
                      {"⭐".repeat(stars)}
                      {"☆".repeat(3 - stars)}
                    </span>
                  )}

                  <span
                    className={`profile-chip ${
                      finished ? "profile-chip-done" : submitted ? "" : "profile-chip-todo"
                    }`}
                  >
                    {finished ? (
                      <BiLabel zh="完成" pinyin="Wánchéng" en="Done" />
                    ) : submitted ? (
                      <BiLabel zh="練習中" pinyin="Liànxí zhōng" en="In progress" />
                    ) : (
                      <BiLabel zh="還沒開始" pinyin="Hái méi kāishǐ" en="Not started" />
                    )}
                  </span>

                  <button
                    type="button"
                    className="btn-profile-practice ghost"
                    onClick={onBrowsePractice}
                  >
                    {submitted ? (
                      <BiLabel zh="複習" pinyin="Fùxí" en="Review" />
                    ) : (
                      <BiLabel zh="練習" pinyin="Liànxí" en="Practice" />
                    )}{" "}
                    →
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
