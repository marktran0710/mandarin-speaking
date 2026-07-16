import { useId } from "react";
import PitchChart from "./PitchChart";
import { resolveImageUrl } from "../utils/teacherStories";
import { BiLabel } from "./BiLabel";
import { getToneName, getTopicLabel, formatContourShape } from "../utils/myStoriesUtils";
import type { AudioRecord, WordProsody } from "../pages/MyStoriesPage";

export default function RecordCard({
  record,
  onDeleteRecord,
  compact = false,
}: {
  record: AudioRecord;
  onDeleteRecord: (id: string) => void;
  compact?: boolean;
}) {
  const savedAudioLabelId = useId();
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
            <strong id={savedAudioLabelId}><BiLabel zh="已存的錄音" pinyin="Yǐ cún de lùyīn" en="Saved voice recording" /></strong>
            <audio controls src={resolveImageUrl(record.audioUrl)} aria-labelledby={savedAudioLabelId} />
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
