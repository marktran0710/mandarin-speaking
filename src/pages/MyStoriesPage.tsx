import { useEffect, useState } from "react";
import PitchChart from "../PitchChart";
import { getTopicVocabulary } from "../TopicSelector";
import {
  canUseDatabase,
  createCustomStory as saveCustomStoryToDatabase,
  deleteCustomStoryFromDatabase,
  HelpRequest,
  listCustomStories,
} from "../database";
import {
  CustomTeacherStory,
  VocabGroup,
  loadCustomStories,
  loadPublishedTeacherTopics,
  resolveImageUrl,
  saveCustomStories,
} from "../utils/teacherStories";
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
  publishedTopics?: import("../TopicSelector").Topic[];
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

type TeacherView = "overview" | "help" | "materials" | "progress" | "recordings";

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

const emptyCustomStoryDraft = {
  title: "Taiwan Community Story",
  learningGoal: "Students describe who, where, what happened, and how people solved the problem.",
  level: "Beginner speaking",
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
  vocabularyGroups: [null, null, null, null, null, null] as (VocabGroup[] | null)[],
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
  helpRequests = [],
  onRaiseHand,
  onResolveHelpRequest,
  onRefreshRecords,
  publishedTopics,
}: MyStoriesPageProps) {
  const isTeacher = mode === "teacher";

  if (isTeacher) {
    return (
      <TeacherDashboard
        records={records}
        onDeleteRecord={onDeleteRecord}
        helpRequests={helpRequests}
        onResolveHelpRequest={onResolveHelpRequest}
        onRefreshRecords={onRefreshRecords}
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
          <p className="stories-kicker">My practice</p>
          <h1>My Story Workbook</h1>
          <p className="stories-subtitle">
            Choose a picture, record your story part, then revise when feedback
            is ready.
          </p>
        </div>

        <section className="student-progress-panel" aria-label="Learning progress">
          <div className="student-progress-main">
            <span>Progress</span>
            <strong>
              {completedPrompts}/{promptImages.length}
            </strong>
            <div className="summary-progress">
              <span
                style={{
                  width: `${Math.round(
                    (completedPrompts / promptImages.length) * 100,
                  )}%`,
                }}
              />
            </div>
          </div>
          <div className="student-progress-stats">
            <span>{records.length} recordings</span>
            <span>
              {averageFluency === null ? "No fluency score yet" : `${averageFluency}/100 fluency`}
            </span>
          </div>
        </section>

        <StudentHelpCard
          helpRequests={helpRequests}
          onRaiseHand={onRaiseHand}
        />

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
                    <strong>{topicCompleted}/{prompts.length}</strong>
                    <span>
                      {topicProgress}% complete
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
                                Part {prompt.imageIndex + 1}
                              </p>
                              <h3>{prompt.topicName}</h3>
                            </div>
                            <span
                              className={`learning-status ${
                                isRevised ? "revised" : latestRecord ? "ready" : "todo"
                              }`}
                            >
                              {latestRecord
                                ? isRevised
                                  ? "Revised"
                                  : hasFeedback
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
                              ? "Revise with another recording"
                              : "Record this part"}
                          </button>

                          {latestRecord && (
                            <div className="revision-summary">
                              <strong>
                                {attemptCount}{" "}
                                {attemptCount === 1 ? "attempt" : "attempts"} collected
                              </strong>
                            </div>
                          )}

                          {latestRecord ? (
                            <details className="prompt-feedback-details">
                              <summary>View feedback</summary>
                              <RecordCard
                                record={latestRecord}
                                onDeleteRecord={onDeleteRecord}
                                compact
                              />
                            </details>
                          ) : (
                            <div className="picture-empty-result">
                              Record this picture when you are ready.
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

function StudentHelpCard({
  helpRequests,
  onRaiseHand,
}: {
  helpRequests: HelpRequest[];
  onRaiseHand?: (message: string) => void;
}) {
  const [message, setMessage] = useState("I need help with my story.");
  const studentName = getSessionName("studentSession", "Student");
  const activeRequest = helpRequests.find(
    (request) =>
      request.studentName === studentName && request.status === "open",
  );

  return (
    <section className="student-help-card" aria-label="Ask teacher for help">
      <div>
        <p className="stories-kicker">Teacher support</p>
        <h2>{activeRequest ? "Your hand is raised" : "Raise your hand"}</h2>
        <p>
          {activeRequest
            ? "Your teacher can see your request. You can update the note if your question changed."
            : "Send a quiet help request while you keep working on your story."}
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
          placeholder="What should the teacher help with?"
        />
        <button type="submit" disabled={!onRaiseHand}>
          {activeRequest ? "Update request" : "Raise hand"}
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
}: {
  records: AudioRecord[];
  onDeleteRecord: (id: string) => void;
  helpRequests: HelpRequest[];
  onResolveHelpRequest?: (id: string) => void;
  onRefreshRecords?: () => Promise<void>;
}) {
  const [activeView, setActiveView] = useState<TeacherView>("overview");
  const [refreshing, setRefreshing] = useState(false);
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
    field: "title" | "learningGoal" | "level",
    value: string,
  ) => {
    setCustomDraft((draft) => ({ ...draft, [field]: value }));
    setValidationErrors((errors) => ({ ...errors, [field]: undefined, form: undefined }));
    clearNotice();
  };

  const updateDraftGroups = (index: number, groups: VocabGroup[] | null) => {
    setCustomDraft((draft) => ({
      ...draft,
      vocabularyGroups: draft.vocabularyGroups.map((g, i) => i === index ? groups : g),
    }));
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
    setValidationErrors((errors) =>
      clearFrameError(errors, index, field),
    );
    clearNotice();
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
          storyToStore = { ...savedStory, ...persisted } as CustomTeacherStory;
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
    { id: "help", label: "Help", count: openHelpRequests.length },
    { id: "materials", label: "Materials", count: customStories.length },
    { id: "progress", label: "Progress" },
    { id: "recordings", label: "Recordings", count: records.length },
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
            <RecentSubmissionsPanel records={records} />
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
                      <img src={resolveImageUrl(imageUrl)} alt={`Custom story frame ${index + 1}`} />
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
              <p>{preparedFrameCount}/6 frames prepared</p>
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
                        <strong>{story.title}</strong>
                        <span>
                          {story.level} - {story.published ? "Published" : "Draft"}
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
      )}
    </div>
  );
}

function RecentSubmissionsPanel({ records }: { records: AudioRecord[] }) {
  return (
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
          {records.map((record) => (
            <div className="teacher-submission-row" key={record.id}>
              <div>
                <strong>{getTopicLabel(record.topicId)}</strong>
                <span>
                  Part {(record.imageIndex ?? 0) + 1} - {record.duration}s
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
    })),
  };
}

function storyToDraft(story: CustomTeacherStory): typeof emptyCustomStoryDraft {
  const frames = Array.from({ length: 6 }, (_, index) => story.frames[index]);

  return {
    title: story.title,
    learningGoal: story.learningGoal,
    level: story.level,
    imageUrls: frames.map((frame) => frame?.imageUrl || ""),
    prompts: frames.map((frame, index) =>
      frame?.prompt || emptyCustomStoryDraft.prompts[index],
    ),
    vocabulary: frames.map((frame) => frame?.vocabulary || ""),
    vocabularyGroups: frames.map((frame) => frame?.vocabularyGroups || null),
  };
}

function clearFrameError(
  errors: CustomStoryValidationErrors,
  index: number,
  field: "imageUrls" | "prompts" | "vocabulary",
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

const STORY_CANVAS_CATEGORIES = [
  { name: "Characters",     hanzi: "人物", sub: "Who is in the story?",               color: "#4f46e5" },
  { name: "Actions",        hanzi: "動作", sub: "What are they doing?",               color: "#d97706" },
  { name: "Settings",       hanzi: "場景", sub: "Where is it happening?",             color: "#0891b2" },
  { name: "Objects & Tools",hanzi: "物品", sub: "What are they using or holding?",    color: "#7c3aed" },
  { name: "Grammar Glue",   hanzi: "語法", sub: "Numbers, Measure Words & Particles", color: "#be185d" },
  { name: "Outcomes",       hanzi: "結果", sub: "Final result or social closing?",    color: "#059669" },
];

const DEFAULT_GROUP_NAMES = STORY_CANVAS_CATEGORIES.map(c => c.name);

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

  const initGroups = (): VocabGroup[] =>
    DEFAULT_GROUP_NAMES.map((name) => ({ name, words: [] }));

  const handleToggle = () => {
    onChange(active ? null : initGroups());
  };

  if (!active) {
    return (
      <button type="button" className="vocab-group-toggle-btn" onClick={handleToggle}>
        + Add Story Canvas categories (Characters · Actions · Settings · Objects & Tools · Grammar Glue · Outcomes)
      </button>
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
        <span>Taiwan Community Story Canvas — Word Categories</span>
        <button type="button" className="vocab-group-remove-btn" onClick={handleToggle}>Remove categories</button>
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
          const cat = STORY_CANVAS_CATEGORIES[gi];
          return (
          <div key={gi} className="vocab-group-slot">
            <div className="vocab-group-slot-header" style={{ background: cat?.color ?? "#64748b" }}>
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
        {record.audioUrl && (
          <div className="saved-audio-player">
            <strong>Saved voice recording</strong>
            <audio controls src={record.audioUrl} />
          </div>
        )}

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
  const topic = getStudentTopics().find((item) => item.id === topicId);
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
