import type { PronunciationEvaluation } from "@shared/api/pronunciation";
import ContourOverlayChart from "./ContourOverlayChart";
import LibrosaPitchChart from "../../../components/pitch/LibrosaPitchChart";
import { dimensionLabel, feedbackBadge, flagLabel, shapeLabel } from "./model";

const UNSCORABLE_TITLE: Record<string, string> = {
  recording_unusable: "The recording was too quiet, too short or unclear",
  no_voiced_speech: "No speech pitch could be measured",
  audio_unreadable: "The audio file could not be read",
  no_measurable_tones: "No tone could be measured in this sentence",
  speaking_rate_implausible: "This did not sound like the whole sentence",
};

function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : `${Math.round(value * 100)}%`;
}

function metricPercent(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? percent(value) : "–";
}

export default function PronunciationResult({ result }: { result: PronunciationEvaluation }) {
  const { score, feedback, words, metrics, debug } = result;
  const badge = feedbackBadge(feedback);
  const scored = result.status === "scored" && score?.total != null;
  const librosa = debug?.librosa_comparison;
  const librosaReference = librosa?.debug?.reference_pitch_contour ?? [];
  const librosaStudent = librosa?.debug?.student_pitch_contour ?? [];

  return (
    <div className="pron-result">
      <section className="pron-score" aria-label="Score">
        {result.dimensions ? (
          <ul className="pron-dimensions">
            {Object.values(result.dimensions).map((dimension) => (
              <li key={dimension.key} className={dimension.score === null ? "is-unavailable" : ""}>
                <span>{dimensionLabel(dimension.key)}</span>
                <b>{dimension.score === null ? "not assessed" : `${dimension.score} / 5`}</b>
                <p>{dimension.feedback || dimension.reason}</p>
                {dimension.key === "pronunciation" && (
                  <small>
                    {dimension.pronunciation_errors?.length ?? 0} segmental errors · {dimension.tone_errors?.length ?? 0} tone errors
                  </small>
                )}
                <details>
                  <summary>Measurements and rubric decision</summary>
                  <pre>{JSON.stringify(dimension, null, 2)}</pre>
                </details>
              </li>
            ))}
          </ul>
        ) : scored && score ? (
          <>
            <div className="pron-total">
              <strong>{score.total}</strong>
              <span>/ 100</span>
            </div>
            <ul className="pron-dimensions">
              {score.dimensions.map((dimension) => (
                <li key={dimension.key} className={dimension.points === null ? "is-unavailable" : ""}>
                  <span>{dimensionLabel(dimension.key)}</span>
                  <b>
                    {dimension.points === null ? "not measured" : `${dimension.points} / ${dimension.out_of}`}
                  </b>
                </li>
              ))}
            </ul>
            {score.renormalized && (
              <small className="pron-note">
                Out of 100 over the measured parts only. Sounds and intelligibility cannot be measured from pitch and
                timing.
              </small>
            )}
          </>
        ) : (
          <div className="pron-unscored">
            <strong>Not scored</strong>
            <span>{UNSCORABLE_TITLE[result.reason ?? ""] ?? result.reason}</span>
          </div>
        )}
      </section>

      <section className="pron-feedback" aria-label="Feedback">
        <header>
          <h3>Feedback</h3>
          <span className={`pron-badge is-${badge.tone}`}>{badge.label}</span>
        </header>
        <p>{feedback.summary}</p>
        {feedback.focus_words.length > 0 && (
          <ul>
            {feedback.focus_words.map((focus) => (
              <li key={focus.word}>
                <b lang="zh-Hant">{focus.word}</b> {focus.feedback}
              </li>
            ))}
          </ul>
        )}
        <p className="pron-tip">{feedback.practice_tip}</p>
        {feedback.adjustments && feedback.adjustments.length > 0 && (
          <small className="pron-note">Sanitised: {feedback.adjustments.join(", ")}</small>
        )}
      </section>

      {debug && (
        <section className="pron-chart-card" aria-label="Pitch comparison">
          <h3>Pitch: teacher vs student</h3>
          <ContourOverlayChart reference={debug.reference_features} student={debug.student_features} />
        </section>
      )}

      {librosa && (
        <section className="pron-chart-card" aria-label="Librosa reference comparison">
          <h3>Librosa teacher–student evidence</h3>
          {librosa.status === "scored" ? (
            <>
              {librosaReference.some(([, pitch]) => pitch !== null) && librosaStudent.some(([, pitch]) => pitch !== null) ? (
                <LibrosaPitchChart reference={librosaReference} student={librosaStudent} alignment={librosa.debug?.dtw_path} />
              ) : (
                <p className="pron-note">Pitch evidence unavailable: {librosa.reason ?? "insufficient voiced pitch"}.</p>
              )}
              <p className="pron-note">
                MFCC similarity {metricPercent(librosa.measurements.mfcc_similarity)} · pitch similarity{" "}
                {metricPercent(librosa.measurements.pitch_similarity)} · timing similarity{" "}
                {metricPercent(librosa.measurements.timing_similarity)}
              </p>
              <p className="pron-note">These similarities describe this pair of recordings; they are not pronunciation grades.</p>
            </>
          ) : (
            <p className="pron-note">Unavailable: {librosa.reason ?? "insufficient paired audio evidence"}.</p>
          )}
          <details>
            <summary>Librosa measurements</summary>
            <pre>{JSON.stringify({ status: librosa.status, reason: librosa.reason, evidence_quality: librosa.evidence_quality, parameters: librosa.parameters, measurements: librosa.measurements }, null, 2)}</pre>
          </details>
        </section>
      )}

      {words.length > 0 && (
        <section aria-label="Syllables">
          <h3>Syllables</h3>
          <div className="pron-table-wrap">
            <table className="pron-table">
              <thead>
                <tr>
                  <th>Syllable</th>
                  <th>Teacher → student</th>
                  <th>Similarity</th>
                  <th>Findings</th>
                </tr>
              </thead>
              <tbody>
                {words.map((word, index) => (
                  <tr key={`${word.word}-${index}`}>
                    <td>
                      <b lang="zh-Hant">{word.word}</b> <small>{word.pinyin}</small>
                    </td>
                    <td>
                      {shapeLabel(word.reference_shape)} → {shapeLabel(word.student_shape)}
                    </td>
                    <td>{percent(word.tone_similarity)}</td>
                    <td>
                      {word.flags.length === 0
                        ? "ok"
                        : word.flags.map((flag) => `${flagLabel(flag)} (${word.evidence})`).join("; ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="pron-note">
            Tone {percent(metrics.tone_similarity)} · rhythm {percent(metrics.rhythm_similarity)} · pauses{" "}
            {percent(metrics.pause_similarity)} · pace {percent(metrics.duration_similarity)}
          </p>
        </section>
      )}

      {debug && (
        <details className="pron-details">
          <summary>Provenance and scoring policy</summary>
          <pre>{JSON.stringify({ provenance: result.provenance ?? debug.provenance, policy: result.scoring_policy ?? debug.policy, issues: debug.issues }, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
