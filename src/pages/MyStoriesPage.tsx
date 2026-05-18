import "./MyStoriesPage.css";

interface AudioRecord {
  id: string;
  timestamp: string;
  duration: number;
  transcription: string;
  model: string;
  topicId?: string;
  praatMetrics?: any;
}

interface MyStoriesPageProps {
  records: AudioRecord[];
  onDeleteRecord: (id: string) => void;
}

export default function MyStoriesPage({
  records,
  onDeleteRecord,
}: MyStoriesPageProps) {
  const getToneName = (tone: number): string => {
    const toneNames: Record<number, string> = {
      1: "High Level (妈 mā)",
      2: "Rising (麻 má)",
      3: "Falling-Rising (马 mǎ)",
      4: "Falling (骂 mà)",
    };
    return toneNames[tone] || "Unknown";
  };

  const getTopicEmoji = (topicId?: string): string => {
    const emojis: Record<string, string> = {
      adventure: "🏔️",
      nature: "🌳",
      fantasy: "✨",
      school: "🏫",
      mystery: "🔍",
      "daily-life": "🏠",
    };
    return emojis[topicId || ""] || "📚";
  };

  return (
    <div className="my-stories-page">
      <div className="stories-header">
        <h1>📚 My Stories</h1>
        <p className="stories-subtitle">
          {records.length} {records.length === 1 ? "story" : "stories"} saved
        </p>
      </div>

      {records.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🎤</div>
          <h2>No Stories Yet</h2>
          <p>Start creating your first story to see it appear here!</p>
        </div>
      ) : (
        <div className="stories-grid">
          {records.map((record) => (
            <div key={record.id} className="story-card">
              <div className="story-header">
                <div className="story-title-group">
                  <span className="topic-emoji">
                    {getTopicEmoji(record.topicId)}
                  </span>
                  <div>
                    <div className="story-timestamp">{record.timestamp}</div>
                    <div className="story-duration">⏱️ {record.duration}s</div>
                  </div>
                </div>
                <button
                  className="btn-delete"
                  onClick={() => onDeleteRecord(record.id)}
                  title="Delete this story"
                >
                  🗑️
                </button>
              </div>

              <div className="story-content">
                <div className="transcription-box">
                  <strong>📝 Transcription:</strong>
                  <p>{record.transcription || "(no speech detected)"}</p>
                </div>

                {record.praatMetrics && (
                  <div className="metrics-summary">
                    <div className="metric-item tone">
                      <span className="metric-icon">🎯</span>
                      <span className="metric-text">
                        Tone: {getToneName(record.praatMetrics.detected_tone)}
                      </span>
                    </div>
                    <div className="metric-item accuracy">
                      <span className="metric-icon">📊</span>
                      <span className="metric-text">
                        Accuracy:{" "}
                        {Math.round(record.praatMetrics.tone_accuracy)}%
                      </span>
                    </div>
                    <div className="metric-item fluency">
                      <span className="metric-icon">💬</span>
                      <span className="metric-text">
                        Fluency: {Math.round(record.praatMetrics.fluency_score)}
                        /100
                      </span>
                    </div>
                    <div className="metric-item rate">
                      <span className="metric-icon">⚡</span>
                      <span className="metric-text">
                        Rate: {record.praatMetrics.speech_rate.toFixed(1)}/s
                      </span>
                    </div>
                  </div>
                )}

                <div className="model-info">
                  <span className="model-badge">{record.model}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
