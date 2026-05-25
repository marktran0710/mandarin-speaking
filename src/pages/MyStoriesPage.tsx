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

export default function MyStoriesPage({
  records,
  onDeleteRecord,
  onPracticeImage,
  mode = "student",
}: MyStoriesPageProps) {
  const isTeacher = mode === "teacher";
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
            <span>Pictures completed</span>
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
                      {topicCompleted}/{prompts.length} pictures completed
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
                                Picture {prompt.imageIndex + 1}
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
                            {latestRecord ? "Record another attempt" : "Record this picture"}
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
                              and what changed.
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
                      Picture {(record.imageIndex ?? 0) + 1} · {record.duration}s
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
  return record.imageUrl
    ? record.imageUrl === prompt.imageUrl
    : record.topicId === prompt.topicId &&
        record.imageIndex === prompt.imageIndex;
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
