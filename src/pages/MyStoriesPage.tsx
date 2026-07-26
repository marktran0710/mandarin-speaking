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
import RecordCard from "../components/RecordCard";
import {
  getAverageMetric,
  getPromptImages,
  getSessionName,
  getStudentTopics,
  isPromptRecord,
} from "../utils/myStoriesUtils";

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
  onDeleteRecord: (id: string) => void;
  onPracticeImage?: (topicId: string, imageIndex: number) => void;
  helpRequests?: HelpRequest[];
  onRaiseHand?: (message: string) => void;
  publishedTopics?: import("../components/TopicSelector").Topic[];
}

export default function MyStoriesPage({
  records,
  onDeleteRecord,
  onPracticeImage,
  helpRequests = [],
  onRaiseHand,
  publishedTopics,
}: MyStoriesPageProps) {
  const [mySubmissions, setMySubmissions] = useState<StorySubmission[]>([]);

  useEffect(() => {
    if (!canUseDatabase()) return;
    let cancelled = false;
    listStorySubmissions()
      .then((subs) => {
        if (cancelled) return;
        const studentName = getSessionName("studentSession", "Student");
        const mine = subs
          .filter((s) => s.studentName === studentName)
          .sort((a, b) => b.submittedAt.localeCompare(a.submittedAt));
        setMySubmissions(mine);
      })
      .catch(() => {
        // Silently skip — the workbook view above is still fully usable.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const studentTopics = publishedTopics ?? getStudentTopics();
  const promptImages = getPromptImages(studentTopics);
  const completedPrompts = promptImages.filter((prompt) =>
    records.some((record) => isPromptRecord(record, prompt)),
  ).length;
  const analyzedRecords = records.filter((record) => record.praatMetrics);
  const averageFluency = getAverageMetric(analyzedRecords, "fluency_score");
  return (
    <div className="my-stories-page">
        <div className="stories-header">
          <p className="stories-kicker">
            <BiLabel zh="我的練習" pinyin="Wǒ de liànxí" en="My practice" />
          </p>
          <h1>
            <BiLabel zh="我的故事練習本" pinyin="Wǒ de gùshì liànxí běn" en="My Story Workbook" />
          </h1>
          <p className="stories-subtitle">
            <BiText
              zh="選一張圖片，錄你的故事部分，等回饋出來後再修改。"
              pinyin="Xuǎn yì zhāng túpiàn, lù nǐ de gùshì bùfen, děng huíkuì chūlái hòu zài xiūgǎi."
              en="Choose a picture, record your story part, then revise when feedback is ready."
            />
          </p>
        </div>

        <section className="student-progress-panel" aria-label="Learning progress">
          <div className="student-progress-main">
            <span><BiLabel zh="進度" pinyin="Jìndù" en="Progress" /></span>
            <strong>
              {completedPrompts}/{promptImages.length}
              {promptImages.length > 0 && completedPrompts === promptImages.length && (
                <span className="progress-complete-badge" title="全部部分完成！ All scenes complete!">🎉</span>
              )}
            </strong>
            <div className={`summary-progress${completedPrompts === promptImages.length && promptImages.length > 0 ? " is-complete" : ""}`}>
              <span
                style={{
                  width: `${promptImages.length === 0 ? 0 : Math.round(
                    (completedPrompts / promptImages.length) * 100,
                  )}%`,
                }}
              />
            </div>
          </div>
          <div className="student-progress-stats">
            <span>
              <BiLabel zh={`${records.length} 個錄音`} pinyin={`${records.length} ge lùyīn`} en={`${records.length} recordings`} />
            </span>
            <span>
              {averageFluency === null ? (
                <BiLabel zh="還沒有流暢度分數" pinyin="Hái méiyǒu liúchàng dù fēnshù" en="No fluency score yet" />
              ) : (
                <BiLabel zh={`流暢度 ${averageFluency}/100`} pinyin={`Liúchàng dù ${averageFluency}/100`} en={`${averageFluency}/100 fluency`} />
              )}
            </span>
          </div>
        </section>

        <StudentHelpCard
          helpRequests={helpRequests}
          onRaiseHand={onRaiseHand}
        />

        <MyStoryFeedbackHistory submissions={mySubmissions} />

        <div className="learning-workbook">
          {studentTopics.map((topic) => {
            const prompts = promptImages.filter(
              (prompt) => prompt.topicId === topic.id,
            );
            const topicRecords = records.filter(
              (record) => record.topicId === topic.id,
            );
            const topicCompleted = prompts.filter((prompt) =>
              records.some((record) => isPromptRecord(record, prompt)),
            ).length;
            const topicProgress = prompts.length === 0 ? 0 : Math.round(
              (topicCompleted / prompts.length) * 100,
            );

            return (
              <section className="topic-workbook-section" key={topic.id}>
                <div className="topic-workbook-header">
                  <div>
                    <p className="stories-kicker">
                      {topic.lessonNumber != null && (
                        <span className="topic-lesson-badge">
                          <BiLabel zh={`第 ${topic.lessonNumber} 課`} pinyin={`Dì ${topic.lessonNumber} kè`} en={`Lesson ${topic.lessonNumber}`} />
                        </span>
                      )}
                      {topic.name}
                    </p>
                    <h2>{topic.description}</h2>
                  </div>
                  <div className="topic-progress-card">
                    <strong>{topicCompleted}/{prompts.length}</strong>
                    <span>
                      <BiLabel zh={`完成 ${topicProgress}%`} pinyin={`Wánchéng ${topicProgress}%`} en={`${topicProgress}% complete`} />
                    </span>
                  </div>
                </div>

                <div className="prompt-grid">
                  {prompts.map((prompt) => {
                    const promptRecords = records.filter((record) =>
                      isPromptRecord(record, prompt),
                    );
                    const latestRecord = promptRecords[0];
                    const attemptCount = promptRecords.length;
                    const isRevised = attemptCount > 1;
                    const hasFeedback = Boolean(
                      latestRecord?.praatMetrics?.ai_feedback,
                    );

                    return (
                      <article
                        className={`prompt-card ${
                          latestRecord ? "completed" : ""
                        }`}
                        key={`${prompt.topicId}-${prompt.imageIndex}`}
                      >
                        <div className="prompt-image">
                          <img
                            src={prompt.imageUrl}
                            alt={`${prompt.topicName} prompt ${
                              prompt.imageIndex + 1
                            }`}
                          />
                        </div>

                        <div className="prompt-content">
                          <div className="prompt-title-row">
                            <div>
                              <p className="picture-topic">
                                <BiLabel zh={`第 ${prompt.imageIndex + 1} 部分`} pinyin={`Dì ${prompt.imageIndex + 1} bùfen`} en={`Part ${prompt.imageIndex + 1}`} />
                              </p>
                              <h3>{prompt.topicName}</h3>
                            </div>
                            <span
                              className={`learning-status ${
                                isRevised ? "revised" : latestRecord ? "ready" : "todo"
                              }`}
                            >
                              {latestRecord ? (
                                isRevised ? (
                                  <BiLabel zh="已修改" pinyin="Yǐ xiūgǎi" en="Revised" />
                                ) : hasFeedback ? (
                                  <BiLabel zh="回饋好了" pinyin="Huíkuì hǎo le" en="Feedback ready" />
                                ) : (
                                  <BiLabel zh="已錄音" pinyin="Yǐ lùyīn" en="Recorded" />
                                )
                              ) : (
                                <BiLabel zh="還沒錄音" pinyin="Hái méi lùyīn" en="Needs recording" />
                              )}
                            </span>
                          </div>

                          {prompt.vocabulary.length > 0 && (
                            <div className="picture-vocabulary">
                              {prompt.vocabulary.map((word) => (
                                <span key={word}>{word}</span>
                              ))}
                            </div>
                          )}

                          <button
                            type="button"
                            className="btn-record-picture"
                            onClick={() =>
                              onPracticeImage?.(
                                prompt.topicId,
                                prompt.imageIndex,
                              )
                            }
                          >
                            {latestRecord ? (
                              <BiLabel zh="再錄一次來修改" pinyin="Zài lù yí cì lái xiūgǎi" en="Revise with another recording" />
                            ) : (
                              <BiLabel zh="錄這個部分" pinyin="Lù zhège bùfen" en="Record this part" />
                            )}
                          </button>

                          {latestRecord && (
                            <div className="revision-summary">
                              <strong>
                                <BiLabel
                                  zh={`已經試了 ${attemptCount} 次`}
                                  pinyin={`Yǐjīng shì le ${attemptCount} cì`}
                                  en={`${attemptCount} ${attemptCount === 1 ? "attempt" : "attempts"} collected`}
                                />
                              </strong>
                            </div>
                          )}

                          {latestRecord ? (
                            <details className="prompt-feedback-details">
                              <summary><BiLabel zh="看回饋" pinyin="Kàn huíkuì" en="View feedback" /></summary>
                              <RecordCard
                                record={latestRecord}
                                onDeleteRecord={onDeleteRecord}
                                compact
                              />
                            </details>
                          ) : (
                            <div className="picture-empty-result">
                              <BiLabel zh="準備好了就錄這張圖片。" pinyin="Zhǔnbèi hǎo le jiù lù zhè zhāng túpiàn." en="Record this picture when you are ready." />
                            </div>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>

                {topicRecords.length > 0 && (
                  <p className="topic-record-count">
                    <BiLabel
                      zh={`這個主題一共有 ${topicRecords.length} 次嘗試。`}
                      pinyin={`Zhège zhǔtí yígòng yǒu ${topicRecords.length} cì chángshì.`}
                      en={`${topicRecords.length} total ${topicRecords.length === 1 ? "attempt" : "attempts"} in this topic.`}
                    />
                  </p>
                )}
              </section>
            );
          })}
        </div>
      </div>
  );
}
