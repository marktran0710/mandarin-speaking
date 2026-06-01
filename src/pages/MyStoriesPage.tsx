import { useMemo, useState } from "react";
import PitchChart from "../PitchChart";
import { TOPICS } from "../TopicSelector";
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
  praatMetrics?: any;
}

interface WordProsody {
  token: string;
  index: number;
  pitch_contour: Array<[number, number]>;
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
}

interface PromptImage {
  topicId: string;
  topicName: string;
  description: string;
  imageUrl: string;
  imageIndex: number;
  vocabulary: string[];
}

interface CustomStoryFrame {
  imageUrl: string;
  prompt: string;
  vocabulary: string;
}

interface CustomTeacherStory {
  id: string;
  title: string;
  learningGoal: string;
  level: string;
  frames: CustomStoryFrame[];
}

interface CustomStoryValidationErrors {
  title?: string;
  learningGoal?: string;
  form?: string;
  frames?: Record<number, { imageUrl?: string; prompt?: string }>;
}

const PROMPT_IMAGES: PromptImage[] = TOPICS.flatMap((topic) =>
  topic.images.map((imageUrl, imageIndex) => ({
    topicId: topic.id,
    topicName: topic.name,
    description: topic.description,
    imageUrl,
    imageIndex,
    vocabulary: topic.vocabulary[imageIndex] || [],
  })),
);

const CUSTOM_STORY_STORAGE_KEY = "teacherCustomStories";

const emptyCustomStoryDraft = {
  title: "Taiwan Community Story",
  learningGoal: "Students describe who, where, what happened, and how people solved the problem.",
  level: "Beginner speaking",
  imageUrls: ["", "", "", ""],
  prompts: [
    "Introduce the place and the people.",
    "Describe the first event.",
    "Explain the problem or surprise.",
    "Tell the result and feeling.",
  ],
  vocabulary: ["", "", "", ""],
};

function loadCustomStories(): CustomTeacherStory[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const stored = window.localStorage.getItem(CUSTOM_STORY_STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
}

function saveCustomStories(stories: CustomTeacherStory[]) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(CUSTOM_STORY_STORAGE_KEY, JSON.stringify(stories));
  }
}

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
    const promptMissing = !draft.prompts[index].trim();

    if (imageMissing || promptMissing) {
      frameErrors[index] = {
        ...(imageMissing
          ? { imageUrl: `Frame ${index + 1} needs an image URL or uploaded image.` }
          : {}),
        ...(promptMissing
          ? { prompt: `Frame ${index + 1} needs a student prompt.` }
          : {}),
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
}: MyStoriesPageProps) {
  const isTeacher = mode === "teacher";
  const [customStories, setCustomStories] = useState<CustomTeacherStory[]>(
    () => loadCustomStories(),
  );
  const [customDraft, setCustomDraft] = useState(emptyCustomStoryDraft);
  const [validationErrors, setValidationErrors] =
    useState<CustomStoryValidationErrors>({});
  const [customStoryNotice, setCustomStoryNotice] = useState("");
  const completedPrompts = PROMPT_IMAGES.filter((prompt) =>
    records.some((record) => isPromptRecord(record, prompt)),
  ).length;
  const analyzedRecords = records.filter((record) => record.praatMetrics);
  const averageFluency =
    analyzedRecords.length > 0
      ? Math.round(
          analyzedRecords.reduce(
            (sum, record) => sum + (record.praatMetrics?.fluency_score || 0),
            0,
          ) / analyzedRecords.length,
        )
      : null;
  const feedbackReadyRecords = records.filter(
    (record) => record.praatMetrics?.ai_feedback,
  );
  const averageToneAccuracy =
    analyzedRecords.length > 0
      ? Math.round(
          analyzedRecords.reduce(
            (sum, record) => sum + (record.praatMetrics?.tone_accuracy || 0),
            0,
          ) / analyzedRecords.length,
        )
      : null;
  const preparedFrameCount = useMemo(
    () =>
      customDraft.imageUrls.filter((imageUrl, index) => {
        return imageUrl.trim() || customDraft.prompts[index].trim();
      }).length,
    [customDraft],
  );

  const updateDraftField = (
    field: "title" | "learningGoal" | "level",
    value: string,
  ) => {
    setCustomDraft((draft) => ({ ...draft, [field]: value }));
    setValidationErrors((errors) => ({ ...errors, [field]: undefined, form: undefined }));
    setCustomStoryNotice("");
  };

  const updateDraftFrame = (
    field: "imageUrls" | "prompts" | "vocabulary",
    index: number,
    value: string,
  ) => {
    setCustomDraft((draft) => ({
      ...draft,
      [field]: draft[field].map((item, itemIndex) =>
        itemIndex === index ? value : item,
      ),
    }));
    setValidationErrors((errors) => {
      if (!errors.frames?.[index]) {
        return { ...errors, form: undefined };
      }

      const nextFrames = { ...errors.frames };
      nextFrames[index] = {
        ...nextFrames[index],
        ...(field === "imageUrls" ? { imageUrl: undefined } : {}),
        ...(field === "prompts" ? { prompt: undefined } : {}),
      };

      if (!nextFrames[index].imageUrl && !nextFrames[index].prompt) {
        delete nextFrames[index];
      }

      return {
        ...errors,
        form: undefined,
        frames: Object.keys(nextFrames).length > 0 ? nextFrames : undefined,
      };
    });
    setCustomStoryNotice("");
  };

  const handleUploadFrameImage = (index: number, file?: File) => {
    if (!file) {
      return;
    }

    if (!file.type.startsWith("image/")) {
      setValidationErrors((errors) => ({
        ...errors,
        form: "Please upload an image file.",
      }));
      return;
    }

    if (file.size > 1_500_000) {
      setValidationErrors((errors) => ({
        ...errors,
        form: "This image is too large for browser storage. Use an image under 1.5 MB or paste an image URL.",
      }));
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

  const handleSaveCustomStory = () => {
    const errors = validateCustomStoryDraft(customDraft);
    if (
      errors.title ||
      errors.learningGoal ||
      errors.form ||
      Object.keys(errors.frames ?? {}).length > 0
    ) {
      setValidationErrors(errors);
      setCustomStoryNotice("");
      return;
    }

    const frames = customDraft.imageUrls.map((imageUrl, index) => ({
      imageUrl: imageUrl.trim(),
      prompt: customDraft.prompts[index].trim(),
      vocabulary: customDraft.vocabulary[index].trim(),
    }));
    const story: CustomTeacherStory = {
      id: `custom-story-${Date.now()}`,
      title: customDraft.title.trim() || "Untitled teacher story",
      learningGoal: customDraft.learningGoal.trim(),
      level: customDraft.level.trim() || "Custom activity",
      frames,
    };
    const nextStories = [story, ...customStories];

    try {
      saveCustomStories(nextStories);
      setCustomStories(nextStories);
      setCustomDraft(emptyCustomStoryDraft);
      setValidationErrors({});
      setCustomStoryNotice("Custom story saved.");
    } catch {
      setValidationErrors({
        form: "The story could not be saved. Uploaded images may be too large for browser storage; try smaller images or image URLs.",
      });
      setCustomStoryNotice("");
    }
  };

  const handleDeleteCustomStory = (id: string) => {
    const nextStories = customStories.filter((story) => story.id !== id);
    setCustomStories(nextStories);
    saveCustomStories(nextStories);
  };

  if (!isTeacher) {
    return (
      <div className="my-stories-page">
        <div className="stories-header">
          <p className="stories-kicker">Student learning portfolio</p>
          <h1>My Story Workbook</h1>
          <p className="stories-subtitle">
            Practice one picture at a time, review your recording, and use
            Praat prosody plus Gemini language feedback to improve the next
            attempt.
          </p>
        </div>

        <section className="learning-summary" aria-label="Learning progress">
          <div className="summary-card">
            <span>Story parts completed</span>
            <strong>
              {completedPrompts}/{PROMPT_IMAGES.length}
            </strong>
            <div className="summary-progress">
              <span
                style={{
                  width: `${Math.round(
                    (completedPrompts / PROMPT_IMAGES.length) * 100,
                  )}%`,
                }}
              />
            </div>
          </div>
          <div className="summary-card">
            <span>Total recordings</span>
            <strong>{records.length}</strong>
            <p>Every attempt is saved under its picture.</p>
          </div>
          <div className="summary-card">
            <span>Average Praat fluency</span>
            <strong>{averageFluency === null ? "--" : `${averageFluency}/100`}</strong>
            <p>Appears after analyzed recordings.</p>
          </div>
        </section>

        <div className="learning-workbook">
          {TOPICS.map((topic) => {
            const prompts = PROMPT_IMAGES.filter(
              (prompt) => prompt.topicId === topic.id,
            );
            const topicRecords = records.filter(
              (record) => record.topicId === topic.id,
            );
            const topicCompleted = prompts.filter((prompt) =>
              records.some((record) => isPromptRecord(record, prompt)),
            ).length;
            const topicProgress = Math.round(
              (topicCompleted / prompts.length) * 100,
            );

            return (
              <section className="topic-workbook-section" key={topic.id}>
                <div className="topic-workbook-header">
                  <div>
                    <p className="stories-kicker">{topic.name}</p>
                    <h2>{topic.description}</h2>
                  </div>
                  <div className="topic-progress-card">
                    <strong>{topicProgress}%</strong>
                    <span>
                      {topicCompleted}/{prompts.length} story parts completed
                    </span>
                  </div>
                </div>

                <div className="prompt-grid">
                  {prompts.map((prompt) => {
                    const promptRecords = records.filter((record) =>
                      isPromptRecord(record, prompt),
                    );
                    const latestRecord = promptRecords[0];
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
                                Part {prompt.imageIndex + 1}
                              </p>
                              <h3>{prompt.topicName}</h3>
                            </div>
                            <span
                              className={`learning-status ${
                                latestRecord ? "ready" : "todo"
                              }`}
                            >
                              {latestRecord
                                ? hasFeedback
                                  ? "Feedback ready"
                                  : "Recorded"
                                : "Needs recording"}
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
                            {latestRecord
                              ? "Record another attempt"
                              : "Record this part"}
                          </button>

                          {latestRecord ? (
                            <RecordCard
                              record={latestRecord}
                              onDeleteRecord={onDeleteRecord}
                              compact
                            />
                          ) : (
                            <div className="picture-empty-result">
                              Focus on describing who, where, what happened,
                              and how this part connects to the next one.
                            </div>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>

                {topicRecords.length > 0 && (
                  <p className="topic-record-count">
                    {topicRecords.length} total{" "}
                    {topicRecords.length === 1 ? "attempt" : "attempts"} in
                    this topic.
                  </p>
                )}
              </section>
            );
          })}
        </div>
      </div>
    );
  }

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
        </div>
      </section>

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

      <section className="teacher-panel teacher-content-builder">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Custom materials</p>
            <h2>Create Story Activity</h2>
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

                return (
                <div
                  className={`teacher-frame-card ${frameError ? "has-error" : ""}`}
                  key={index}
                >
                  <div className="teacher-frame-image-preview">
                    {imageUrl ? (
                      <img src={imageUrl} alt={`Custom story frame ${index + 1}`} />
                    ) : (
                      <span>Frame {index + 1}</span>
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
                      Student prompt
                      <textarea
                        aria-invalid={Boolean(frameError?.prompt)}
                        value={customDraft.prompts[index]}
                        onChange={(event) =>
                          updateDraftFrame("prompts", index, event.target.value)
                        }
                        rows={2}
                        placeholder="What should students say for this picture?"
                      />
                      {frameError?.prompt && (
                        <span className="teacher-form-error">
                          {frameError.prompt}
                        </span>
                      )}
                    </label>
                    <label>
                      Vocabulary
                      <input
                        value={customDraft.vocabulary[index]}
                        onChange={(event) =>
                          updateDraftFrame("vocabulary", index, event.target.value)
                        }
                        placeholder="台北, 下雨, 幫忙"
                      />
                    </label>
                  </div>
                </div>
                );
              })}
            </div>

            <div className="teacher-builder-actions">
              <p>{preparedFrameCount}/4 frames prepared</p>
              <button type="submit" className="btn-save-custom-story">
                Save custom story
              </button>
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
                        <strong>{story.title}</strong>
                        <span>{story.level}</span>
                      </div>
                      <button
                        type="button"
                        className="btn-delete-custom-story"
                        onClick={() => handleDeleteCustomStory(story.id)}
                      >
                        Delete
                      </button>
                    </div>
                    <p>{story.learningGoal}</p>
                    <div className="custom-story-frame-strip">
                      {story.frames.map((frame, index) => (
                        <div className="custom-story-mini-frame" key={index}>
                          {frame.imageUrl ? (
                            <img src={frame.imageUrl} alt={`${story.title} frame ${index + 1}`} />
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

      <section className="teacher-dashboard-grid">
        <div className="teacher-panel topic-coverage-panel">
          <div className="teacher-panel-header">
            <div>
              <p className="stories-kicker">Curriculum coverage</p>
              <h2>Topic Progress</h2>
            </div>
          </div>

          <div className="topic-coverage-list">
            {TOPICS.map((topic) => {
              const topicRecords = records.filter(
                (record) => record.topicId === topic.id,
              );
              const coverage = Math.min(
                100,
                Math.round((topicRecords.length / topic.images.length) * 100),
              );

              return (
                <div className="topic-coverage-row" key={topic.id}>
                  <div>
                    <strong>{topic.name}</strong>
                    <span>
                      {topicRecords.length}{" "}
                      {topicRecords.length === 1 ? "attempt" : "attempts"}
                    </span>
                  </div>
                  <div className="coverage-meter" aria-label={`${topic.name} coverage`}>
                    <span style={{ width: `${coverage}%` }} />
                  </div>
                </div>
              );
            })}
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

      <section className="teacher-panel teacher-recordings-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Detailed review</p>
            <h2>Student Recording Evidence</h2>
          </div>
        </div>

        {records.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">Data</div>
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
          title="Delete this story"
        >
          Delete
        </button>
      </div>

      <div className="story-content">
        <div className="transcription-box">
          <strong>Transcription</strong>
          <p>{record.transcription || "(no speech detected)"}</p>
        </div>

        {record.praatMetrics && (
          <>
            <div className="metrics-summary">
              <div className="metric-item tone">
                <span className="metric-text">
                  Tone: {getToneName(record.praatMetrics.detected_tone)}
                </span>
              </div>
              <div className="metric-item accuracy">
                <span className="metric-text">
                  Accuracy: {Math.round(record.praatMetrics.tone_accuracy)}%
                </span>
              </div>
              <div className="metric-item fluency">
                <span className="metric-text">
                  Praat fluency:{" "}
                  {Math.round(record.praatMetrics.fluency_score)}/100
                </span>
              </div>
              <div className="metric-item rate">
                <span className="metric-text">
                  Rate: {record.praatMetrics.speech_rate.toFixed(1)}/s
                </span>
              </div>
            </div>

            {record.praatMetrics.pitch_contour?.length > 0 && (
              <div className="story-prosody-chart">
                <strong>Praat prosody visualization</strong>
                <PitchChart
                  pitchContour={record.praatMetrics.pitch_contour}
                  detectedTone={record.praatMetrics.detected_tone}
                />
              </div>
            )}

            {record.praatMetrics.word_prosody?.length > 0 && (
              <div className="saved-word-prosody">
                <strong>Word-by-word prosody</strong>
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
              AI coach ({record.praatMetrics.ai_feedback.provider || "Gemini"})
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
    1: "High Level (ma1)",
    2: "Rising (ma2)",
    3: "Falling-Rising (ma3)",
    4: "Falling (ma4)",
  };
  return toneNames[tone] || "Unknown";
}

function getTopicLabel(topicId?: string): string {
  const topic = TOPICS.find((item) => item.id === topicId);
  return topic?.name || "Story";
}

function formatContourShape(shape: string): string {
  const labels: Record<string, string> = {
    dip: "Dipping",
    falling: "Falling",
    level: "Level",
    rising: "Rising",
    variable: "Variable",
  };
  return labels[shape] || "Variable";
}
