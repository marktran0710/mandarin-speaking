import React, { useEffect, useMemo, useRef, useState } from "react";
import Chart from "chart.js/auto";
import PitchChart from "../components/PitchChart";
import {
  canUseDatabase,
  createCustomStory as saveCustomStoryToDatabase,
  deleteCustomStoryFromDatabase,
  HelpRequest,
  listCustomStories,
  listStorySubmissions,
  listVocabQuizAttempts,
  type StorySubmission,
  type VocabQuizAttempt,
} from "../services/database";
import {
  type CustomStoryFrame,
  CustomTeacherStory,
  NarrativeMode,
  type StoryDifficultyLevel,
  VocabGroup,
  loadCustomStories,
  resolveImageUrl,
  saveCustomStories,
} from "../utils/teacherStories";
import { exportStoryFile, readStoryImportFile } from "../utils/storyPortability";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";
import StoryFeedbackCard from "../components/StoryFeedbackCard";
import "./MyStoriesPage.css";
import {
  buildPhraseRows,
  buildVocabRows,
  clearFrameError,
  formatContourShape,
  formatRequestTime,
  frameCountForMode,
  getAudioUploadError,
  getAverageMetric,
  getImageUploadError,
  getPromptImages,
  getSessionName,
  getStudentTopics,
  getToneName,
  getTopicLabel,
  hasCustomStoryErrors,
  isPromptRecord,
  mergePhraseSuggestions,
  mergeVocabSuggestions,
  narrativeModeLabel,
  computeStudentQuizStats,
  computeWordMissStats,
  quizAttemptAccuracy,
  resizeToCount,
  summarizeWordMissTrends,
  wordMissSeverity,
  type PhraseRow,
  type PhraseSuggestion,
  type VocabRow,
  type VocabWordSuggestion,
  type WordMissSeverity,
  type WordMissStats,
} from "../utils/myStoriesUtils";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

// How many phrases to ask the AI for per difficulty tier — a harder tier's
// suggested-answer sentence is longer/more complex, so it naturally yields
// more reusable phrase-level chunks.
const PHRASE_COUNT_BY_LEVEL: Record<StoryDifficultyLevel, number> = {
  easy: 1,
  medium: 2,
  hard: 3,
};

// ── Shared Chart.js look for the teacher analytics tabs ────────────────────
// A plainer, more neutral "data dashboard" register than the rest of the
// app's playful student-facing style: the app's own sans stack instead of
// the display/heading font, restrained gridlines, and a flat (non-bold)
// tick weight. Set once so every chart on Quiz Analytics and Recording
// Analytics inherits it without repeating options per chart.
const CHART_FONT_FAMILY =
  '"Inter", "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif';
Chart.defaults.font.family = CHART_FONT_FAMILY;
Chart.defaults.font.size = 12;
Chart.defaults.color = "#6f697c";
Chart.defaults.borderColor = "#efe6d3";
Chart.defaults.plugins.tooltip.backgroundColor = "#201d29";
Chart.defaults.plugins.tooltip.titleFont = { family: CHART_FONT_FAMILY, weight: "bold" };
Chart.defaults.plugins.tooltip.bodyFont = { family: CHART_FONT_FAMILY };
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 6;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 8;
Chart.defaults.plugins.legend.labels.boxHeight = 8;

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

export interface CustomStoryValidationErrors {
  title?: string;
  learningGoal?: string;
  form?: string;
  frames?: Record<number, { imageUrl?: string; prompt?: string }>;
}

type TeacherView =
  | "overview"
  | "help"
  | "materials"
  | "progress"
  | "recordings"
  | "submissions"
  | "quizAnalytics"
  | "recordingAnalytics";

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

// Temporarily disabled 2026-07-07 at the user's request. The component,
// its data (vocabularyGroups), and this flag stay in place so it's a
// one-line flip to bring back.
const GRAMMAR_CANVAS_ENABLED = false;

/** Fields that vary per difficulty tier — same scene/plot/imageUrl, just
 * progressively more complex text. Each holds one array per tier, all three
 * kept the same length as `imageUrls` (see updateFrameCount). */
type TieredDraftField =
  | "prompts"
  | "vocabulary"
  | "vocabularyPinyin"
  | "vocabularyPos"
  | "vocabularyTranslation"
  | "phrases"
  | "phrasesTranslation"
  | "suggestedAnswers"
  | "listenAudioUrls"
  | "listenScripts";

function blankTiers(count: number): Record<StoryDifficultyLevel, string[]> {
  return {
    easy: new Array(count).fill(""),
    medium: new Array(count).fill(""),
    hard: new Array(count).fill(""),
  };
}

const emptyCustomStoryDraft = {
  title: "Taiwan Community Story",
  learningGoal: "Students describe who, where, what happened, and how people solved the problem.",
  level: "Beginner speaking",
  lessonNumber: "",
  activeLevel: "easy" as StoryDifficultyLevel,
  imageUrls: ["", "", "", "", "", ""],
  prompts: {
    easy: [
      "Introduce the place and the people.",
      "Describe the first event.",
      "Explain the problem or surprise.",
      "Tell the result and feeling.",
      "Revise the story with one clearer detail.",
      "Finish with a lesson or next step.",
    ],
    medium: ["", "", "", "", "", ""],
    hard: ["", "", "", "", "", ""],
  },
  vocabulary: blankTiers(6),
  vocabularyPinyin: blankTiers(6),
  vocabularyPos: blankTiers(6),
  vocabularyTranslation: blankTiers(6),
  vocabularyDistractors: ["", "", "", "", "", ""],
  vocabularyGroups: [null, null, null, null, null, null] as (VocabGroup[] | null)[],
  phrases: blankTiers(6),
  phrasesTranslation: blankTiers(6),
  suggestedAnswers: blankTiers(6),
  listenAudioUrls: blankTiers(6),
  listenScripts: blankTiers(6),
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

function MyStoryFeedbackHistory({
  submissions,
}: {
  submissions: StorySubmission[];
}) {
  if (submissions.length === 0) return null;

  return (
    <section className="my-story-feedback-history" aria-label="My story feedback history">
      <p className="stories-kicker">
        <BiLabel zh="回顧和進步" pinyin="Huígù hé jìnbù" en="Review and improve" />
      </p>
      <h2>
        <BiLabel zh="我的故事回顧" pinyin="Wǒ de gùshì huígù" en="My Story Feedback" />
      </h2>
      <p className="stories-subtitle">
        <BiText
          zh="再看一次你交過的故事，跟著建議練習，下次會更好。"
          pinyin="Zài kàn yí cì nǐ jiāo guò de gùshì, gēnzhe jiànyì liànxí, xiàcì huì gèng hǎo."
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
              scenes={sub.scenes}
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
  const [message, setMessage] = useState("我的故事需要幫忙。 I need help with my story.");
  const studentName = getSessionName("studentSession", "Student");
  const activeRequest = helpRequests.find(
    (request) =>
      request.studentName === studentName && request.status === "open",
  );

  return (
    <section className="student-help-card" aria-label="Ask teacher for help">
      <div>
        <p className="stories-kicker">
          <BiLabel zh="老師幫忙" pinyin="Lǎoshī bāngmáng" en="Teacher support" />
        </p>
        <h2>
          {activeRequest ? (
            <BiLabel zh="已舉手" pinyin="Yǐ jǔshǒu" en="Your hand is raised" />
          ) : (
            <BiLabel zh="舉手問問題" pinyin="Jǔshǒu wèn wèntí" en="Raise your hand" />
          )}
        </h2>
        <p>
          {activeRequest ? (
            <BiText
              zh="老師已經看到你舉手了。如果問題不一樣了，可以再說一次。"
              pinyin="Lǎoshī yǐjīng kàndào nǐ jǔshǒu le. Rúguǒ wèntí bù yíyàng le, kěyǐ zài shuō yí cì."
              en="Your teacher can see your request. You can update the note if your question changed."
            />
          ) : (
            <BiText
              zh="一邊做故事，一邊可以偷偷舉手，老師會看到。"
              pinyin="Yìbiān zuò gùshì, yìbiān kěyǐ tōutōu jǔshǒu, lǎoshī huì kàndào."
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
            <BiLabel zh="再舉手一次" pinyin="Zài jǔshǒu yí cì" en="Update request" />
          ) : (
            <BiLabel zh="舉手" pinyin="Jǔshǒu" en="Raise hand" />
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

  const [quizAttempts, setQuizAttempts] = useState<VocabQuizAttempt[]>([]);
  const [quizAttemptsError, setQuizAttemptsError] = useState("");

  useEffect(() => {
    if (activeView !== "quizAnalytics" || !canUseDatabase()) return;
    setQuizAttemptsError("");
    listVocabQuizAttempts()
      .then(setQuizAttempts)
      .catch(() => setQuizAttemptsError("Could not load vocabulary quiz analytics."));
  }, [activeView]);

  const [customStories, setCustomStories] = useState<CustomTeacherStory[]>(
    () => loadCustomStories(),
  );
  const [customDraft, setCustomDraft] = useState(emptyCustomStoryDraft);
  const [editingStoryId, setEditingStoryId] = useState<string | null>(null);
  const [vocabDraftGeneration, setVocabDraftGeneration] = useState(0);
  const [vocabFillLoadingIndex, setVocabFillLoadingIndex] = useState<number | null>(null);
  const [vocabFillError, setVocabFillError] = useState("");
  const [distractorGenLoadingIndex, setDistractorGenLoadingIndex] = useState<number | null>(null);
  const [distractorGenError, setDistractorGenError] = useState("");
  const [phraseDraftGeneration, setPhraseDraftGeneration] = useState(0);
  const [phraseFillLoadingIndex, setPhraseFillLoadingIndex] = useState<number | null>(null);
  const [phraseFillError, setPhraseFillError] = useState("");
  const [validationErrors, setValidationErrors] =
    useState<CustomStoryValidationErrors>({});
  const [customStoryNotice, setCustomStoryNotice] = useState("");
  const [importError, setImportError] = useState("");
  const [importNotice, setImportNotice] = useState("");
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
    return imageUrl.trim() || customDraft.prompts.easy[index].trim();
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
    field: "title" | "learningGoal" | "level" | "lessonNumber",
    value: string,
  ) => {
    setCustomDraft((draft) => ({ ...draft, [field]: value }));
    setValidationErrors((errors) => ({ ...errors, [field]: undefined, form: undefined }));
    clearNotice();
  };

  const resizeTiers = (
    tiers: Record<StoryDifficultyLevel, string[]>,
    clamped: number,
  ): Record<StoryDifficultyLevel, string[]> => ({
    easy: resizeToCount(tiers.easy, clamped, ""),
    medium: resizeToCount(tiers.medium, clamped, ""),
    hard: resizeToCount(tiers.hard, clamped, ""),
  });

  const updateFrameCount = (count: number) => {
    const clamped = Math.min(12, Math.max(1, count));
    setCustomDraft((draft) => ({
      ...draft,
      imageUrls: resizeToCount(draft.imageUrls, clamped, ""),
      prompts: resizeTiers(draft.prompts, clamped),
      vocabulary: resizeTiers(draft.vocabulary, clamped),
      vocabularyPinyin: resizeTiers(draft.vocabularyPinyin, clamped),
      vocabularyPos: resizeTiers(draft.vocabularyPos, clamped),
      vocabularyTranslation: resizeTiers(draft.vocabularyTranslation, clamped),
      vocabularyDistractors: resizeToCount(draft.vocabularyDistractors, clamped, ""),
      vocabularyGroups: resizeToCount(draft.vocabularyGroups, clamped, null),
      phrases: resizeTiers(draft.phrases, clamped),
      phrasesTranslation: resizeTiers(draft.phrasesTranslation, clamped),
      suggestedAnswers: resizeTiers(draft.suggestedAnswers, clamped),
      listenAudioUrls: resizeTiers(draft.listenAudioUrls, clamped),
      listenScripts: resizeTiers(draft.listenScripts, clamped),
    }));
    setValidationErrors((errors) => ({ ...errors, frames: undefined, form: undefined }));
  };

  const updateDraftGroups = (index: number, groups: VocabGroup[] | null) => {
    setCustomDraft((draft) => ({
      ...draft,
      vocabularyGroups: draft.vocabularyGroups.map((g, i) => i === index ? groups : g),
    }));
  };

  // Text fields are edited one tier at a time (via the level dropdown) —
  // `imageUrls` is the one frame field shared across all three tiers.
  const updateDraftFrame = (
    field: "imageUrls" | TieredDraftField,
    index: number,
    value: string,
  ) => {
    setCustomDraft((draft) => {
      if (field === "imageUrls") {
        return {
          ...draft,
          imageUrls: draft.imageUrls.map((item, i) => (i === index ? value : item)),
        };
      }
      const level = draft.activeLevel;
      const tiers = draft[field];
      return {
        ...draft,
        [field]: {
          ...tiers,
          [level]: tiers[level].map((item, i) => (i === index ? value : item)),
        },
      };
    });
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

  const handleFillVocabFromSentence = async (index: number) => {
    const level = customDraft.activeLevel;
    const sentence = customDraft.suggestedAnswers[level][index]?.trim();
    if (!sentence) return;

    setVocabFillError("");
    setVocabFillLoadingIndex(index);
    try {
      const response = await fetch(`${BACKEND_URL}/api/vocab-from-sentence`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sentence }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Could not extract vocabulary from that sentence.");
      }
      const { words } = (await response.json()) as { words: VocabWordSuggestion[] };

      const existingRows = buildVocabRows(
        customDraft.vocabulary[level][index] ?? "",
        customDraft.vocabularyPinyin[level][index] ?? "",
        customDraft.vocabularyPos[level][index] ?? "",
        customDraft.vocabularyTranslation[level][index] ?? "",
      );
      const mergedRows = mergeVocabSuggestions(existingRows, words);

      setCustomDraft((draft) => ({
        ...draft,
        vocabulary: {
          ...draft.vocabulary,
          [level]: draft.vocabulary[level].map((v, i) => (i === index ? mergedRows.map((r) => r.word).join(", ") : v)),
        },
        vocabularyPinyin: {
          ...draft.vocabularyPinyin,
          [level]: draft.vocabularyPinyin[level].map((v, i) => (i === index ? mergedRows.map((r) => r.pinyin).join(", ") : v)),
        },
        vocabularyPos: {
          ...draft.vocabularyPos,
          [level]: draft.vocabularyPos[level].map((v, i) => (i === index ? mergedRows.map((r) => r.pos).join(", ") : v)),
        },
        vocabularyTranslation: {
          ...draft.vocabularyTranslation,
          [level]: draft.vocabularyTranslation[level].map((v, i) => (i === index ? mergedRows.map((r) => r.translation).join(", ") : v)),
        },
      }));
      setVocabDraftGeneration((generation) => generation + 1);
    } catch (error) {
      setVocabFillError(
        error instanceof Error ? error.message : "Could not extract vocabulary from that sentence.",
      );
    } finally {
      setVocabFillLoadingIndex(null);
    }
  };

  const handleFillPhrasesFromSentence = async (index: number) => {
    const level = customDraft.activeLevel;
    const sentence = customDraft.suggestedAnswers[level][index]?.trim();
    if (!sentence) return;

    setPhraseFillError("");
    setPhraseFillLoadingIndex(index);
    try {
      const response = await fetch(`${BACKEND_URL}/api/phrases-from-sentence`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sentence, count: PHRASE_COUNT_BY_LEVEL[level] }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Could not extract phrases from that sentence.");
      }
      const { phrases } = (await response.json()) as { phrases: PhraseSuggestion[] };

      const existingRows = buildPhraseRows(
        customDraft.phrases[level][index] ?? "",
        customDraft.phrasesTranslation[level][index] ?? "",
      );
      const mergedRows = mergePhraseSuggestions(existingRows, phrases);

      setCustomDraft((draft) => ({
        ...draft,
        phrases: {
          ...draft.phrases,
          [level]: draft.phrases[level].map((v, i) => (i === index ? mergedRows.map((r) => r.phrase).join(", ") : v)),
        },
        phrasesTranslation: {
          ...draft.phrasesTranslation,
          [level]: draft.phrasesTranslation[level].map((v, i) => (i === index ? mergedRows.map((r) => r.translation).join(", ") : v)),
        },
      }));
      setPhraseDraftGeneration((generation) => generation + 1);
    } catch (error) {
      setPhraseFillError(
        error instanceof Error ? error.message : "Could not extract phrases from that sentence.",
      );
    } finally {
      setPhraseFillLoadingIndex(null);
    }
  };

  // Generates AI distractors for a scene's vocab quiz once, when the teacher
  // has words + translations ready — cached in the draft (and persisted with
  // the story on save) rather than regenerated per student attempt.
  const handleGenerateQuizDistractors = async (index: number) => {
    const level = customDraft.activeLevel;
    const rows = buildVocabRows(
      customDraft.vocabulary[level][index] ?? "",
      customDraft.vocabularyPinyin[level][index] ?? "",
      customDraft.vocabularyPos[level][index] ?? "",
      customDraft.vocabularyTranslation[level][index] ?? "",
    ).filter((row) => row.word.trim() && row.translation.trim());
    if (rows.length === 0) return;

    const context = customDraft.suggestedAnswers[level][index]?.trim() || undefined;
    setDistractorGenError("");
    setDistractorGenLoadingIndex(index);
    try {
      const response = await fetch(`${BACKEND_URL}/api/vocab-quiz-distractors`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          words: rows.map((row) => ({ word: row.word, translation: row.translation, context })),
        }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Could not generate quiz distractors for these words.");
      }
      const { results } = (await response.json()) as {
        results: { word: string; distractors: string[] }[];
      };
      const byWord = new Map(results.map((r) => [r.word, r.distractors]));
      const aligned = rows.map((row) => byWord.get(row.word) ?? []);

      setCustomDraft((draft) => ({
        ...draft,
        vocabularyDistractors: draft.vocabularyDistractors.map((v, i) =>
          i === index ? JSON.stringify(aligned) : v,
        ),
      }));
    } catch (error) {
      setDistractorGenError(
        error instanceof Error ? error.message : "Could not generate quiz distractors for these words.",
      );
    } finally {
      setDistractorGenLoadingIndex(null);
    }
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
    setVocabDraftGeneration((generation) => generation + 1);
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

  const handleExportStory = async (story: CustomTeacherStory) => {
    setImportError("");
    try {
      await exportStoryFile(story);
    } catch (error) {
      console.error("Failed to export story:", error);
      setImportError(
        error instanceof Error ? error.message : "Could not export this story.",
      );
    }
  };

  const handleImportStoryFile = async (file: File) => {
    setImportError("");
    setImportNotice("");
    let imported: CustomTeacherStory;
    try {
      imported = await readStoryImportFile(file);
    } catch (error) {
      setImportError(
        error instanceof Error ? error.message : "Could not read that story file.",
      );
      return;
    }

    let storyToStore = imported;
    if (canUseDatabase()) {
      try {
        const persisted = await saveCustomStoryToDatabase(imported);
        if (persisted) {
          storyToStore = {
            ...imported,
            ...persisted,
            frames: persisted.frames.map((persistedFrame, i) => ({
              ...imported.frames[i],
              ...persistedFrame,
            })),
          } as CustomTeacherStory;
        }
      } catch (error) {
        console.error("Failed to save imported story to database:", error);
        setImportError(
          "The story was read but could not be saved to the server. Check that the backend is running and try again.",
        );
        return;
      }
    }

    const nextStories = [storyToStore, ...customStories];
    setCustomStories(nextStories);
    try {
      saveCustomStories(nextStories);
    } catch {
      console.warn("Could not cache imported story in localStorage (quota).");
    }
    setImportNotice(`Imported "${storyToStore.title}" as a new draft.`);
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
    setVocabDraftGeneration((generation) => generation + 1);
    setValidationErrors({});
    setCustomStoryNotice("");
  };

  const handleCancelCustomStoryEdit = () => {
    setEditingStoryId(null);
    setCustomDraft(emptyCustomStoryDraft);
    setVocabDraftGeneration((generation) => generation + 1);
    setValidationErrors({});
    setCustomStoryNotice("");
  };
  // Grouped so the nav reads as a few labeled clusters instead of eight
  // identical pills wrapping onto an uneven second row — "things students
  // sent you" (Review), "what you're teaching" (Content), and "data" (
  // Analytics) are genuinely different jobs, not just a flat list.
  const teacherViewGroups: Array<{
    label: string | null;
    items: Array<{ id: TeacherView; label: string; count?: number }>;
  }> = [
    { label: null, items: [{ id: "overview", label: "Overview" }] },
    {
      label: "Review",
      items: [
        { id: "submissions", label: "Submissions", count: submissions.length },
        { id: "recordings", label: "Recordings", count: records.length },
        { id: "help", label: "Help", count: openHelpRequests.length },
      ],
    },
    {
      label: "Content",
      items: [
        { id: "materials", label: "Materials", count: customStories.length },
        { id: "progress", label: "Progress" },
      ],
    },
    {
      label: "Analytics",
      items: [
        { id: "quizAnalytics", label: "Quiz Analytics", count: quizAttempts.length },
        {
          id: "recordingAnalytics",
          label: "Recording Analytics",
          count: feedbackReadyRecords.length,
        },
      ],
    },
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
        {teacherViewGroups.map((group, gi) => (
          <div className="teacher-view-tab-group" key={group.label ?? `group-${gi}`}>
            {group.label && (
              <span className="teacher-view-tab-group-label">{group.label}</span>
            )}
            <div className="teacher-view-tab-row" role="group" aria-label={group.label ?? "Overview"}>
              {group.items.map((view) => (
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
            </div>
          </div>
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
                Editing difficulty tier
                <select
                  value={customDraft.activeLevel}
                  onChange={(event) =>
                    setCustomDraft((draft) => ({
                      ...draft,
                      activeLevel: event.target.value as StoryDifficultyLevel,
                    }))
                  }
                >
                  <option value="easy">Easy (required — students always see this)</option>
                  <option value="medium">Medium (optional)</option>
                  <option value="hard">Hard (optional)</option>
                </select>
              </label>
            </div>
            {customDraft.activeLevel !== "easy" && (
              <p className="teacher-tier-hint">
                Editing the {customDraft.activeLevel === "medium" ? "Medium" : "Hard"} version of each
                scene's text below — the images and frame count stay shared with Easy. Any scene left
                blank here falls back to its Easy text for students.
              </p>
            )}

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
                const level = customDraft.activeLevel;

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
                    <VocabularyTable
                      key={`${vocabDraftGeneration}-${index}-${level}`}
                      vocabulary={customDraft.vocabulary[level][index] ?? ""}
                      vocabularyPinyin={customDraft.vocabularyPinyin[level][index] ?? ""}
                      vocabularyPos={customDraft.vocabularyPos[level][index] ?? ""}
                      vocabularyTranslation={customDraft.vocabularyTranslation[level][index] ?? ""}
                      onChangeColumn={(field, value) => updateDraftFrame(field, index, value)}
                    />
                    <button
                      type="button"
                      className="btn-vocab-autofill"
                      disabled={
                        !customDraft.vocabulary[level][index]?.trim() ||
                        !customDraft.vocabularyTranslation[level][index]?.trim() ||
                        distractorGenLoadingIndex === index
                      }
                      onClick={() => handleGenerateQuizDistractors(index)}
                    >
                      {distractorGenLoadingIndex === index
                        ? "Generating…"
                        : customDraft.vocabularyDistractors[index]?.trim()
                          ? "🤖 Regenerate quiz distractors"
                          : "🤖 Generate quiz distractors"}
                    </button>
                    {distractorGenError && distractorGenLoadingIndex === null && (
                      <span className="teacher-form-error">{distractorGenError}</span>
                    )}
                    <PhraseTable
                      key={`${phraseDraftGeneration}-phrases-${index}-${level}`}
                      phrases={customDraft.phrases[level][index] ?? ""}
                      phrasesTranslation={customDraft.phrasesTranslation[level][index] ?? ""}
                      onChangeColumn={(field, value) => updateDraftFrame(field, index, value)}
                    />
                    {customDraft.narrativeMode !== "listen_retell" && (
                      <>
                        <label>
                          {isExampleFrame ? "Example script (shown to students as a model — helps them know how to start)" : "Suggested answer (optional)"}
                          <textarea
                            value={customDraft.suggestedAnswers[level][index] ?? ""}
                            onChange={(event) =>
                              updateDraftFrame("suggestedAnswers", index, event.target.value)
                            }
                            rows={isExampleFrame ? 4 : 2}
                            placeholder={isExampleFrame ? "Write the model story text students will read before recording their own…" : ""}
                          />
                        </label>
                        <button
                          type="button"
                          className="btn-vocab-autofill"
                          disabled={
                            !customDraft.suggestedAnswers[level][index]?.trim() ||
                            vocabFillLoadingIndex === index
                          }
                          onClick={() => handleFillVocabFromSentence(index)}
                        >
                          {vocabFillLoadingIndex === index
                            ? "Filling…"
                            : "✨ Fill vocabulary table from this sentence"}
                        </button>
                        {vocabFillError && vocabFillLoadingIndex === null && (
                          <span className="teacher-form-error">{vocabFillError}</span>
                        )}
                        <button
                          type="button"
                          className="btn-vocab-autofill"
                          disabled={
                            !customDraft.suggestedAnswers[level][index]?.trim() ||
                            phraseFillLoadingIndex === index
                          }
                          onClick={() => handleFillPhrasesFromSentence(index)}
                        >
                          {phraseFillLoadingIndex === index
                            ? "Generating…"
                            : `✨ Generate ${PHRASE_COUNT_BY_LEVEL[customDraft.activeLevel]} phrase${PHRASE_COUNT_BY_LEVEL[customDraft.activeLevel] > 1 ? "s" : ""} from this sentence`}
                        </button>
                        {phraseFillError && phraseFillLoadingIndex === null && (
                          <span className="teacher-form-error">{phraseFillError}</span>
                        )}
                      </>
                    )}
                    {customDraft.narrativeMode === "listen_retell" && (
                      <>
                        <label>
                          Listening audio for "Listen & Retell" (optional)
                          <input
                            value={customDraft.listenAudioUrls[level][index] ?? ""}
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
                            value={customDraft.listenScripts[level][index] ?? ""}
                            onChange={(event) =>
                              updateDraftFrame("listenScripts", index, event.target.value)
                            }
                            rows={4}
                            placeholder="The passage students should listen to before retelling the story"
                          />
                        </label>
                      </>
                    )}
                    {GRAMMAR_CANVAS_ENABLED && (
                      <VocabGroupEditor
                        vocabulary={customDraft.vocabulary[level][index]}
                        groups={customDraft.vocabularyGroups[index]}
                        onChange={(groups) => updateDraftGroups(index, groups)}
                      />
                    )}
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
            <div className="custom-story-library-header">
              <h3>Teacher Story Library</h3>
              <label className="btn-import-custom-story">
                Import story
                <input
                  type="file"
                  accept="application/json,.json"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (file) handleImportStoryFile(file);
                  }}
                />
              </label>
            </div>
            {importError && (
              <div className="teacher-form-alert" role="alert">
                {importError}
              </div>
            )}
            {importNotice && (
              <div className="teacher-form-success" role="status">
                {importNotice}
              </div>
            )}
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
                        <details className="custom-story-item-menu">
                          <summary aria-label="More actions">⋯</summary>
                          <div className="custom-story-item-menu-list" role="menu">
                            <button
                              type="button"
                              role="menuitem"
                              className="btn-export-custom-story"
                              onClick={(event) => {
                                handleExportStory(story);
                                event.currentTarget.closest("details")?.removeAttribute("open");
                              }}
                            >
                              Export
                            </button>
                            <button
                              type="button"
                              role="menuitem"
                              className="btn-delete-custom-story"
                              onClick={(event) => {
                                handleDeleteCustomStory(story.id);
                                event.currentTarget.closest("details")?.removeAttribute("open");
                              }}
                            >
                              Delete
                            </button>
                          </div>
                        </details>
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
                      scenes={sub.scenes}
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {activeView === "quizAnalytics" && (
        <QuizAnalyticsPanel attempts={quizAttempts} loadError={quizAttemptsError} />
      )}

      {activeView === "recordingAnalytics" && (
        <RecordingAnalyticsPanel records={records} />
      )}
    </div>
  );
}

const QUIZ_MODE_ORDER: Array<"speed" | "strikes" | "free"> = ["speed", "strikes", "free"];
const QUIZ_MODE_INFO: Record<"speed" | "strikes" | "free", { icon: string; label: string; color: string }> = {
  speed: { icon: "⏱️", label: "Speed", color: "#7c3aed" },
  strikes: { icon: "❌", label: "3 Strikes", color: "#1c9a5b" },
  free: { icon: "🎯", label: "Free Practice", color: "#8a5a12" },
};

function QuizAnalyticsPanel({
  attempts,
  loadError,
}: {
  attempts: VocabQuizAttempt[];
  loadError: string;
}) {
  const [studentFilter, setStudentFilter] = useState("all");
  const [modeFilter, setModeFilter] = useState<"all" | "speed" | "strikes" | "free">("all");

  if (loadError) {
    return (
      <section className="teacher-panel teacher-quiz-analytics-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Vocabulary quiz analytics</p>
            <h2>Quiz Analytics</h2>
          </div>
        </div>
        <p className="teacher-form-error">{loadError}</p>
      </section>
    );
  }

  if (attempts.length === 0) {
    return (
      <section className="teacher-panel teacher-quiz-analytics-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Vocabulary quiz analytics</p>
            <h2>Quiz Analytics</h2>
          </div>
        </div>
        <div className="teacher-empty-panel">
          <strong>No quiz attempts yet</strong>
          <p>Time spent, accuracy, and repeated mistakes will appear here after students complete a vocabulary quiz.</p>
        </div>
      </section>
    );
  }

  const students = Array.from(new Set(attempts.map((a) => a.studentName))).sort();
  const studentFiltered = studentFilter === "all"
    ? attempts
    : attempts.filter((a) => a.studentName === studentFilter);
  const filtered = modeFilter === "all"
    ? studentFiltered
    : studentFiltered.filter((a) => a.mode === modeFilter);

  const totalQuestions = filtered.reduce((sum, a) => sum + a.totalQuestions, 0);
  const correctCount = filtered.reduce((sum, a) => sum + a.correctCount, 0);
  const totalTimeMs = filtered.reduce((sum, a) => sum + a.totalTimeMs, 0);
  const overallAccuracy = totalQuestions > 0 ? Math.round((correctCount / totalQuestions) * 100) : 0;
  const avgTimePerQuestion = totalQuestions > 0 ? Math.round(totalTimeMs / totalQuestions / 1000) : 0;

  const studentStats = computeStudentQuizStats(filtered);
  const allWordStats = computeWordMissStats(filtered);
  const wordStats = allWordStats.slice(0, 10);
  const wordMissInsight = summarizeWordMissTrends(allWordStats, wordStats.length);

  // Mode comparison always reads the student-filtered set (not mode-filtered)
  // so all three mode bars stay visible for comparison no matter which mode
  // is picked in the filter above.
  const modeChartData = QUIZ_MODE_ORDER.map((mode) => {
    const modeAttempts = studentFiltered.filter((a) => a.mode === mode);
    const avg = modeAttempts.length === 0
      ? 0
      : Math.round(modeAttempts.reduce((sum, a) => sum + quizAttemptAccuracy(a), 0) / modeAttempts.length);
    return { mode, avg, count: modeAttempts.length };
  });

  // One point per attempt when a single student is selected (a short-term
  // trend is visible); a single class-average-per-day line for "All
  // students" — never one line per student, which would need an unbounded
  // categorical palette for a whole classroom.
  const sortedByDate = [...filtered].sort(
    (a, b) => new Date(a.completedAt).getTime() - new Date(b.completedAt).getTime(),
  );
  const timeSeries = studentFilter !== "all"
    ? sortedByDate.map((a) => ({ label: new Date(a.completedAt).toLocaleDateString(), value: quizAttemptAccuracy(a) }))
    : (() => {
        const byDay = new Map<string, number[]>();
        sortedByDate.forEach((a) => {
          const day = new Date(a.completedAt).toLocaleDateString();
          byDay.set(day, [...(byDay.get(day) || []), quizAttemptAccuracy(a)]);
        });
        return Array.from(byDay.entries()).map(([day, values]) => ({
          label: day,
          value: Math.round(values.reduce((s, v) => s + v, 0) / values.length),
        }));
      })();

  return (
    <>
      <section className="teacher-panel quiz-analytics-filters-panel">
        <div className="quiz-analytics-filters">
          <label>
            Student
            <select value={studentFilter} onChange={(e) => setStudentFilter(e.target.value)}>
              <option value="all">All students</option>
              {students.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </label>
          <label>
            Quiz mode
            <select value={modeFilter} onChange={(e) => setModeFilter(e.target.value as typeof modeFilter)}>
              <option value="all">All modes</option>
              {QUIZ_MODE_ORDER.map((mode) => (
                <option key={mode} value={mode}>{QUIZ_MODE_INFO[mode].icon} {QUIZ_MODE_INFO[mode].label}</option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {filtered.length === 0 ? (
        <div className="teacher-empty-panel">
          <strong>No attempts match this filter</strong>
          <p>Try a different student or quiz mode.</p>
        </div>
      ) : (
        <>
          <section className="teacher-stat-grid" aria-label="Quiz analytics overview">
            <DashboardStat
              label="Quiz attempts"
              value={String(filtered.length)}
              note="Completed vocabulary quiz sessions"
            />
            <DashboardStat
              label="Overall accuracy"
              value={`${overallAccuracy}%`}
              note={`${correctCount}/${totalQuestions} questions correct`}
            />
            <DashboardStat
              label="Avg. time / question"
              value={`${avgTimePerQuestion}s`}
              note="Across all recorded attempts"
            />
          </section>

          <section className="teacher-panel teacher-quiz-analytics-panel">
            <div className="teacher-panel-header">
              <div>
                <p className="stories-kicker">Visualized</p>
                <h2>Charts</h2>
              </div>
            </div>
            <div className="quiz-analytics-charts">
              <div className="quiz-analytics-chart-card">
                <h3>Accuracy by quiz mode</h3>
                <ModeAccuracyChart data={modeChartData} />
              </div>
              <div className="quiz-analytics-chart-card">
                <h3>
                  {studentFilter === "all"
                    ? "Class average accuracy over time"
                    : `${studentFilter}'s accuracy over time`}
                </h3>
                <AccuracyTimeChart points={timeSeries} />
              </div>
              <div className="quiz-analytics-chart-card quiz-analytics-chart-wide">
                <h3>Most-missed vocabulary words</h3>
                {wordStats.length === 0 ? (
                  <p className="quiz-analytics-empty-note">No missed words in this filter — nice work!</p>
                ) : (
                  <>
                    <p className="quiz-analytics-insight">{wordMissInsight}</p>
                    <WordMissChart data={wordStats} />
                  </>
                )}
              </div>
            </div>
          </section>

          <section className="teacher-panel teacher-quiz-analytics-panel">
            <div className="teacher-panel-header">
              <div>
                <p className="stories-kicker">Per student</p>
                <h2>Student Quiz Performance</h2>
              </div>
              <span className="queue-count">{studentStats.length}</span>
            </div>

            <div className="quiz-analytics-student-table">
              <div className="quiz-analytics-student-row quiz-analytics-student-head">
                <span>Student</span>
                <span>Attempts</span>
                <span>Accuracy</span>
                <span>Avg. time/question</span>
                <span>Most repeated mistake</span>
              </div>
              {studentStats.map((student) => (
                <div className="quiz-analytics-student-row" key={student.studentName}>
                  <span>{student.studentName}</span>
                  <span>{student.attempts}</span>
                  <span>{student.accuracyPct}%</span>
                  <span>{(student.avgTimePerQuestionMs / 1000).toFixed(1)}s</span>
                  <span>
                    {student.topMissedWord
                      ? `${student.topMissedWord.word} (missed ${student.topMissedWord.missCount}×)`
                      : "—"}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section className="teacher-panel teacher-quiz-analytics-panel">
            <div className="teacher-panel-header">
              <div>
                <p className="stories-kicker">Class-wide</p>
                <h2>Words Needing the Most Practice</h2>
              </div>
              <span className="queue-count">{wordStats.length}</span>
            </div>

            {wordStats.length === 0 ? (
              <div className="teacher-empty-panel">
                <strong>No repeated mistakes yet</strong>
                <p>Words students get wrong more than once will show up here.</p>
              </div>
            ) : (
              <div className="quiz-analytics-word-list">
                {wordStats.map((word) => {
                  const severity = wordMissSeverity(word.missRatePct);
                  return (
                    <div className="quiz-analytics-word-row" key={word.word}>
                      <strong>{word.word}</strong>
                      <span className={`word-severity-badge word-severity-${severity}`}>
                        {WORD_SEVERITY_LABEL[severity]}
                      </span>
                      <span>
                        Missed {word.timesMissed}/{word.timesAsked} times ({word.missRatePct}%)
                      </span>
                      <span>Avg. {(word.avgTimeMs / 1000).toFixed(1)}s/question</span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}

/** Chart.js canvas that (re)builds its chart whenever `build` changes,
 * tearing down the previous instance first — same lifecycle as
 * components/PitchChart.tsx. */
function QuizChartCanvas({ build, height = 220 }: { build: (ctx: CanvasRenderingContext2D) => Chart; height?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    chartRef.current?.destroy();
    chartRef.current = build(ctx);
    return () => chartRef.current?.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [build]);

  return (
    <div className="quiz-analytics-chart-canvas" style={{ height }}>
      <canvas ref={canvasRef} />
    </div>
  );
}

function ModeAccuracyChart({ data }: { data: Array<{ mode: "speed" | "strikes" | "free"; avg: number; count: number }> }) {
  const build = useMemo(
    () => (ctx: CanvasRenderingContext2D) =>
      new Chart(ctx, {
        type: "bar",
        data: {
          labels: data.map((m) => `${QUIZ_MODE_INFO[m.mode].icon} ${QUIZ_MODE_INFO[m.mode].label}`),
          datasets: [{
            label: "Average accuracy",
            data: data.map((m) => m.avg),
            backgroundColor: data.map((m) => QUIZ_MODE_INFO[m.mode].color),
            borderRadius: 4,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (item) => {
                  const m = data[item.dataIndex];
                  return `${item.parsed.y}% avg accuracy (${m.count} attempt${m.count === 1 ? "" : "s"})`;
                },
              },
            },
          },
          scales: {
            y: {
              beginAtZero: true,
              max: 100,
              title: { display: true, text: "Accuracy" },
              ticks: { callback: (v) => `${v}%` },
            },
            x: { grid: { display: false } },
          },
        },
      }),
    [data],
  );
  return <QuizChartCanvas build={build} />;
}

function AccuracyTimeChart({ points }: { points: Array<{ label: string; value: number }> }) {
  const build = useMemo(
    () => (ctx: CanvasRenderingContext2D) =>
      new Chart(ctx, {
        type: "line",
        data: {
          labels: points.map((p) => p.label),
          datasets: [{
            label: "Accuracy",
            data: points.map((p) => p.value),
            borderColor: "#7c3aed",
            backgroundColor: "rgba(124, 58, 237, 0.14)",
            borderWidth: 2,
            tension: 0.3,
            fill: true,
            pointRadius: 4,
            pointHoverRadius: 6,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: (item) => `${item.parsed.y}% accuracy` } },
          },
          scales: {
            y: {
              beginAtZero: true,
              max: 100,
              title: { display: true, text: "Accuracy" },
              ticks: { callback: (v) => `${v}%` },
            },
            x: { grid: { display: false } },
          },
        },
      }),
    [points],
  );
  return <QuizChartCanvas build={build} />;
}

function WordMissChart({ data }: { data: WordMissStats[] }) {
  const build = useMemo(
    () => (ctx: CanvasRenderingContext2D) => {
      // Draws "N× (P%)" past the end of each bar. Chart.js has no built-in
      // data-label support without a paid/extra plugin, so this is a small
      // inline plugin closing over `data` rather than a new dependency.
      const barEndLabels = {
        id: "wordMissBarLabels",
        afterDatasetsDraw(chart: Chart) {
          const meta = chart.getDatasetMeta(0);
          chart.ctx.save();
          chart.ctx.font = `600 12px ${CHART_FONT_FAMILY}`;
          chart.ctx.fillStyle = "#4a4556";
          chart.ctx.textBaseline = "middle";
          chart.ctx.textAlign = "left";
          meta.data.forEach((bar, i) => {
            const w = data[i];
            const { x, y } = bar.getProps(["x", "y"], true);
            chart.ctx.fillText(`${w.timesMissed}× (${w.missRatePct}%)`, x + 6, y);
          });
          chart.ctx.restore();
        },
      };

      return new Chart(ctx, {
        type: "bar",
        data: {
          labels: data.map((w) => w.word),
          datasets: [{
            label: "Times missed",
            data: data.map((w) => w.timesMissed),
            backgroundColor: data.map((w) =>
              wordMissSeverity(w.missRatePct) === "critical"
                ? "#c81e3a"
                : wordMissSeverity(w.missRatePct) === "watch"
                  ? "#ffa726"
                  : "#8a5a12",
            ),
            borderRadius: 4,
          }],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          layout: { padding: { right: 64 } },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (item) => {
                  const w = data[item.dataIndex];
                  return [
                    `Missed ${w.timesMissed} of ${w.timesAsked} time${w.timesAsked === 1 ? "" : "s"} (${w.missRatePct}%)`,
                    `Avg. ${(w.avgTimeMs / 1000).toFixed(1)}s to answer`,
                  ];
                },
              },
            },
          },
          scales: {
            x: {
              beginAtZero: true,
              ticks: { precision: 0 },
              title: { display: true, text: "Times missed (most to least common)" },
            },
            y: { grid: { display: false } },
          },
        },
        plugins: [barEndLabels],
      });
    },
    [data],
  );
  return <QuizChartCanvas build={build} height={Math.max(180, data.length * 32)} />;
}

const AI_FEEDBACK_CATEGORIES = ["fluency", "grammar", "vocabulary"] as const;
const AI_FEEDBACK_CATEGORY_INFO: Record<(typeof AI_FEEDBACK_CATEGORIES)[number], { label: string; color: string }> = {
  fluency: { label: "Fluency", color: "#7c3aed" },
  grammar: { label: "Grammar", color: "#1c9a5b" },
  vocabulary: { label: "Vocabulary", color: "#8a5a12" },
};

/** Class-wide analytics over story-recording feedback (Praat + AI). Unlike
 * Quiz Analytics, recordings have no student-name field today, so this is
 * aggregate-only — a topic filter, not a student one. */
function RecordingAnalyticsPanel({ records }: { records: AudioRecord[] }) {
  const [topicFilter, setTopicFilter] = useState("all");

  if (records.length === 0) {
    return (
      <section className="teacher-panel teacher-recording-analytics-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Recording feedback analytics</p>
            <h2>Recording Analytics</h2>
          </div>
        </div>
        <div className="teacher-empty-panel">
          <strong>No recordings yet</strong>
          <p>Fluency, tone accuracy, and AI feedback trends will appear here once students submit recordings.</p>
        </div>
      </section>
    );
  }

  const topicIds = Array.from(
    new Set(records.map((r) => r.topicId).filter((id): id is string => Boolean(id))),
  );

  const filtered = topicFilter === "all" ? records : records.filter((r) => r.topicId === topicFilter);
  const withMetrics = filtered.filter((r) => r.praatMetrics);
  const withAiFeedback = filtered.filter((r) => r.praatMetrics?.ai_feedback);

  const avgFluency = withMetrics.length > 0
    ? Math.round(withMetrics.reduce((sum, r) => sum + (r.praatMetrics.fluency_score || 0), 0) / withMetrics.length)
    : null;
  const avgTone = withMetrics.length > 0
    ? Math.round(withMetrics.reduce((sum, r) => sum + (r.praatMetrics.tone_accuracy || 0), 0) / withMetrics.length)
    : null;

  const categoryData = AI_FEEDBACK_CATEGORIES.map((category) => {
    const scores = withAiFeedback
      .map((r) => r.praatMetrics.ai_feedback[category]?.score)
      .filter((s): s is number => typeof s === "number");
    return {
      category,
      avg: scores.length > 0 ? Math.round(scores.reduce((s, v) => s + v, 0) / scores.length) : 0,
      count: scores.length,
    };
  });
  const allAiScores = categoryData.flatMap((c) => (c.count > 0 ? [c.avg] : []));
  const avgAiScore = allAiScores.length > 0
    ? Math.round(allAiScores.reduce((s, v) => s + v, 0) / allAiScores.length)
    : null;

  const parsedByTime = withMetrics
    .map((r) => ({
      time: new Date(r.timestamp).getTime(),
      fluency: r.praatMetrics.fluency_score,
      tone: r.praatMetrics.tone_accuracy,
    }))
    .filter((r) => !Number.isNaN(r.time))
    .sort((a, b) => a.time - b.time);
  const byDay = new Map<string, { fluency: number[]; tone: number[] }>();
  parsedByTime.forEach((r) => {
    const day = new Date(r.time).toLocaleDateString();
    const entry = byDay.get(day) || { fluency: [], tone: [] };
    entry.fluency.push(r.fluency || 0);
    entry.tone.push(r.tone || 0);
    byDay.set(day, entry);
  });
  const timeSeries = Array.from(byDay.entries()).map(([day, v]) => ({
    label: day,
    fluency: Math.round(v.fluency.reduce((s, x) => s + x, 0) / v.fluency.length),
    tone: Math.round(v.tone.reduce((s, x) => s + x, 0) / v.tone.length),
  }));

  const perTopic = topicIds
    .map((id) => ({ topic: getTopicLabel(id), count: records.filter((r) => r.topicId === id).length }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10);

  return (
    <>
      <section className="teacher-panel quiz-analytics-filters-panel">
        <div className="quiz-analytics-filters">
          <label>
            Topic
            <select value={topicFilter} onChange={(e) => setTopicFilter(e.target.value)}>
              <option value="all">All topics</option>
              {topicIds.map((id) => (
                <option key={id} value={id}>{getTopicLabel(id)}</option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {filtered.length === 0 ? (
        <div className="teacher-empty-panel">
          <strong>No recordings match this filter</strong>
          <p>Try a different topic.</p>
        </div>
      ) : (
        <>
          <section className="teacher-stat-grid" aria-label="Recording analytics overview">
            <DashboardStat
              label="Recordings"
              value={String(filtered.length)}
              note="Total submitted recordings"
            />
            <DashboardStat
              label="Avg. fluency"
              value={avgFluency === null ? "--" : `${avgFluency}/100`}
              note="Praat fluency score"
            />
            <DashboardStat
              label="Avg. tone accuracy"
              value={avgTone === null ? "--" : `${avgTone}%`}
              note="Praat tone accuracy"
            />
            <DashboardStat
              label="Avg. AI feedback score"
              value={avgAiScore === null ? "--" : `${avgAiScore}/100`}
              note="Fluency + grammar + vocabulary"
            />
          </section>

          <section className="teacher-panel teacher-recording-analytics-panel">
            <div className="teacher-panel-header">
              <div>
                <p className="stories-kicker">Visualized</p>
                <h2>Charts</h2>
              </div>
            </div>
            <div className="quiz-analytics-charts">
              <div className="quiz-analytics-chart-card quiz-analytics-chart-wide">
                <h3>Fluency &amp; tone accuracy over time</h3>
                {timeSeries.length === 0 ? (
                  <p className="quiz-analytics-empty-note">No analyzed recordings in this filter yet.</p>
                ) : (
                  <FluencyToneTimeChart points={timeSeries} />
                )}
              </div>
              <div className="quiz-analytics-chart-card">
                <h3>AI feedback score by category</h3>
                {allAiScores.length === 0 ? (
                  <p className="quiz-analytics-empty-note">No AI feedback in this filter yet.</p>
                ) : (
                  <AiFeedbackCategoryChart data={categoryData} />
                )}
              </div>
              <div className="quiz-analytics-chart-card">
                <h3>Recordings per topic</h3>
                {perTopic.length === 0 ? (
                  <p className="quiz-analytics-empty-note">No topic data yet.</p>
                ) : (
                  <RecordingsPerTopicChart data={perTopic} />
                )}
              </div>
            </div>
          </section>
        </>
      )}
    </>
  );
}

function FluencyToneTimeChart({ points }: { points: Array<{ label: string; fluency: number; tone: number }> }) {
  const build = useMemo(
    () => (ctx: CanvasRenderingContext2D) =>
      new Chart(ctx, {
        type: "line",
        data: {
          labels: points.map((p) => p.label),
          datasets: [
            {
              label: "Fluency",
              data: points.map((p) => p.fluency),
              borderColor: "#7c3aed",
              backgroundColor: "rgba(124, 58, 237, 0.1)",
              borderWidth: 2,
              tension: 0.3,
              pointRadius: 4,
              pointHoverRadius: 6,
            },
            {
              label: "Tone accuracy",
              data: points.map((p) => p.tone),
              borderColor: "#1c9a5b",
              backgroundColor: "rgba(28, 154, 91, 0.1)",
              borderWidth: 2,
              tension: 0.3,
              pointRadius: 4,
              pointHoverRadius: 6,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: true, position: "top", align: "end" } },
          scales: {
            y: {
              beginAtZero: true,
              max: 100,
              title: { display: true, text: "Score" },
              ticks: { callback: (v) => `${v}` },
            },
            x: { grid: { display: false } },
          },
        },
      }),
    [points],
  );
  return <QuizChartCanvas build={build} />;
}

function AiFeedbackCategoryChart({ data }: { data: Array<{ category: (typeof AI_FEEDBACK_CATEGORIES)[number]; avg: number; count: number }> }) {
  const build = useMemo(
    () => (ctx: CanvasRenderingContext2D) =>
      new Chart(ctx, {
        type: "bar",
        data: {
          labels: data.map((c) => AI_FEEDBACK_CATEGORY_INFO[c.category].label),
          datasets: [{
            label: "Average score",
            data: data.map((c) => c.avg),
            backgroundColor: data.map((c) => AI_FEEDBACK_CATEGORY_INFO[c.category].color),
            borderRadius: 4,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (item) => {
                  const c = data[item.dataIndex];
                  return `${item.parsed.y}/100 avg (${c.count} score${c.count === 1 ? "" : "s"})`;
                },
              },
            },
          },
          scales: {
            y: { beginAtZero: true, max: 100, title: { display: true, text: "Score" } },
            x: { grid: { display: false } },
          },
        },
      }),
    [data],
  );
  return <QuizChartCanvas build={build} />;
}

function RecordingsPerTopicChart({ data }: { data: Array<{ topic: string; count: number }> }) {
  const build = useMemo(
    () => (ctx: CanvasRenderingContext2D) =>
      new Chart(ctx, {
        type: "bar",
        data: {
          labels: data.map((t) => t.topic),
          datasets: [{
            label: "Recordings",
            data: data.map((t) => t.count),
            backgroundColor: "#0b5fa8",
            borderRadius: 4,
          }],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { beginAtZero: true, title: { display: true, text: "Recordings" }, ticks: { precision: 0 } },
            y: { grid: { display: false } },
          },
        },
      }),
    [data],
  );
  return <QuizChartCanvas build={build} height={Math.max(160, data.length * 32)} />;
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

const WORD_SEVERITY_LABEL: Record<WordMissSeverity, string> = {
  critical: "Critical",
  watch: "Watch",
  ok: "OK",
};

/** Maps a TieredDraftField name to its backend base/Medium/Hard field names
 * (e.g. "suggestedAnswers" -> "suggestedAnswer"/"suggestedAnswerMedium"/
 * "suggestedAnswerHard") — the draft's plural array names don't always match
 * the singular per-frame field names on CustomStoryFrame. */
const TIER_BACKEND_FIELD: Record<
  TieredDraftField,
  { easy: keyof CustomStoryFrame; medium: keyof CustomStoryFrame; hard: keyof CustomStoryFrame }
> = {
  prompts: { easy: "prompt", medium: "promptMedium", hard: "promptHard" },
  vocabulary: { easy: "vocabulary", medium: "vocabularyMedium", hard: "vocabularyHard" },
  vocabularyPinyin: {
    easy: "vocabularyPinyin",
    medium: "vocabularyPinyinMedium",
    hard: "vocabularyPinyinHard",
  },
  vocabularyPos: { easy: "vocabularyPos", medium: "vocabularyPosMedium", hard: "vocabularyPosHard" },
  vocabularyTranslation: {
    easy: "vocabularyTranslation",
    medium: "vocabularyTranslationMedium",
    hard: "vocabularyTranslationHard",
  },
  phrases: { easy: "phrases", medium: "phrasesMedium", hard: "phrasesHard" },
  phrasesTranslation: {
    easy: "phrasesTranslation",
    medium: "phrasesTranslationMedium",
    hard: "phrasesTranslationHard",
  },
  suggestedAnswers: {
    easy: "suggestedAnswer",
    medium: "suggestedAnswerMedium",
    hard: "suggestedAnswerHard",
  },
  listenAudioUrls: {
    easy: "listenAudioUrl",
    medium: "listenAudioUrlMedium",
    hard: "listenAudioUrlHard",
  },
  listenScripts: { easy: "listenScript", medium: "listenScriptMedium", hard: "listenScriptHard" },
};

const TIERED_DRAFT_FIELDS: TieredDraftField[] = [
  "prompts",
  "vocabulary",
  "vocabularyPinyin",
  "vocabularyPos",
  "vocabularyTranslation",
  "phrases",
  "phrasesTranslation",
  "suggestedAnswers",
  "listenAudioUrls",
  "listenScripts",
];

function createCustomStory(
  draft: typeof emptyCustomStoryDraft,
  existingId?: string | null,
): CustomTeacherStory {
  return {
    id: existingId || `custom-story-${Date.now()}`,
    title: draft.title.trim() || "Untitled teacher story",
    learningGoal: draft.learningGoal.trim(),
    level: draft.level.trim() || "Custom activity",
    frames: draft.imageUrls.map((imageUrl, index) => {
      const frame: CustomStoryFrame = {
        imageUrl: imageUrl.trim(),
        prompt: draft.prompts.easy[index].trim(),
        vocabulary: draft.vocabulary.easy[index].trim(),
      };
      if (draft.vocabularyGroups[index]) {
        frame.vocabularyGroups = draft.vocabularyGroups[index]!;
      }
      if (draft.vocabularyDistractors[index]?.trim()) {
        frame.vocabularyDistractors = draft.vocabularyDistractors[index].trim();
      }
      TIERED_DRAFT_FIELDS.forEach((field) => {
        (["medium", "hard"] as const).forEach((level) => {
          const value = draft[field][level][index]?.trim();
          if (value) {
            (frame as any)[TIER_BACKEND_FIELD[field][level]] = value;
          }
        });
      });
      // Easy's optional fields (beyond prompt/vocabulary, always present)
      if (draft.phrases.easy[index]?.trim()) frame.phrases = draft.phrases.easy[index].trim();
      if (draft.phrasesTranslation.easy[index]?.trim())
        frame.phrasesTranslation = draft.phrasesTranslation.easy[index].trim();
      if (draft.vocabularyPinyin.easy[index]?.trim())
        frame.vocabularyPinyin = draft.vocabularyPinyin.easy[index].trim();
      if (draft.vocabularyPos.easy[index]?.trim())
        frame.vocabularyPos = draft.vocabularyPos.easy[index].trim();
      if (draft.vocabularyTranslation.easy[index]?.trim())
        frame.vocabularyTranslation = draft.vocabularyTranslation.easy[index].trim();
      if (draft.suggestedAnswers.easy[index]?.trim())
        frame.suggestedAnswer = draft.suggestedAnswers.easy[index].trim();
      if (draft.listenAudioUrls.easy[index]?.trim())
        frame.listenAudioUrl = draft.listenAudioUrls.easy[index].trim();
      if (draft.listenScripts.easy[index]?.trim())
        frame.listenScript = draft.listenScripts.easy[index].trim();
      return frame;
    }),
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

  const tiersFor = (field: TieredDraftField): Record<StoryDifficultyLevel, string[]> => {
    const backendFields = TIER_BACKEND_FIELD[field];
    return {
      easy: frames.map((frame, index) => {
        const value = frame?.[backendFields.easy] as string | undefined;
        return value || (field === "prompts" ? emptyCustomStoryDraft.prompts.easy[index] : "");
      }),
      medium: frames.map((frame) => (frame?.[backendFields.medium] as string | undefined) || ""),
      hard: frames.map((frame) => (frame?.[backendFields.hard] as string | undefined) || ""),
    };
  };

  return {
    title: story.title,
    learningGoal: story.learningGoal,
    level: story.level,
    lessonNumber: story.lessonNumber != null ? String(story.lessonNumber) : "",
    activeLevel: "easy",
    imageUrls: frames.map((frame) => frame?.imageUrl || ""),
    prompts: tiersFor("prompts"),
    vocabulary: tiersFor("vocabulary"),
    vocabularyGroups: frames.map((frame) => frame?.vocabularyGroups || null),
    phrases: tiersFor("phrases"),
    phrasesTranslation: tiersFor("phrasesTranslation"),
    vocabularyPinyin: tiersFor("vocabularyPinyin"),
    vocabularyPos: tiersFor("vocabularyPos"),
    vocabularyTranslation: tiersFor("vocabularyTranslation"),
    vocabularyDistractors: frames.map((frame) => frame?.vocabularyDistractors || ""),
    suggestedAnswers: tiersFor("suggestedAnswers"),
    listenAudioUrls: tiersFor("listenAudioUrls"),
    listenScripts: tiersFor("listenScripts"),
    linear: story.linear ?? false,
    firstFrameIsExample: story.firstFrameIsExample ?? false,
    narrativeMode: story.narrativeMode ?? "story",
  };
}

const VOCAB_POS_OPTIONS = ["N", "V", "Adj", "Adv", "MW", "Particle", "Phrase", "Other"];

function VocabularyTable({
  vocabulary,
  vocabularyPinyin,
  vocabularyPos,
  vocabularyTranslation,
  onChangeColumn,
}: {
  vocabulary: string;
  vocabularyPinyin: string;
  vocabularyPos: string;
  vocabularyTranslation: string;
  onChangeColumn: (
    field: "vocabulary" | "vocabularyPinyin" | "vocabularyPos" | "vocabularyTranslation",
    value: string,
  ) => void;
}) {
  const [rows, setRows] = useState<VocabRow[]>(() =>
    buildVocabRows(vocabulary, vocabularyPinyin, vocabularyPos, vocabularyTranslation),
  );

  const commitRows = (nextRows: VocabRow[]) => {
    setRows(nextRows);
    onChangeColumn("vocabulary", nextRows.map((r) => r.word).join(", "));
    onChangeColumn("vocabularyPinyin", nextRows.map((r) => r.pinyin).join(", "));
    onChangeColumn("vocabularyPos", nextRows.map((r) => r.pos).join(", "));
    onChangeColumn("vocabularyTranslation", nextRows.map((r) => r.translation).join(", "));
  };

  const updateCell = (rowIndex: number, field: keyof VocabRow, value: string) => {
    commitRows(rows.map((row, i) => (i === rowIndex ? { ...row, [field]: value } : row)));
  };

  const addRow = () => {
    commitRows([...rows, { word: "", pinyin: "", pos: "", translation: "" }]);
  };

  const removeRow = (rowIndex: number) => {
    commitRows(rows.filter((_, i) => i !== rowIndex));
  };

  return (
    <div className="vocab-table" role="table" aria-label="Vocabulary">
      <div className="vocab-table-header" role="row">
        <span role="columnheader">Chinese word</span>
        <span role="columnheader">Pinyin</span>
        <span role="columnheader">Part of speech</span>
        <span role="columnheader">English translation</span>
        <span role="columnheader" aria-hidden="true" />
      </div>
      {rows.map((row, index) => (
        <div className="vocab-table-row" role="row" key={index}>
          <input
            aria-label="Chinese word"
            value={row.word}
            onChange={(event) => updateCell(index, "word", event.target.value)}
            placeholder="餐廳"
          />
          <input
            aria-label="Pinyin"
            value={row.pinyin}
            onChange={(event) => updateCell(index, "pinyin", event.target.value)}
            placeholder="cāntīng"
          />
          <select
            aria-label="Part of speech"
            value={row.pos}
            onChange={(event) => updateCell(index, "pos", event.target.value)}
          >
            <option value="">--</option>
            {VOCAB_POS_OPTIONS.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          <input
            aria-label="English translation"
            value={row.translation}
            onChange={(event) => updateCell(index, "translation", event.target.value)}
            placeholder="restaurant"
          />
          <button
            type="button"
            className="vocab-table-remove"
            aria-label={`Remove word ${index + 1}`}
            onClick={() => removeRow(index)}
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" className="vocab-table-add-btn" onClick={addRow}>
        + Add word
      </button>
    </div>
  );
}

/** Per-scene "handy phrases" table — easy-to-learn, practice, and remember
 * chunks students can reuse (replaces the old single whole-story grammar
 * pattern/example fields). Same comma-joined-column convention as
 * VocabularyTable above, just with fewer columns. */
function PhraseTable({
  phrases,
  phrasesTranslation,
  onChangeColumn,
}: {
  phrases: string;
  phrasesTranslation: string;
  onChangeColumn: (field: "phrases" | "phrasesTranslation", value: string) => void;
}) {
  const [rows, setRows] = useState<PhraseRow[]>(() =>
    buildPhraseRows(phrases, phrasesTranslation),
  );

  const commitRows = (nextRows: PhraseRow[]) => {
    setRows(nextRows);
    onChangeColumn("phrases", nextRows.map((r) => r.phrase).join(", "));
    onChangeColumn("phrasesTranslation", nextRows.map((r) => r.translation).join(", "));
  };

  const updateCell = (rowIndex: number, field: keyof PhraseRow, value: string) => {
    commitRows(rows.map((row, i) => (i === rowIndex ? { ...row, [field]: value } : row)));
  };

  const addRow = () => {
    commitRows([...rows, { phrase: "", translation: "" }]);
  };

  const removeRow = (rowIndex: number) => {
    commitRows(rows.filter((_, i) => i !== rowIndex));
  };

  return (
    <div className="vocab-table phrase-table" role="table" aria-label="Phrases">
      <div className="vocab-table-header" role="row">
        <span role="columnheader">Phrase (Chinese)</span>
        <span role="columnheader">English translation</span>
        <span role="columnheader" aria-hidden="true" />
      </div>
      {rows.map((row, index) => (
        <div className="vocab-table-row phrase-table-row" role="row" key={index}>
          <input
            aria-label="Phrase"
            value={row.phrase}
            onChange={(event) => updateCell(index, "phrase", event.target.value)}
            placeholder="我想要…"
          />
          <input
            aria-label="English translation"
            value={row.translation}
            onChange={(event) => updateCell(index, "translation", event.target.value)}
            placeholder="I would like…"
          />
          <button
            type="button"
            className="vocab-table-remove"
            aria-label={`Remove phrase ${index + 1}`}
            onClick={() => removeRow(index)}
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" className="vocab-table-add-btn" onClick={addRow}>
        + Add phrase
      </button>
    </div>
  );
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
          <BiLabel zh="刪除" pinyin="Shānchú" en="Delete" />
        </button>
      </div>

      <div className="story-content">
        {record.audioUrl && (
          <div className="saved-audio-player">
            <strong><BiLabel zh="已存的錄音" pinyin="Yǐ cún de lùyīn" en="Saved voice recording" /></strong>
            <audio controls src={resolveImageUrl(record.audioUrl)} />
          </div>
        )}

        <div className="transcription-box">
          <strong><BiLabel zh="逐字稿" pinyin="Zhúzìgǎo" en="Transcription" /></strong>
          <p>
            {record.transcription || (
              <BiLabel zh="（沒聽到聲音）" pinyin="(méi tīngdào shēngyīn)" en="(no speech detected)" />
            )}
          </p>
        </div>

        {record.praatMetrics && (
          <>
            <div className="saved-metrics-summary">
              <div className="metric-item tone">
                <span className="metric-text">
                  <BiLabel zh="聲調：" pinyin="Shēngdiào:" en="Tone: " />
                  {getToneName(record.praatMetrics.detected_tone)}
                </span>
              </div>
              <div className="metric-item accuracy">
                <span className="metric-text">
                  <BiLabel zh="準確度：" pinyin="Zhǔnquè dù:" en="Accuracy: " />
                  {Math.round(record.praatMetrics.tone_accuracy)}%
                </span>
              </div>
              <div className="metric-item fluency">
                <span className="metric-text">
                  <BiLabel zh="Praat 流暢度：" pinyin="Praat liúchàng dù:" en="Praat fluency: " />
                  {Math.round(record.praatMetrics.fluency_score)}/100
                </span>
              </div>
              <div className="metric-item rate">
                <span className="metric-text">
                  <BiLabel zh="語速：" pinyin="Yǔsù:" en="Rate: " />
                  {record.praatMetrics.speech_rate.toFixed(1)}/s
                </span>
              </div>
            </div>

            {record.praatMetrics.pitch_contour?.length > 0 && (
              <div className="story-prosody-chart">
                <strong><BiLabel zh="Praat 音調圖" pinyin="Praat yīndiào tú" en="Praat prosody visualization" /></strong>
                <PitchChart
                  pitchContour={record.praatMetrics.pitch_contour}
                  detectedTone={record.praatMetrics.detected_tone}
                />
              </div>
            )}

            {record.praatMetrics.word_prosody?.length > 0 && (
              <div className="saved-word-prosody">
                <strong><BiLabel zh="逐字音調" pinyin="Zhúzì yīndiào" en="Word-by-word prosody" /></strong>
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
                zh={`AI 老師（${record.praatMetrics.ai_feedback.provider || "Gemini"}）`}
                pinyin={`AI lǎoshī (${record.praatMetrics.ai_feedback.provider || "Gemini"})`}
                en={`AI coach (${record.praatMetrics.ai_feedback.provider || "Gemini"})`}
              />
            </strong>
            <p>{record.praatMetrics.ai_feedback.fluency?.feedback}</p>
            <p>{record.praatMetrics.ai_feedback.grammar?.feedback}</p>
            <p>{record.praatMetrics.ai_feedback.vocabulary?.feedback}</p>
          </div>
        )}

        <div className="model-info">
          <span className="model-badge">{record.model}</span>
        </div>
      </div>
    </div>
  );
}

