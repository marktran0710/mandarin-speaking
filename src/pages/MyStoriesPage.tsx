import React, { useEffect, useState } from "react";
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
import "./MyStoriesPage.css";
import StudentHelpCard from "../components/StudentHelpCard";
import MyStoryFeedbackHistory from "../components/MyStoryFeedbackHistory";
import TeacherHelpQueue from "../components/TeacherHelpQueue";
import RecordCard from "../components/RecordCard";
import QuizAnalyticsPanel from "../components/QuizAnalyticsPanel";
import RecordingAnalyticsPanel from "../components/RecordingAnalyticsPanel";
import TeacherOverviewView from "../components/TeacherOverviewView";
import TeacherProgressView from "../components/TeacherProgressView";
import TeacherRecordingsView from "../components/TeacherRecordingsView";
import TeacherSubmissionsView from "../components/TeacherSubmissionsView";
import VocabularyTable from "../components/VocabularyTable";
import PhraseTable from "../components/PhraseTable";
import VocabGroupEditor from "../components/VocabGroupEditor";
import {
  buildPhraseRows,
  buildVocabRows,
  clearFrameError,
  frameCountForMode,
  getAudioUploadError,
  getAverageMetric,
  getImageUploadError,
  getPromptImages,
  getSessionName,
  getStudentTopics,
  hasCustomStoryErrors,
  isPromptRecord,
  mergePhraseSuggestions,
  mergeVocabSuggestions,
  narrativeModeLabel,
  resizeToCount,
  type PhraseSuggestion,
  type VocabWordSuggestion,
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
    field: "title" | "learningGoal" | "lessonNumber",
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
        <TeacherOverviewView
          totalRecords={records.length}
          feedbackReadyCount={feedbackReadyRecords.length}
          averageFluency={averageFluency}
          averageToneAccuracy={averageToneAccuracy}
          helpRequests={helpRequests}
          onResolveHelpRequest={onResolveHelpRequest}
        />
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
                Level
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
                          {story.published ? "Published" : "Draft"}
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

      {activeView === "progress" && <TeacherProgressView records={records} />}

      {activeView === "recordings" && (
        <TeacherRecordingsView records={records} onDeleteRecord={onDeleteRecord} />
      )}

      {activeView === "submissions" && (
        <TeacherSubmissionsView submissions={submissions} />
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


