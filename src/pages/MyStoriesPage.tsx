import React, { useEffect, useState } from "react";
import PitchChart from "../components/PitchChart";
import { getTopicVocabulary } from "../components/TopicSelector";
import {
  canUseDatabase,
  createCustomStory as saveCustomStoryToDatabase,
  deleteCustomStoryFromDatabase,
  HelpRequest,
  listCustomStories,
  listStorySubmissions,
  type StorySubmission,
} from "../services/database";
import {
  CustomTeacherStory,
  NarrativeMode,
  VocabGroup,
  loadCustomStories,
  loadPublishedTeacherTopics,
  resolveImageUrl,
  saveCustomStories,
} from "../utils/teacherStories";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";
import StoryFeedbackCard from "../components/StoryFeedbackCard";
import "./MyStoriesPage.css";

interface AudioRecord {
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

interface WordProsody {
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
  mode?: "student" | "teacher";
  helpRequests?: HelpRequest[];
  onRaiseHand?: (message: string) => void;
  onResolveHelpRequest?: (id: string) => void;
  onRefreshRecords?: () => Promise<void>;
  onStorySaved?: () => void;
  publishedTopics?: import("../components/TopicSelector").Topic[];
}

interface PromptImage {
  topicId: string;
  topicName: string;
  description: string;
  imageUrl: string;
  imageIndex: number;
  vocabulary: string[];
}

interface CustomStoryValidationErrors {
  title?: string;
  learningGoal?: string;
  form?: string;
  frames?: Record<number, { imageUrl?: string; prompt?: string }>;
}

type TeacherView = "overview" | "help" | "materials" | "progress" | "recordings" | "submissions";

function getStudentTopics() {
  return loadPublishedTeacherTopics();
}

function getPromptImages(topics = getStudentTopics()): PromptImage[] {
  return topics.flatMap((topic) =>
    topic.images.map((imageUrl, imageIndex) => ({
      topicId: topic.id,
      topicName: topic.name,
      description: topic.description,
      imageUrl,
      imageIndex,
      vocabulary: getTopicVocabulary(topic, imageIndex),
    })),
  );
}

/** Normal-mode stories are a 6-scene story; Describe/Listen & Retell are single-frame activities. */
function frameCountForMode(mode: NarrativeMode): number {
  return mode === "story" ? 6 : 1;
}

interface StoryFrameGuide {
  zh: string;
  en: string;
  tip: string;
  color: string;
  accent: string;
  renderIcon: () => React.ReactElement;
}

const STORY_FRAME_GUIDES: StoryFrameGuide[] = [
  {
    zh: "開場 — 誰在哪裡？",
    en: "Scene 1 · Setting",
    tip: "Show the character(s) and location",
    color: "var(--jade)",
    accent: "var(--jade-soft)",
    renderIcon: () => (
      <g>
        <circle cx="72" cy="56" r="18" fill="var(--jade)" />
        <path d="M54 90 Q72 72 90 90 L90 108 L54 108 Z" fill="var(--jade)" opacity="0.8" />
        <path d="M128 38 C128 52 112 68 112 68 C112 68 96 52 96 38 C96 29 103 22 112 22 C121 22 128 29 128 38 Z" fill="var(--gold)" />
        <circle cx="112" cy="38" r="7" fill="white" />
      </g>
    ),
  },
  {
    zh: "第一個動作",
    en: "Scene 2 · First Action",
    tip: "What does the character do first?",
    color: "var(--seal)",
    accent: "var(--seal-soft)",
    renderIcon: () => (
      <g>
        <circle cx="88" cy="42" r="16" fill="var(--seal)" />
        <path d="M68 62 L88 58 L108 62" stroke="var(--seal)" strokeWidth="5" fill="none" strokeLinecap="round" />
        <path d="M72 62 L62 86 M78 62 L72 86" stroke="var(--seal)" strokeWidth="5" strokeLinecap="round" />
        <path d="M100 62 L108 82 M106 62 L116 80" stroke="var(--seal)" strokeWidth="5" strokeLinecap="round" />
        <path d="M52 70 L140 70" stroke="var(--seal)" strokeWidth="3" strokeDasharray="6 4" opacity="0.5" />
      </g>
    ),
  },
  {
    zh: "問題出現",
    en: "Scene 3 · Problem",
    tip: "A problem or surprise happens",
    color: "var(--gold)",
    accent: "var(--gold-soft)",
    renderIcon: () => (
      <g>
        <ellipse cx="88" cy="52" rx="34" ry="24" fill="var(--gold)" opacity="0.85" />
        <ellipse cx="68" cy="60" rx="22" ry="18" fill="var(--gold)" opacity="0.85" />
        <ellipse cx="108" cy="58" rx="26" ry="20" fill="var(--gold)" opacity="0.85" />
        <path d="M94 72 L80 96 L90 96 L80 114" stroke="var(--gold-deep)" strokeWidth="5" strokeLinecap="round" fill="none" />
      </g>
    ),
  },
  {
    zh: "尋求幫助",
    en: "Scene 4 · Asking for Help",
    tip: "Someone asks or offers to help",
    color: "var(--jade-deep)",
    accent: "var(--jade-soft)",
    renderIcon: () => (
      <g>
        <circle cx="62" cy="50" r="14" fill="var(--jade-deep)" />
        <path d="M48 72 Q62 60 76 72 L76 92 L48 92 Z" fill="var(--jade-deep)" opacity="0.8" />
        <circle cx="118" cy="50" r="14" fill="var(--jade-deep)" opacity="0.7" />
        <path d="M104 72 Q118 60 132 72 L132 92 L104 92 Z" fill="var(--jade-deep)" opacity="0.55" />
        <rect x="72" y="28" width="36" height="22" rx="6" fill="var(--gold)" />
        <polygon points="84,50 92,50 88,58" fill="var(--gold)" />
        <line x1="78" y1="36" x2="100" y2="36" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
        <line x1="78" y1="43" x2="94" y2="43" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
      </g>
    ),
  },
  {
    zh: "解決問題",
    en: "Scene 5 · Solution",
    tip: "Show how the problem gets solved",
    color: "var(--seal-deep)",
    accent: "var(--seal-soft)",
    renderIcon: () => (
      <g>
        <circle cx="88" cy="65" r="32" fill="var(--seal-deep)" opacity="0.15" />
        <circle cx="88" cy="65" r="26" fill="var(--seal-deep)" opacity="0.2" />
        <path d="M68 65 L82 79 L108 52" stroke="var(--seal-deep)" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <circle cx="118" cy="38" r="5" fill="var(--gold)" />
        <circle cx="60" cy="42" r="3" fill="var(--gold)" />
        <circle cx="126" cy="80" r="4" fill="var(--gold)" />
      </g>
    ),
  },
  {
    zh: "結尾感受",
    en: "Scene 6 · Ending Feeling",
    tip: "How does everyone feel at the end?",
    color: "var(--gold-deep)",
    accent: "var(--gold-soft)",
    renderIcon: () => (
      <g>
        <circle cx="88" cy="60" r="30" fill="var(--gold-deep)" opacity="0.15" />
        <circle cx="88" cy="60" r="24" fill="var(--gold-deep)" opacity="0.85" />
        <circle cx="80" cy="55" r="3.5" fill="white" />
        <circle cx="96" cy="55" r="3.5" fill="white" />
        <path d="M76 66 Q88 78 100 66" stroke="white" strokeWidth="3.5" strokeLinecap="round" fill="none" />
        <path d="M112 28 C112 24 116 22 118 26 C120 22 124 24 124 28 C124 34 118 38 118 38 C118 38 112 34 112 28 Z" fill="var(--gold-deep)" />
      </g>
    ),
  },
];

function resizeToCount<T>(items: T[], count: number, fill: T): T[] {
  if (items.length === count) return items;
  if (items.length > count) return items.slice(0, count);
  return [...items, ...Array.from({ length: count - items.length }, () => fill)];
}

const emptyCustomStoryDraft = {
  title: "Taiwan Community Story",
  learningGoal: "Students describe who, where, what happened, and how people solved the problem.",
  level: "Beginner speaking",
  lessonNumber: "",
  imageUrls: ["", "", "", "", "", ""],
  prompts: [
    "Introduce the place and the people.",
    "Describe the first event.",
    "Explain the problem or surprise.",
    "Tell the result and feeling.",
    "Revise the story with one clearer detail.",
    "Finish with a lesson or next step.",
  ],
  vocabulary: ["", "", "", "", "", ""],
  vocabularyPinyin: ["", "", "", "", "", ""],
  vocabularyGroups: [null, null, null, null, null, null] as (VocabGroup[] | null)[],
  grammarPattern: "",
  grammarExample: "",
  suggestedAnswers: ["", "", "", "", "", ""],
  listenAudioUrls: ["", "", "", "", "", ""],
  listenScripts: ["", "", "", "", "", ""],
  linear: false,
  firstFrameIsExample: false,
  narrativeMode: "story" as NarrativeMode,
};

function validateCustomStoryDraft(
  draft: typeof emptyCustomStoryDraft,
): CustomStoryValidationErrors {
  const errors: CustomStoryValidationErrors = {};
  const frameErrors: CustomStoryValidationErrors["frames"] = {};

  if (!draft.title.trim()) {
    errors.title = "Add a story title for students.";
  }

  if (!draft.learningGoal.trim()) {
    errors.learningGoal = "Add a learning goal so students know what to practice.";
  }

  draft.imageUrls.forEach((imageUrl, index) => {
    const imageMissing = !imageUrl.trim();

    if (imageMissing) {
      frameErrors[index] = {
        imageUrl: `Frame ${index + 1} needs an image URL or uploaded image.`,
      };
    }
  });

  if (Object.keys(frameErrors).length > 0) {
    errors.frames = frameErrors;
  }

  return errors;
}

export default function MyStoriesPage({
  records,
  onDeleteRecord,
  onPracticeImage,
  mode = "student",
  helpRequests = [],
  onRaiseHand,
  onResolveHelpRequest,
  onRefreshRecords,
  onStorySaved,
  publishedTopics,
}: MyStoriesPageProps) {
  const isTeacher = mode === "teacher";

  const [mySubmissions, setMySubmissions] = useState<StorySubmission[]>([]);

  useEffect(() => {
    if (isTeacher || !canUseDatabase()) return;
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
  }, [isTeacher]);

  if (isTeacher) {
    return (
      <TeacherDashboard
        records={records}
        onDeleteRecord={onDeleteRecord}
        helpRequests={helpRequests}
        onResolveHelpRequest={onResolveHelpRequest}
        onRefreshRecords={onRefreshRecords}
        onStorySaved={onStorySaved}
      />
    );
  }

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
            <BiLabel zh="我的練習" en="My practice" />
          </p>
          <h1>
            <BiLabel zh="我的故事練習本" en="My Story Workbook" />
          </h1>
          <p className="stories-subtitle">
            <BiText
              zh="選一張圖片，錄製你的故事段落，等回饋出來後再修改。"
              en="Choose a picture, record your story part, then revise when feedback is ready."
            />
          </p>
        </div>

        <section className="student-progress-panel" aria-label="Learning progress">
          <div className="student-progress-main">
            <span><BiLabel zh="進度" en="Progress" /></span>
            <strong>
              {completedPrompts}/{promptImages.length}
              {promptImages.length > 0 && completedPrompts === promptImages.length && (
                <span className="progress-complete-badge" title="全部場景完成！ All scenes complete!">🎉</span>
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
              <BiLabel zh={`${records.length} 筆錄音`} en={`${records.length} recordings`} />
            </span>
            <span>
              {averageFluency === null ? (
                <BiLabel zh="尚無流暢度分數" en="No fluency score yet" />
              ) : (
                <BiLabel zh={`流暢度 ${averageFluency}/100`} en={`${averageFluency}/100 fluency`} />
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
                          <BiLabel zh={`第 ${topic.lessonNumber} 課`} en={`Lesson ${topic.lessonNumber}`} />
                        </span>
                      )}
                      {topic.name}
                    </p>
                    <h2>{topic.description}</h2>
                  </div>
                  <div className="topic-progress-card">
                    <strong>{topicCompleted}/{prompts.length}</strong>
                    <span>
                      <BiLabel zh={`完成 ${topicProgress}%`} en={`${topicProgress}% complete`} />
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
                                <BiLabel zh={`第 ${prompt.imageIndex + 1} 部分`} en={`Part ${prompt.imageIndex + 1}`} />
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
                                  <BiLabel zh="已修改" en="Revised" />
                                ) : hasFeedback ? (
                                  <BiLabel zh="回饋已就緒" en="Feedback ready" />
                                ) : (
                                  <BiLabel zh="已錄音" en="Recorded" />
                                )
                              ) : (
                                <BiLabel zh="尚待錄音" en="Needs recording" />
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
                              <BiLabel zh="再錄一次以修改" en="Revise with another recording" />
                            ) : (
                              <BiLabel zh="錄製這個部分" en="Record this part" />
                            )}
                          </button>

                          {latestRecord && (
                            <div className="revision-summary">
                              <strong>
                                <BiLabel
                                  zh={`已收集 ${attemptCount} 次嘗試`}
                                  en={`${attemptCount} ${attemptCount === 1 ? "attempt" : "attempts"} collected`}
                                />
                              </strong>
                            </div>
                          )}

                          {latestRecord ? (
                            <details className="prompt-feedback-details">
                              <summary><BiLabel zh="查看回饋" en="View feedback" /></summary>
                              <RecordCard
                                record={latestRecord}
                                onDeleteRecord={onDeleteRecord}
                                compact
                              />
                            </details>
                          ) : (
                            <div className="picture-empty-result">
                              <BiLabel zh="準備好之後就錄這張圖片。" en="Record this picture when you are ready." />
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
                      zh={`此主題共 ${topicRecords.length} 次嘗試。`}
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

function MyStoryFeedbackHistory({
  submissions,
}: {
  submissions: StorySubmission[];
}) {
  if (submissions.length === 0) return null;

  return (
    <section className="my-story-feedback-history" aria-label="My story feedback history">
      <p className="stories-kicker">
        <BiLabel zh="回顧與進步" en="Review and improve" />
      </p>
      <h2>
        <BiLabel zh="我的故事回顧" en="My Story Feedback" />
      </h2>
      <p className="stories-subtitle">
        <BiText
          zh="再看一次你交過的故事，跟著建議練習，下次會更好。"
          en="Look back at stories you've submitted and follow the suggestions to improve next time."
        />
      </p>
      <div className="my-story-feedback-list">
        {submissions.map((sub) => (
          <details key={sub.id} className="my-story-feedback-item">
            <summary>
              <span className="msfh-title">{sub.storyTitle}</span>
              <span className="msfh-date">
                {new Date(sub.submittedAt).toLocaleDateString()}
              </span>
            </summary>
            <StoryFeedbackCard
              feedback={sub.storyFeedback}
              concatenatedAudioUrl={sub.concatenatedAudioUrl}
            />
          </details>
        ))}
      </div>
    </section>
  );
}

function StudentHelpCard({
  helpRequests,
  onRaiseHand,
}: {
  helpRequests: HelpRequest[];
  onRaiseHand?: (message: string) => void;
}) {
  const [message, setMessage] = useState("我的故事需要協助。 I need help with my story.");
  const studentName = getSessionName("studentSession", "Student");
  const activeRequest = helpRequests.find(
    (request) =>
      request.studentName === studentName && request.status === "open",
  );

  return (
    <section className="student-help-card" aria-label="Ask teacher for help">
      <div>
        <p className="stories-kicker">
          <BiLabel zh="老師協助" en="Teacher support" />
        </p>
        <h2>
          {activeRequest ? (
            <BiLabel zh="已舉手" en="Your hand is raised" />
          ) : (
            <BiLabel zh="舉手提問" en="Raise your hand" />
          )}
        </h2>
        <p>
          {activeRequest ? (
            <BiText
              zh="老師已經看到你的請求。如果問題改變了，可以更新備註。"
              en="Your teacher can see your request. You can update the note if your question changed."
            />
          ) : (
            <BiText
              zh="在繼續完成故事的同時，悄悄發送一個求助請求。"
              en="Send a quiet help request while you keep working on your story."
            />
          )}
        </p>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onRaiseHand?.(message);
        }}
      >
        <input
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          aria-label="Help request message"
          placeholder="老師可以幫你什麼？ What should the teacher help with?"
        />
        <button type="submit" disabled={!onRaiseHand}>
          {activeRequest ? (
            <BiLabel zh="更新請求" en="Update request" />
          ) : (
            <BiLabel zh="舉手" en="Raise hand" />
          )}
        </button>
      </form>
    </section>
  );
}

function TeacherDashboard({
  records,
  onDeleteRecord,
  helpRequests,
  onResolveHelpRequest,
  onRefreshRecords,
  onStorySaved,
}: {
  records: AudioRecord[];
  onDeleteRecord: (id: string) => void;
  helpRequests: HelpRequest[];
  onResolveHelpRequest?: (id: string) => void;
  onRefreshRecords?: () => Promise<void>;
  onStorySaved?: () => void;
}) {
  const [activeView, setActiveView] = useState<TeacherView>("overview");
  const [refreshing, setRefreshing] = useState(false);
  const [submissions, setSubmissions] = useState<StorySubmission[]>([]);

  useEffect(() => {
    if (!canUseDatabase()) return;
    listStorySubmissions().then(setSubmissions).catch(() => {});
  }, []);

  useEffect(() => {
    if (activeView !== "submissions" || !canUseDatabase()) return;
    listStorySubmissions().then(setSubmissions).catch(() => {});
  }, [activeView]);
  const [customStories, setCustomStories] = useState<CustomTeacherStory[]>(
    () => loadCustomStories(),
  );
  const [customDraft, setCustomDraft] = useState(emptyCustomStoryDraft);
  const [editingStoryId, setEditingStoryId] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] =
    useState<CustomStoryValidationErrors>({});
  const [customStoryNotice, setCustomStoryNotice] = useState("");
  const analyzedRecords = records.filter((record) => record.praatMetrics);
  const feedbackReadyRecords = records.filter(
    (record) => record.praatMetrics?.ai_feedback,
  );
  const averageFluency = getAverageMetric(analyzedRecords, "fluency_score");
  const averageToneAccuracy = getAverageMetric(analyzedRecords, "tone_accuracy");
  const openHelpRequests = helpRequests.filter(
    (request) => request.status === "open",
  );
  const preparedFrameCount = customDraft.imageUrls.filter((imageUrl, index) => {
    return imageUrl.trim() || customDraft.prompts[index].trim();
  }).length;

  useEffect(() => {
    if (!canUseDatabase()) {
      return;
    }

    listCustomStories()
      .then((stories) => {
        setCustomStories(stories);
        saveCustomStories(stories);
      })
      .catch((error) => {
        console.error("Failed to load custom stories from database:", error);
      });
  }, []);

  const clearNotice = () => setCustomStoryNotice("");

  const updateDraftField = (
    field: "title" | "learningGoal" | "level" | "lessonNumber" | "grammarPattern" | "grammarExample",
    value: string,
  ) => {
    setCustomDraft((draft) => ({ ...draft, [field]: value }));
    setValidationErrors((errors) => ({ ...errors, [field]: undefined, form: undefined }));
    clearNotice();
  };

  const updateFrameCount = (count: number) => {
    const clamped = Math.min(12, Math.max(1, count));
    setCustomDraft((draft) => ({
      ...draft,
      imageUrls: resizeToCount(draft.imageUrls, clamped, ""),
      prompts: resizeToCount(draft.prompts, clamped, ""),
      vocabulary: resizeToCount(draft.vocabulary, clamped, ""),
      vocabularyPinyin: resizeToCount(draft.vocabularyPinyin, clamped, ""),
      vocabularyGroups: resizeToCount(draft.vocabularyGroups, clamped, null),

      suggestedAnswers: resizeToCount(draft.suggestedAnswers, clamped, ""),
      listenAudioUrls: resizeToCount(draft.listenAudioUrls, clamped, ""),
      listenScripts: resizeToCount(draft.listenScripts, clamped, ""),
    }));
    setValidationErrors((errors) => ({ ...errors, frames: undefined, form: undefined }));
  };

  const updateDraftGroups = (index: number, groups: VocabGroup[] | null) => {
    setCustomDraft((draft) => ({
      ...draft,
      vocabularyGroups: draft.vocabularyGroups.map((g, i) => i === index ? groups : g),
    }));
  };

  const updateDraftFrame = (
    field: "imageUrls" | "prompts" | "vocabulary" | "vocabularyPinyin" | "suggestedAnswers" | "listenAudioUrls" | "listenScripts",
    index: number,
    value: string,
  ) => {
    setCustomDraft((draft) => ({
      ...draft,
      [field]: draft[field].map((item, itemIndex) =>
        itemIndex === index ? value : item,
      ),
    }));
    setValidationErrors((errors) =>
      clearFrameError(errors, index, field),
    );
    clearNotice();
  };

  const handlePasteFrameImage = (index: number, event: React.ClipboardEvent) => {
    const items = event.clipboardData?.items;
    if (!items) {
      return;
    }
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        event.preventDefault();
        handleUploadFrameImage(index, item.getAsFile() ?? undefined);
        return;
      }
    }
  };

  const handleUploadFrameImage = (index: number, file?: File) => {
    if (!file) {
      return;
    }

    const error = getImageUploadError(file);
    if (error) {
      setValidationErrors((errors) => ({ ...errors, form: error }));
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        updateDraftFrame("imageUrls", index, reader.result);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleUploadFrameAudio = (index: number, file?: File) => {
    if (!file) {
      return;
    }

    const error = getAudioUploadError(file);
    if (error) {
      setValidationErrors((errors) => ({ ...errors, form: error }));
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        updateDraftFrame("listenAudioUrls", index, reader.result);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleSaveCustomStory = async () => {
    const errors = validateCustomStoryDraft(customDraft);
    if (hasCustomStoryErrors(errors)) {
      setValidationErrors(errors);
      setCustomStoryNotice("");
      return;
    }

    const existingStory = customStories.find((story) => story.id === editingStoryId);
    const savedStory: CustomTeacherStory = {
      ...createCustomStory(customDraft, editingStoryId),
      published: existingStory?.published ?? false,
    };

    // Persist to the backend first. It writes any uploaded data-URL images to
    // disk and returns the frames with lightweight /uploads/images/... URLs.
    // Caching the raw base64 in localStorage overflows its ~5MB quota, which
    // would otherwise abort the whole save and lose the uploaded image.
    let storyToStore = savedStory;
    if (canUseDatabase()) {
      try {
        const persisted = await saveCustomStoryToDatabase(savedStory);
        if (persisted) {
          storyToStore = {
            ...savedStory,
            ...persisted,
            frames: persisted.frames.map((persistedFrame, i) => ({
              ...savedStory.frames[i],
              ...persistedFrame,
            })),
          } as CustomTeacherStory;
        }
      } catch (error) {
        console.error("Failed to save custom story to database:", error);
        setValidationErrors({
          form: "The story could not be saved to the server. Check that the backend is running and try again.",
        });
        setCustomStoryNotice("");
        return;
      }
    }

    const nextStories = editingStoryId
      ? customStories.map((story) =>
          story.id === editingStoryId ? storyToStore : story,
        )
      : [storyToStore, ...customStories];

    setCustomStories(nextStories);
    try {
      saveCustomStories(nextStories);
    } catch {
      // localStorage is only a cache. If it overflows (e.g. data-URL images
      // while the backend is offline) the story is still saved server-side, so
      // keep going rather than failing the whole save.
      console.warn("Could not cache custom stories in localStorage (quota).");
    }
    setEditingStoryId(null);
    setCustomDraft(emptyCustomStoryDraft);
    setValidationErrors({});
    setCustomStoryNotice(
      editingStoryId ? "Custom story updated." : "Custom story saved.",
    );
    onStorySaved?.();
  };

  const handleDeleteCustomStory = (id: string) => {
    const nextStories = customStories.filter((story) => story.id !== id);
    setCustomStories(nextStories);
    saveCustomStories(nextStories);
    if (canUseDatabase()) {
      deleteCustomStoryFromDatabase(id).catch((error) => {
        console.error("Failed to delete custom story from database:", error);
      });
    }
    if (editingStoryId === id) {
      handleCancelCustomStoryEdit();
    }
  };

  const handleTogglePublishCustomStory = (id: string) => {
    const nextStories = customStories.map((story) =>
      story.id === id ? { ...story, published: !story.published } : story,
    );
    setCustomStories(nextStories);
    saveCustomStories(nextStories);
    const updatedStory = nextStories.find((story) => story.id === id);
    if (updatedStory && canUseDatabase()) {
      saveCustomStoryToDatabase(updatedStory).catch((error) => {
        console.error("Failed to update story publish state in database:", error);
      });
    }
    setCustomStoryNotice(
      updatedStory?.published
        ? "Story published for students."
        : "Story unpublished from student topics.",
    );
  };

  const handleEditCustomStory = (story: CustomTeacherStory) => {
    setEditingStoryId(story.id);
    setCustomDraft(storyToDraft(story));
    setValidationErrors({});
    setCustomStoryNotice("");
  };

  const handleCancelCustomStoryEdit = () => {
    setEditingStoryId(null);
    setCustomDraft(emptyCustomStoryDraft);
    setValidationErrors({});
    setCustomStoryNotice("");
  };
  const teacherViews: Array<{
    id: TeacherView;
    label: string;
    count?: number;
  }> = [
    { id: "overview", label: "Overview" },
    { id: "submissions", label: "Submissions", count: submissions.length },
    { id: "help", label: "Help", count: openHelpRequests.length },
    { id: "materials", label: "Materials", count: customStories.length },
    { id: "progress", label: "Progress" },
  ];

  return (
    <div className="my-stories-page teacher-dashboard-page">
      <section className="teacher-dashboard-hero">
        <div>
          <p className="stories-kicker">Teacher workspace</p>
          <h1>Class Speaking Dashboard</h1>
          <p>
            Review student story recordings, monitor topic coverage, and inspect
            Praat prosody plus AI language feedback in one place.
          </p>
        </div>

        <div className="teacher-dashboard-date">
          <span>Today</span>
          <strong>{new Date().toLocaleDateString()}</strong>
          {onRefreshRecords && (
            <button
              type="button"
              className="teacher-refresh-btn"
              disabled={refreshing}
              onClick={async () => {
                setRefreshing(true);
                await onRefreshRecords();
                setRefreshing(false);
              }}
            >
              {refreshing ? "Refreshing…" : "↺ Refresh recordings"}
            </button>
          )}
        </div>
      </section>

      <nav className="teacher-view-tabs" aria-label="Teacher tools">
        {teacherViews.map((view) => (
          <button
            type="button"
            className={activeView === view.id ? "active" : ""}
            aria-current={activeView === view.id ? "page" : undefined}
            onClick={() => setActiveView(view.id)}
            key={view.id}
          >
            <span>{view.label}</span>
            {view.count !== undefined && <strong>{view.count}</strong>}
          </button>
        ))}
      </nav>

      {activeView === "overview" && (
        <>
          <section className="teacher-stat-grid" aria-label="Class overview">
            <DashboardStat
              label="Submissions"
              value={String(records.length)}
              note="Total saved student attempts"
            />
            <DashboardStat
              label="Feedback ready"
              value={String(feedbackReadyRecords.length)}
              note="Gemini/Praat results available"
            />
            <DashboardStat
              label="Avg. fluency"
              value={averageFluency === null ? "--" : `${averageFluency}/100`}
              note="Based on analyzed recordings"
            />
            <DashboardStat
              label="Tone accuracy"
              value={
                averageToneAccuracy === null ? "--" : `${averageToneAccuracy}%`
              }
              note="Class pronunciation trend"
            />
          </section>

          <section className="teacher-dashboard-grid">
            <TeacherHelpQueue
              helpRequests={helpRequests}
              onResolveHelpRequest={onResolveHelpRequest}
              compact
            />
          </section>
        </>
      )}

      {activeView === "help" && (
        <TeacherHelpQueue
          helpRequests={helpRequests}
          onResolveHelpRequest={onResolveHelpRequest}
        />
      )}

      {activeView === "materials" && (
      <section className="teacher-panel teacher-content-builder">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Custom materials</p>
            <h2>{editingStoryId ? "Edit Story Activity" : "Create Story Activity"}</h2>
          </div>
          <span className="queue-count">{customStories.length}</span>
        </div>

        <div className="teacher-builder-layout">
          <form
            className="custom-story-form"
            onSubmit={(event) => {
              event.preventDefault();
              handleSaveCustomStory();
            }}
          >
            <div className="teacher-form-grid">
              <label>
                Story title
                <input
                  aria-invalid={Boolean(validationErrors.title)}
                  value={customDraft.title}
                  onChange={(event) => updateDraftField("title", event.target.value)}
                  placeholder="e.g. A Rainy Day at Taipei Station"
                />
                {validationErrors.title && (
                  <span className="teacher-form-error">{validationErrors.title}</span>
                )}
              </label>
              <label>
                Level
                <input
                  value={customDraft.level}
                  onChange={(event) => updateDraftField("level", event.target.value)}
                  placeholder="e.g. Intermediate speaking"
                />
              </label>
              <label>
                Lesson number
                <input
                  type="number"
                  min={1}
                  value={customDraft.lessonNumber}
                  onChange={(event) => updateDraftField("lessonNumber", event.target.value)}
                  placeholder="e.g. 3"
                />
              </label>
              <label>
                Narrative type
                <select
                  value={customDraft.narrativeMode}
                  onChange={(event) => {
                    const narrativeMode = event.target.value as NarrativeMode;
                    setCustomDraft((draft) => ({ ...draft, narrativeMode }));
                    updateFrameCount(frameCountForMode(narrativeMode));
                  }}
                >
                  <option value="story">Normal mode (story with scenes)</option>
                  <option value="describe">Descriptive (Describe the Picture)</option>
                  <option value="listen_retell">Listen &amp; Retell</option>
                </select>
              </label>
              <label>
                Number of frames
                <input
                  type="number"
                  min={1}
                  max={12}
                  value={customDraft.imageUrls.length}
                  onChange={(event) => updateFrameCount(Number(event.target.value) || 1)}
                />
              </label>
              <label>
                Grammar pattern (optional)
                <input
                  value={customDraft.grammarPattern}
                  onChange={(event) => updateDraftField("grammarPattern", event.target.value)}
                  placeholder="S + Vaux + V(O)"
                />
              </label>
              <label>
                Example sentence (optional)
                <input
                  value={customDraft.grammarExample}
                  onChange={(event) => updateDraftField("grammarExample", event.target.value)}
                  placeholder="我要喝茶"
                />
              </label>
            </div>

            <label>
              Learning goal
              <textarea
                aria-invalid={Boolean(validationErrors.learningGoal)}
                value={customDraft.learningGoal}
                onChange={(event) =>
                  updateDraftField("learningGoal", event.target.value)
                }
                rows={3}
                placeholder="What should students practice in this story?"
              />
              {validationErrors.learningGoal && (
                <span className="teacher-form-error">
                  {validationErrors.learningGoal}
                </span>
              )}
            </label>


            {customDraft.narrativeMode === "story" && customDraft.imageUrls.length > 1 && (
              <label className="teacher-checkbox-field">
                <input
                  type="checkbox"
                  checked={customDraft.firstFrameIsExample}
                  onChange={(event) =>
                    setCustomDraft((draft) => ({ ...draft, firstFrameIsExample: event.target.checked }))
                  }
                />
                First frame is a teacher model example — students see it before recording (frame 1 becomes a read-only demo)
              </label>
            )}

            {validationErrors.form && (
              <div className="teacher-form-alert" role="alert">
                {validationErrors.form}
              </div>
            )}
            {customStoryNotice && (
              <div className="teacher-form-success" role="status">
                {customStoryNotice}
              </div>
            )}

            <div className="teacher-frame-editor">
              {customDraft.imageUrls.map((imageUrl, index) => {
                const frameError = validationErrors.frames?.[index];
                const isExampleFrame = index === 0 && customDraft.firstFrameIsExample;

                return (
                <div
                  className={`teacher-frame-card ${frameError ? "has-error" : ""}${isExampleFrame ? " is-example-frame" : ""}`}
                  key={index}
                >
                  {isExampleFrame && (
                    <div className="teacher-example-badge">🎯 Teacher Model Example — students watch this before recording</div>
                  )}
                  <div
                    className="teacher-frame-image-preview"
                    tabIndex={0}
                    role="textbox"
                    aria-label={`Paste an image for frame ${index + 1}`}
                    onPaste={(event) => handlePasteFrameImage(index, event)}
                    title="Click here, then paste (Ctrl+V) an image from your clipboard"
                  >
                    {imageUrl ? (
                      <img src={resolveImageUrl(imageUrl)} alt={`Custom story frame ${index + 1}`} />
                    ) : customDraft.narrativeMode === "story" && STORY_FRAME_GUIDES[index] ? (() => {
                      const g = STORY_FRAME_GUIDES[index];
                      return (
                        <svg viewBox="0 0 180 130" xmlns="http://www.w3.org/2000/svg" className="teacher-frame-guide-svg">
                          <rect width="180" height="130" fill={g.accent} />
                          {g.renderIcon()}
                          <rect x="0" y="96" width="180" height="34" fill={g.color} />
                          <text x="90" y="110" textAnchor="middle" fill="white" fontSize="9" fontWeight="700" fontFamily="sans-serif">{g.zh}</text>
                          <text x="90" y="122" textAnchor="middle" fill="white" fontSize="7.5" fontFamily="sans-serif" opacity="0.9">{g.tip}</text>
                          <text x="8" y="14" fill={g.color} fontSize="8" fontWeight="700" fontFamily="sans-serif">{g.en}</text>
                          <text x="172" y="92" textAnchor="end" fill={g.color} fontSize="7" fontFamily="sans-serif" opacity="0.6">📋 paste image here</text>
                        </svg>
                      );
                    })() : (
                      <span>Frame {index + 1}<br /><small className="teacher-frame-paste-hint">📋 Click + paste (Ctrl+V)</small></span>
                    )}
                  </div>
                  <div className="teacher-frame-fields">
                    <label>
                      Image URL or uploaded file
                      <input
                        aria-invalid={Boolean(frameError?.imageUrl)}
                        value={imageUrl}
                        onChange={(event) =>
                          updateDraftFrame("imageUrls", index, event.target.value)
                        }
                        placeholder="Paste an image link for this scene"
                      />
                      {frameError?.imageUrl && (
                        <span className="teacher-form-error">
                          {frameError.imageUrl}
                        </span>
                      )}
                    </label>
                    <label className="teacher-file-upload">
                      Upload from computer
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/gif"
                        onChange={(event) =>
                          handleUploadFrameImage(index, event.target.files?.[0])
                        }
                      />
                    </label>
                    <label>
                      Vocabulary
                      <input
                        value={customDraft.vocabulary[index] ?? ""}
                        onChange={(event) =>
                          updateDraftFrame("vocabulary", index, event.target.value)
                        }
                        placeholder="台北, 下雨, 幫忙"
                      />
                    </label>
                    <label>
                      Vocabulary Pinyin (optional)
                      <input
                        value={customDraft.vocabularyPinyin[index] ?? ""}
                        onChange={(event) =>
                          updateDraftFrame("vocabularyPinyin", index, event.target.value)
                        }
                        placeholder="tái běi, xià yǔ, bāng máng"
                      />
                    </label>
                    {customDraft.narrativeMode !== "listen_retell" && (
                      <label>
                        {isExampleFrame ? "Example script (shown to students as a model — helps them know how to start)" : "Suggested answer (optional)"}
                        <textarea
                          value={customDraft.suggestedAnswers[index] ?? ""}
                          onChange={(event) =>
                            updateDraftFrame("suggestedAnswers", index, event.target.value)
                          }
                          rows={isExampleFrame ? 4 : 2}
                          placeholder={isExampleFrame ? "Write the model story text students will read before recording their own…" : ""}
                        />
                      </label>
                    )}
                    {customDraft.narrativeMode === "listen_retell" && (
                      <>
                        <label>
                          Listening audio for "Listen & Retell" (optional)
                          <input
                            value={customDraft.listenAudioUrls[index] ?? ""}
                            onChange={(event) =>
                              updateDraftFrame("listenAudioUrls", index, event.target.value)
                            }
                            placeholder="https://... or upload below"
                          />
                        </label>
                        <label className="teacher-file-upload">
                          Upload audio from computer
                          <input
                            type="file"
                            accept="audio/mpeg,audio/wav,audio/webm,audio/ogg"
                            onChange={(event) =>
                              handleUploadFrameAudio(index, event.target.files?.[0])
                            }
                          />
                        </label>
                        <label>
                          Listening script (read aloud by text-to-speech if no audio is uploaded — not shown to students)
                          <textarea
                            value={customDraft.listenScripts[index] ?? ""}
                            onChange={(event) =>
                              updateDraftFrame("listenScripts", index, event.target.value)
                            }
                            rows={4}
                            placeholder="The passage students should listen to before retelling the story"
                          />
                        </label>
                      </>
                    )}
                    <VocabGroupEditor
                      vocabulary={customDraft.vocabulary[index]}
                      groups={customDraft.vocabularyGroups[index]}
                      onChange={(groups) => updateDraftGroups(index, groups)}
                    />
                  </div>
                </div>
                );
              })}
            </div>

            <div className="teacher-builder-actions">
              <p>{preparedFrameCount}/{customDraft.imageUrls.length} frames prepared</p>
              <div className="teacher-builder-buttons">
                {editingStoryId && (
                  <button
                    type="button"
                    className="btn-cancel-custom-story"
                    onClick={handleCancelCustomStoryEdit}
                  >
                    Cancel edit
                  </button>
                )}
                <button type="submit" className="btn-save-custom-story">
                  {editingStoryId ? "Update custom story" : "Save custom story"}
                </button>
              </div>
            </div>
          </form>

          <div className="custom-story-library" aria-label="Saved custom stories">
            <h3>Teacher Story Library</h3>
            {customStories.length === 0 ? (
              <div className="teacher-empty-panel">
                <strong>No custom stories yet</strong>
                <p>
                  Add image links and prompts to prepare a reusable classroom
                  speaking activity.
                </p>
              </div>
            ) : (
              <div className="custom-story-list">
                {customStories.map((story) => (
                  <article className="custom-story-item" key={story.id}>
                    <div className="custom-story-item-header">
                      <div>
                        <strong>
                          {story.lessonNumber != null && (
                            <span className="topic-lesson-badge">Lesson {story.lessonNumber}</span>
                          )}
                          {story.title}
                        </strong>
                        <span>
                          {story.level} - {story.published ? "Published" : "Draft"}
                          {" - "}
                          {narrativeModeLabel(story.narrativeMode)}
                        </span>
                      </div>
                      <div className="custom-story-item-actions">
                        <button
                          type="button"
                          className="btn-publish-custom-story"
                          onClick={() => handleTogglePublishCustomStory(story.id)}
                        >
                          {story.published ? "Unpublish" : "Publish"}
                        </button>
                        <button
                          type="button"
                          className="btn-edit-custom-story"
                          onClick={() => handleEditCustomStory(story)}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn-delete-custom-story"
                          onClick={() => handleDeleteCustomStory(story.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    <p>{story.learningGoal}</p>
                    <div className="custom-story-frame-strip">
                      {story.frames.map((frame, index) => (
                        <div className="custom-story-mini-frame" key={index}>
                          {frame.imageUrl ? (
                            <img src={resolveImageUrl(frame.imageUrl)} alt={`${story.title} frame ${index + 1}`} />
                          ) : (
                            <span>{index + 1}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      )}

      {activeView === "progress" && (
      <section className="teacher-dashboard-grid">
        <div className="teacher-panel topic-coverage-panel">
          <div className="teacher-panel-header">
            <div>
              <p className="stories-kicker">Curriculum coverage</p>
              <h2>Topic Progress</h2>
            </div>
          </div>

          <div className="topic-coverage-list">
            {<div className="teacher-empty-panel">
              <strong>Activity Coverage</strong>
              <p>Coverage displays for published teacher materials.</p>
            </div>}
          </div>
        </div>

        <div className="teacher-panel review-queue-panel">
          <div className="teacher-panel-header">
            <div>
              <p className="stories-kicker">Review queue</p>
              <h2>Recent Submissions</h2>
            </div>
            <span className="queue-count">{records.length}</span>
          </div>

          {records.length === 0 ? (
            <div className="teacher-empty-panel">
              <strong>No submissions yet</strong>
              <p>Student recordings will appear here after practice sessions.</p>
            </div>
          ) : (
            <div className="teacher-submission-list">
              {records.slice(0, 5).map((record) => (
                <div className="teacher-submission-row" key={record.id}>
                  <div>
                    <strong>{getTopicLabel(record.topicId)}</strong>
                    <span>
                      Part {(record.imageIndex ?? 0) + 1} · {record.duration}s
                    </span>
                  </div>
                  <div className="submission-score">
                    {record.praatMetrics
                      ? `${Math.round(record.praatMetrics.fluency_score)}/100`
                      : "Pending"}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
      )}

      {activeView === "recordings" && (
      <section className="teacher-panel teacher-recordings-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Detailed review</p>
            <h2>Student Recording Evidence</h2>
          </div>
        </div>

        {records.length === 0 ? (
          <div className="stories-empty-state">
            <div className="stories-empty-icon">Data</div>
            <h2>No Student Recordings Yet</h2>
            <p>Student submissions will appear here after practice sessions.</p>
          </div>
        ) : (
          <div className="stories-grid teacher-recording-grid">
            {records.map((record) => (
              <RecordCard
                key={record.id}
                record={record}
                onDeleteRecord={onDeleteRecord}
              />
            ))}
          </div>
        )}
      </section>
      )}

      {activeView === "submissions" && (
        <section className="teacher-panel teacher-submissions-panel">
          <div className="teacher-panel-header">
            <div>
              <p className="stories-kicker">Student story submissions</p>
              <h2>Submitted Stories</h2>
            </div>
            <span className="queue-count">{submissions.length}</span>
          </div>
          {submissions.length === 0 ? (
            <div className="teacher-empty-panel">
              <strong>No submissions yet</strong>
              <p>Students will appear here after they complete and submit all scenes of a story.</p>
            </div>
          ) : (
            <div className="story-submission-list">
              {submissions.map((sub) => (
                <div key={sub.id} className="story-submission-card">
                  <div className="story-submission-header">
                    <div>
                      <p className="story-submission-student">{sub.studentName}</p>
                      <p className="story-submission-title">{sub.storyTitle}</p>
                    </div>
                    <span className="story-submission-date">
                      {new Date(sub.submittedAt).toLocaleString()}
                    </span>
                  </div>
                  <div className="story-submission-scenes">
                    {sub.scenes.map((scene) => (
                      <div key={scene.sceneIndex} className="story-submission-scene">
                        <div className="sss-header">
                          <span className="sss-scene-num">Scene {scene.sceneIndex + 1}</span>
                          <span className="sss-score" title="Vocab / Tone / Character-by-character prosody">
                            Vocab {scene.vocabScore}% · Tone {scene.toneAccuracy}% · Prosody {scene.pronScore}%
                          </span>
                        </div>
                        {scene.transcription && (
                          <p className="sss-transcription" lang="zh-TW">"{scene.transcription}"</p>
                        )}
                        <div className="sss-vocab-row">
                          {(scene.vocabUsed ?? []).map(w => (
                            <span key={w} className="sss-chip sss-chip-used">✓ {w}</span>
                          ))}
                          {(scene.vocabMissing ?? []).map(w => (
                            <span key={w} className="sss-chip sss-chip-missing">✗ {w}</span>
                          ))}
                        </div>
                        {scene.audioUrl && (
                          <audio controls src={resolveImageUrl(scene.audioUrl)} className="sss-audio" />
                        )}
                      </div>
                    ))}
                  </div>
                  {(sub.concatenatedAudioUrl || sub.storyFeedback) && (
                    <StoryFeedbackCard
                      feedback={sub.storyFeedback}
                      concatenatedAudioUrl={sub.concatenatedAudioUrl}
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}


function TeacherHelpQueue({
  helpRequests,
  onResolveHelpRequest,
  compact = false,
}: {
  helpRequests: HelpRequest[];
  onResolveHelpRequest?: (id: string) => void;
  compact?: boolean;
}) {
  const openRequests = helpRequests.filter(
    (request) => request.status === "open",
  );
  const resolvedRequests = helpRequests
    .filter((request) => request.status === "resolved")
    .slice(0, compact ? 2 : 5);

  return (
    <section className="teacher-panel teacher-help-panel">
      <div className="teacher-panel-header">
        <div>
          <p className="stories-kicker">Live support</p>
          <h2>Student Help Requests</h2>
        </div>
        <span className="queue-count">{openRequests.length}</span>
      </div>

      {openRequests.length === 0 ? (
        <div className="teacher-empty-panel">
          <strong>No raised hands</strong>
          <p>Open help requests will appear here when students ask for support.</p>
        </div>
      ) : (
        <div className="teacher-help-list">
          {openRequests.map((request) => (
            <article className="teacher-help-request" key={request.id}>
              <div>
                <strong>{request.studentName}</strong>
                <span>{formatRequestTime(request.createdAt)}</span>
                <p>{request.message}</p>
              </div>
              <button
                type="button"
                onClick={() => onResolveHelpRequest?.(request.id)}
                disabled={!onResolveHelpRequest}
              >
                Mark helped
              </button>
            </article>
          ))}
        </div>
      )}

      {!compact && resolvedRequests.length > 0 && (
        <div className="teacher-resolved-help">
          <h3>Recently helped</h3>
          {resolvedRequests.map((request) => (
            <div className="teacher-resolved-row" key={request.id}>
              <span>{request.studentName}</span>
              <small>{formatRequestTime(request.resolvedAt || request.createdAt)}</small>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function getAverageMetric(records: AudioRecord[], metric: string): number | null {
  if (records.length === 0) {
    return null;
  }

  const total = records.reduce(
    (sum, record) => sum + (record.praatMetrics?.[metric] || 0),
    0,
  );
  return Math.round(total / records.length);
}

function narrativeModeLabel(mode?: NarrativeMode): string {
  switch (mode) {
    case "describe":
      return "Descriptive";
    case "listen_retell":
      return "Listen & Retell";
    default:
      return "Normal mode";
  }
}

function hasCustomStoryErrors(errors: CustomStoryValidationErrors): boolean {
  return Boolean(
    errors.title ||
      errors.learningGoal ||
      errors.form ||
      Object.keys(errors.frames ?? {}).length > 0,
  );
}

function createCustomStory(
  draft: typeof emptyCustomStoryDraft,
  existingId?: string | null,
): CustomTeacherStory {
  return {
    id: existingId || `custom-story-${Date.now()}`,
    title: draft.title.trim() || "Untitled teacher story",
    learningGoal: draft.learningGoal.trim(),
    level: draft.level.trim() || "Custom activity",
    frames: draft.imageUrls.map((imageUrl, index) => ({
      imageUrl: imageUrl.trim(),
      prompt: draft.prompts[index].trim(),
      vocabulary: draft.vocabulary[index].trim(),
      ...(draft.vocabularyGroups[index] ? { vocabularyGroups: draft.vocabularyGroups[index]! } : {}),
      ...(draft.grammarPattern?.trim() ? { grammarPattern: draft.grammarPattern.trim() } : {}),
      ...(draft.grammarExample?.trim() ? { grammarExample: draft.grammarExample.trim() } : {}),
      ...(draft.vocabularyPinyin[index]?.trim() ? { vocabularyPinyin: draft.vocabularyPinyin[index].trim() } : {}),
      ...(draft.suggestedAnswers[index]?.trim() ? { suggestedAnswer: draft.suggestedAnswers[index].trim() } : {}),
      ...(draft.listenAudioUrls[index]?.trim() ? { listenAudioUrl: draft.listenAudioUrls[index].trim() } : {}),
      ...(draft.listenScripts[index]?.trim() ? { listenScript: draft.listenScripts[index].trim() } : {}),
    })),
    ...(draft.linear ? { linear: true } : {}),
    ...(draft.firstFrameIsExample ? { firstFrameIsExample: true } : {}),
    ...(draft.lessonNumber.trim() ? { lessonNumber: Number(draft.lessonNumber) } : {}),
    narrativeMode: draft.narrativeMode,
  };
}

function storyToDraft(story: CustomTeacherStory): typeof emptyCustomStoryDraft {
  const narrativeMode = story.narrativeMode ?? "story";
  // Preserve the story's actual saved frame count — it may have been
  // changed away from the mode's default via "Number of frames" — and only
  // fall back to the mode default if the story somehow has no frames at all.
  const frameCount = story.frames.length || frameCountForMode(narrativeMode);
  const frames = Array.from({ length: frameCount }, (_, index) => story.frames[index]);

  return {
    title: story.title,
    learningGoal: story.learningGoal,
    level: story.level,
    lessonNumber: story.lessonNumber != null ? String(story.lessonNumber) : "",
    imageUrls: frames.map((frame) => frame?.imageUrl || ""),
    prompts: frames.map((frame, index) =>
      frame?.prompt || emptyCustomStoryDraft.prompts[index],
    ),
    vocabulary: frames.map((frame) => frame?.vocabulary || ""),
    vocabularyGroups: frames.map((frame) => frame?.vocabularyGroups || null),
    grammarPattern: story.frames.find((f) => f?.grammarPattern)?.grammarPattern || "",
    grammarExample: story.frames.find((f) => f?.grammarExample)?.grammarExample || "",
    vocabularyPinyin: frames.map((frame) => frame?.vocabularyPinyin || ""),
    suggestedAnswers: frames.map((frame) => frame?.suggestedAnswer || ""),
    listenAudioUrls: frames.map((frame) => frame?.listenAudioUrl || ""),
    listenScripts: frames.map((frame) => frame?.listenScript || ""),
    linear: story.linear ?? false,
    firstFrameIsExample: story.firstFrameIsExample ?? false,
    narrativeMode: story.narrativeMode ?? "story",
  };
}

function clearFrameError(
  errors: CustomStoryValidationErrors,
  index: number,
  field: "imageUrls" | "prompts" | "vocabulary" | "suggestedAnswers" | "listenAudioUrls" | "listenScripts",
): CustomStoryValidationErrors {
  const frameError = errors.frames?.[index];

  if (!frameError) {
    return { ...errors, form: undefined };
  }

  const nextFrames = { ...errors.frames };
  nextFrames[index] = {
    ...frameError,
    imageUrl: field === "imageUrls" ? undefined : frameError.imageUrl,
    prompt: field === "prompts" ? undefined : frameError.prompt,
  };

  if (!nextFrames[index].imageUrl && !nextFrames[index].prompt) {
    delete nextFrames[index];
  }

  return {
    ...errors,
    form: undefined,
    frames: Object.keys(nextFrames).length > 0 ? nextFrames : undefined,
  };
}

const GRAMMAR_CANVAS_CATEGORIES = [
  { name: "Subject", hanzi: "主語", sub: "Who is doing it (S)",        color: "var(--jade)" },
  { name: "Verb",     hanzi: "動詞", sub: "Aux + main verb (Vaux + V)", color: "var(--seal)" },
  { name: "Object",   hanzi: "受語", sub: "What the verb acts on (O)",  color: "var(--gold-deep)" },
];

const GRAMMAR_GROUP_NAMES = GRAMMAR_CANVAS_CATEGORIES.map(c => c.name);

function VocabGroupEditor({
  vocabulary,
  groups,
  onChange,
}: {
  vocabulary: string;
  groups: VocabGroup[] | null;
  onChange: (groups: VocabGroup[] | null) => void;
}) {
  const words = vocabulary.split(",").map((w) => w.trim()).filter(Boolean);

  if (words.length === 0) return null;

  const active = groups !== null;
  const categoryMeta = GRAMMAR_CANVAS_CATEGORIES;
  const editorTitle = "Grammar Pattern Canvas (Subject · Verb · Object)";

  const handleToggle = (groupNames: string[] | null) => {
    onChange(groupNames ? groupNames.map((name) => ({ name, words: [] })) : null);
  };

  if (!active) {
    return (
      <div className="vocab-group-toggle-row">
        <button type="button" className="vocab-group-toggle-btn" onClick={() => handleToggle(GRAMMAR_GROUP_NAMES)}>
          + Add Grammar categories (Subject · Verb · Object)
        </button>
      </div>
    );
  }

  const currentGroups = groups!;
  const assignedWords = currentGroups.flatMap((g) => g.words);
  const unassigned = words.filter((w) => !assignedWords.includes(w));

  const assignWord = (word: string, groupIndex: number) => {
    const next = currentGroups.map((g, i) => ({
      ...g,
      words: i === groupIndex ? [...g.words, word] : g.words.filter((w) => w !== word),
    }));
    onChange(next);
  };

  const removeWord = (word: string, groupIndex: number) => {
    const next = currentGroups.map((g, i) => ({
      ...g,
      words: i === groupIndex ? g.words.filter((w) => w !== word) : g.words,
    }));
    onChange(next);
  };

  return (
    <div className="vocab-group-editor">
      <div className="vocab-group-editor-header">
        <span>{editorTitle}</span>
        <button type="button" className="vocab-group-remove-btn" onClick={() => handleToggle(null)}>Remove categories</button>
      </div>

      {unassigned.length > 0 && (
        <div className="vocab-group-unassigned">
          <span className="vocab-group-label">Unassigned words — click a word then pick a group:</span>
          <div className="vocab-group-chips">
            {unassigned.map((word) => (
              <span key={word} className="vocab-group-chip unassigned">{word}</span>
            ))}
          </div>
        </div>
      )}

      <div className="vocab-group-grid">
        {currentGroups.map((group, gi) => {
          const cat = categoryMeta[gi];
          return (
          <div key={gi} className="vocab-group-slot">
            <div className="vocab-group-slot-header" style={{ background: cat?.color ?? "var(--clay-muted)" }}>
              <span className="vgs-hanzi">{cat?.hanzi}</span>
              <div className="vgs-title-block">
                <span className="vgs-name">{group.name}</span>
                <span className="vgs-sub">{cat?.sub}</span>
              </div>
            </div>
            <div className="vocab-group-slot-words">
              {group.words.map((word) => (
                <span
                  key={word}
                  className="vocab-group-chip assigned"
                  onClick={() => removeWord(word, gi)}
                  title="Click to remove"
                >
                  {word} ×
                </span>
              ))}
              {unassigned.map((word) => (
                <button
                  key={word}
                  type="button"
                  className="vocab-group-add-word-btn"
                  onClick={() => assignWord(word, gi)}
                >
                  + {word}
                </button>
              ))}
            </div>
          </div>
          );
        })}
      </div>
    </div>
  );
}

function getSessionName(storageKey: string, fallback: string) {
  try {
    const session = JSON.parse(localStorage.getItem(storageKey) || "{}");
    return typeof session.name === "string" && session.name.trim()
      ? session.name.trim()
      : fallback;
  } catch {
    return fallback;
  }
}

function formatRequestTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Just now";
  }

  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getImageUploadError(file: File): string {
  if (!file.type.startsWith("image/")) {
    return "Please upload an image file.";
  }

  if (file.size > 1_500_000) {
    return "This image is too large for browser storage. Use an image under 1.5 MB or paste an image URL.";
  }

  return "";
}

function getAudioUploadError(file: File): string {
  if (!file.type.startsWith("audio/")) {
    return "Please upload an audio file.";
  }

  if (file.size > 5_000_000) {
    return "This audio file is too large. Use a clip under 5 MB.";
  }

  return "";
}

function DashboardStat({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="teacher-stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{note}</p>
    </div>
  );
}

function RecordCard({
  record,
  onDeleteRecord,
  compact = false,
}: {
  record: AudioRecord;
  onDeleteRecord: (id: string) => void;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "record-summary" : "story-card"}>
      <div className="story-header">
        <div className="story-title-group">
          <span className="topic-emoji">{getTopicLabel(record.topicId)}</span>
          <div>
            <div className="story-timestamp">{record.timestamp}</div>
            <div className="story-duration">{record.duration}s</div>
          </div>
        </div>
        <button
          className="btn-delete"
          onClick={() => onDeleteRecord(record.id)}
          title="刪除這則故事 Delete this story"
        >
          <BiLabel zh="刪除" en="Delete" />
        </button>
      </div>

      <div className="story-content">
        {record.audioUrl && (
          <div className="saved-audio-player">
            <strong><BiLabel zh="已儲存的錄音" en="Saved voice recording" /></strong>
            <audio controls src={resolveImageUrl(record.audioUrl)} />
          </div>
        )}

        <div className="transcription-box">
          <strong><BiLabel zh="逐字稿" en="Transcription" /></strong>
          <p>
            {record.transcription || (
              <BiLabel zh="（未偵測到語音）" en="(no speech detected)" />
            )}
          </p>
        </div>

        {record.praatMetrics && (
          <>
            <div className="saved-metrics-summary">
              <div className="metric-item tone">
                <span className="metric-text">
                  <BiLabel zh="聲調：" en="Tone: " />
                  {getToneName(record.praatMetrics.detected_tone)}
                </span>
              </div>
              <div className="metric-item accuracy">
                <span className="metric-text">
                  <BiLabel zh="準確度：" en="Accuracy: " />
                  {Math.round(record.praatMetrics.tone_accuracy)}%
                </span>
              </div>
              <div className="metric-item fluency">
                <span className="metric-text">
                  <BiLabel zh="Praat 流暢度：" en="Praat fluency: " />
                  {Math.round(record.praatMetrics.fluency_score)}/100
                </span>
              </div>
              <div className="metric-item rate">
                <span className="metric-text">
                  <BiLabel zh="語速：" en="Rate: " />
                  {record.praatMetrics.speech_rate.toFixed(1)}/s
                </span>
              </div>
            </div>

            {record.praatMetrics.pitch_contour?.length > 0 && (
              <div className="story-prosody-chart">
                <strong><BiLabel zh="Praat 音調視覺化" en="Praat prosody visualization" /></strong>
                <PitchChart
                  pitchContour={record.praatMetrics.pitch_contour}
                  detectedTone={record.praatMetrics.detected_tone}
                />
              </div>
            )}

            {record.praatMetrics.word_prosody?.length > 0 && (
              <div className="saved-word-prosody">
                <strong><BiLabel zh="逐字音調" en="Word-by-word prosody" /></strong>
                <div className="saved-word-prosody-grid">
                  {record.praatMetrics.word_prosody.map((item: WordProsody) => (
                    <div
                      className="saved-word-prosody-card"
                      key={`${item.token}-${item.index}`}
                    >
                      <span>{item.token}</span>
                      <em>{formatContourShape(item.contour_shape)}</em>
                      <small>
                        {Math.round(item.mean_pitch)} Hz ·{" "}
                        {Math.round(item.pitch_range)} Hz range
                      </small>
                      <p>{item.feedback}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {record.praatMetrics?.ai_feedback && (
          <div className="story-ai-summary">
            <strong>
              <BiLabel
                zh={`AI 教練（${record.praatMetrics.ai_feedback.provider || "Gemini"}）`}
                en={`AI coach (${record.praatMetrics.ai_feedback.provider || "Gemini"})`}
              />
            </strong>
            <p>{record.praatMetrics.ai_feedback.fluency.feedback}</p>
            <p>{record.praatMetrics.ai_feedback.grammar.feedback}</p>
            <p>{record.praatMetrics.ai_feedback.vocabulary.feedback}</p>
          </div>
        )}

        <div className="model-info">
          <span className="model-badge">{record.model}</span>
        </div>
      </div>
    </div>
  );
}

function isPromptRecord(record: AudioRecord, prompt: PromptImage): boolean {
  return (
    record.imageUrl === prompt.imageUrl ||
    (record.topicId === prompt.topicId && record.imageIndex === prompt.imageIndex)
  );
}

function getToneName(tone: number): string {
  const toneNames: Record<number, string> = {
    1: "一聲 High Level (ma1)",
    2: "二聲 Rising (ma2)",
    3: "三聲 Falling-Rising (ma3)",
    4: "四聲 Falling (ma4)",
  };
  return toneNames[tone] || "未知 Unknown";
}

function getTopicLabel(topicId?: string): string {
  const topic = getStudentTopics().find((item) => item.id === topicId);
  return topic?.name || "故事 Story";
}

function formatContourShape(shape: string): string {
  const labels: Record<string, string> = {
    dip: "低降 Dipping",
    falling: "下降 Falling",
    level: "平直 Level",
    rising: "上升 Rising",
    variable: "不規則 Variable",
  };
  return labels[shape] || "不規則 Variable";
}
