import type { AudioRecord } from "../MyStoriesPage";
import {
  type AnalysisPhase, type DebugProcessingState, type JsonObject, type ProcessingTraceStage, type StageDefinition,
  metric, RUBRICS, stageDlContent, StageCard, traceDurationLabel, traceStatusLabel,
} from "./utils";

interface DebugPipelineDetailsProps {
  stageDefinitions: StageDefinition[];
  inputSource: "microphone" | "upload";
  processingState: DebugProcessingState;
  analysisPhase: AnalysisPhase;
  analysisElapsed: number;
  activeTrace: ProcessingTraceStage[];
  praat: JsonObject;
  ai: JsonObject;
  outputReady: boolean;
  captureEntry: ProcessingTraceStage;
  statusForStage: (stageId: string) => ProcessingTraceStage;
  record: AudioRecord;
  words: JsonObject[];
  contentGate: string;
  canScorePronunciation: boolean;
  failedWords: JsonObject[];
}

export default function DebugPipelineDetails(props: DebugPipelineDetailsProps) {
  const { stageDefinitions, inputSource, processingState, analysisPhase, analysisElapsed, activeTrace, praat, ai,
    outputReady, captureEntry, statusForStage, record, words, contentGate, canScorePronunciation, failedWords } = props;
  const content = (ai.content_accuracy ?? {}) as JsonObject;
  const showProcessingTrace = processingState !== "idle" || activeTrace.length > 0;
  return <>
      {showProcessingTrace && (
        <section className={`pdebug-trace pdebug-trace-${processingState}`} aria-labelledby="pdebug-trace-heading">
          <div className="pdebug-trace-heading">
            <div>
              <span>PROCESSING TRACE</span>
              <h3 id="pdebug-trace-heading">
                {(processingState === "complete" || activeTrace.length > 0)
                  ? "How this attempt became the result"
                  : processingState === "error"
                    ? "Where processing stopped"
                    : "Processing this student attempt"}
              </h3>
            </div>
            {(processingState === "uploading" || processingState === "processing") && (
              <span className="pdebug-trace-live">
                {analysisPhase === "preparing" ? "Preparing audio" : `Backend running · ${analysisElapsed}s`}
              </span>
            )}
            {processingState === "complete" && praat.processing_trace && (
              <small>{traceDurationLabel((praat.processing_trace as JsonObject).total_duration_ms as number)}</small>
            )}
          </div>
          <ol className="pdebug-trace-list">
            {stageDefinitions.map((definition) => {
              const displayDefinition = definition.id === "capture" && inputSource === "upload"
                ? { ...definition, label: "Upload", description: "Audio file input" }
                : definition;
              const entry = definition.id === "capture" ? captureEntry : statusForStage(definition.id);
              return (
                <li key={definition.id} data-status={entry.status}>
                  <span className="pdebug-trace-marker" aria-hidden="true" />
                  <div>
                    <strong>{displayDefinition.label}</strong>
                    <span>{displayDefinition.description}</span>
                    {entry.detail && <small>{entry.detail}</small>}
                  </div>
                  <em>
                    {traceStatusLabel(entry.status)}
                    {entry.duration_ms !== undefined && ` · ${traceDurationLabel(entry.duration_ms)}`}
                  </em>
                </li>
              );
            })}
          </ol>
          {processingState === "processing" && activeTrace.length === 0 && (
            <p className="pdebug-trace-note">Steps below fill in live as the backend completes each one.</p>
          )}
        </section>
      )}

      {outputReady && <div className="pdebug-score-grid" aria-label="Attempt score summary">
        <article><span>Tone contour</span><strong>{metric(praat.tone_accuracy, "%")}</strong><small>Praat/tone matcher</small></article>
        <article><span>Fluency</span><strong>{metric(praat.fluency_score, "/100")}</strong><small>CAF + pitch continuity</small></article>
        <article><span>Vocabulary</span><strong>{metric(ai.vocabulary_coverage?.score, "/100")}</strong><small>{ai.provider || "No provider"}</small></article>
        <article><span>Content gate</span><strong>{contentGate}</strong><small>{content.judged === false ? "Placeholder, not a score" : "AI scene comparison"}</small></article>
      </div>}

      <div className="pdebug-layer-grid">
        {stageDefinitions.map((definition) => {
          const displayDefinition = definition.id === "capture" && inputSource === "upload"
            ? { ...definition, label: "Upload" }
            : definition;
          const entry = definition.id === "capture" ? captureEntry : statusForStage(definition.id);
          const dlItems = stageDlContent(definition.id, entry, {
            record, praat, ai, words, contentGate, canScorePronunciation,
          });
          return (
            <StageCard
              key={definition.id}
              id={definition.id}
              label={displayDefinition.label}
              description={definition.description}
              entry={entry}
              dlItems={dlItems}
            >
              {definition.id === "quality_gate" && outputReady && (
                <>
                  <div className="pdebug-decisions">
                    <div data-state={canScorePronunciation ? "pass" : "retry"}>
                      <strong>Recording quality</strong>
                      <span>{canScorePronunciation ? "Scoreable" : "Retry recording"}</span>
                    </div>
                    <div data-state={failedWords.length === 0 ? "pass" : "retry"}>
                      <strong>Pronunciation mastery</strong>
                      <span>{failedWords.length === 0 ? "Passed" : `Drill ${failedWords.length} word${failedWords.length === 1 ? "" : "s"}`}</span>
                    </div>
                    <div data-state={contentGate === "Passed" || contentGate === "Not judged" ? "pass" : "retry"}>
                      <strong>Scene meaning</strong>
                      <span>{contentGate}</span>
                    </div>
                  </div>
                  {failedWords.length > 0 && (
                    <table className="pdebug-word-table">
                      <thead><tr><th>Word</th><th>Tone score</th><th>Weakest syllable</th><th>Verdict</th></tr></thead>
                      <tbody>{failedWords.map((word: JsonObject, index: number) => {
                        const syllables = Array.isArray(word.syllables) ? word.syllables : [];
                        const weakest = syllables.length
                          ? [...syllables].sort((a, b) => Number(a.score) - Number(b.score))[0]
                          : null;
                        return (
                          <tr key={`${word.token}-${index}`}>
                            <td lang="zh-Hant">{word.token || `Word ${index + 1}`}</td>
                            <td>{metric(word.tone_accuracy, "%")}</td>
                            <td>{weakest ? `${weakest.char}: ${metric(weakest.score)}` : "Not available"}</td>
                            <td>{word.judged === false ? "Unjudged" : "Below 58 minimum"}</td>
                          </tr>
                        );
                      })}</tbody>
                    </table>
                  )}
                </>
              )}
            </StageCard>
          );
        })}
      </div>

      <section className="pdebug-rubrics" aria-labelledby="pdebug-rubrics-heading">
        <div>
          <p className="tdash-view-kicker">Scoring contract</p>
          <h2 id="pdebug-rubrics-heading">Rubrics used by the current pipeline</h2>
          <p>Practice does not collapse everything into one opaque overall score. Acoustic, language and content signals remain separate, then gates determine the next action.</p>
        </div>
        <div className="pdebug-rubric-list">
          {RUBRICS.map((rubric) => (
            <article key={rubric.name}>
              <span>{rubric.owner}</span><h3>{rubric.name}</h3><p>{rubric.rule}</p>
            </article>
          ))}
        </div>
      </section>
  </>;
}
