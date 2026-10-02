import type { PronunciationEvaluation } from "@shared/api/pronunciation";
import "./OmpalComparison.css";

const ROWS = [
  ["Accuracy / 發音準確度", "accuracy"],
  ["Fluency / 流暢度", "fluency"],
  ["Prosody / 韻律", "prosody"],
] as const;

function score(value: number | null | undefined) {
  return value == null ? "—" : `${value.toFixed(2)} / 5`;
}

export default function OmpalComparison({ result }: { result: PronunciationEvaluation }) {
  const comparison = result.ompal_comparison;
  if (!comparison || comparison.reason === "disabled") return null;
  return (
    <section className="ompal-comparison" aria-label="OMPAL score">
      <h3>OMPAL score / OMPAL 評分</h3>
      {comparison.status === "scored" && comparison.scores ? (
        <>
          <div className="ompal-comparison__scroll">
            <table>
              <thead><tr><th scope="col">Dimension / 項目</th><th scope="col">OMPAL</th></tr></thead>
              <tbody>{ROWS.map(([label, external]) => (
                <tr key={external}><th scope="row">{label}</th><td>{score(comparison.scores?.[external])}</td></tr>
              ))}</tbody>
            </table>
          </div>
          <p>OMPAL model / 模型：{comparison.model_version}</p>
          {comparison.feedback && <p>{comparison.feedback}</p>}
          <p>OMPAL provides the speaking score on a 0–5 scale. Praat remains available below for the voice visualisation.</p>
          <p lang="zh-Hant">OMPAL 提供 0–5 分的口說評分；下方保留 Praat 聲音視覺化。</p>
        </>
      ) : <p role="status">OMPAL is temporarily unavailable. Praat visualisation and AI feedback remain available. / OMPAL 暫時無法評分，但仍可查看 Praat 視覺化與 AI 回饋。</p>}
      <p>Audio and target text are sent to the external OMPAL service. / 錄音與目標句子會傳送至外部 OMPAL 服務。</p>
    </section>
  );
}
