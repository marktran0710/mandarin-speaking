import type { PronunciationEvaluation } from "@shared/api/pronunciation";
import "./OmpalComparison.css";

const ROWS = [
  ["Accuracy / 發音準確度", "pronunciation", "accuracy"],
  ["Fluency / 流暢度", "fluency", "fluency"],
  ["Prosody / 韻律", "prosody", "prosody"],
] as const;

function score(value: number | null | undefined) {
  return value == null ? "—" : `${value.toFixed(2)} / 5`;
}

export default function OmpalComparison({ result }: { result: PronunciationEvaluation }) {
  const comparison = result.ompal_comparison;
  if (!comparison || comparison.reason === "disabled") return null;
  return (
    <section className="ompal-comparison" aria-label="OMPAL comparison">
      <h3>OMPAL comparison / OMPAL 評分比較</h3>
      {comparison.status === "scored" && comparison.scores ? (
        <>
          <div className="ompal-comparison__scroll">
            <table>
              <thead><tr><th scope="col">Dimension / 項目</th><th scope="col">Current / 本系統</th><th scope="col">OMPAL</th></tr></thead>
              <tbody>{ROWS.map(([label, local, external]) => (
                <tr key={external}><th scope="row">{label}</th><td>{score(result.dimensions?.[local]?.score)}</td><td>{score(comparison.scores?.[external])}</td></tr>
              ))}</tbody>
            </table>
          </div>
          <p>OMPAL model / 模型：{comparison.model_version}</p>
          {comparison.feedback && <p>{comparison.feedback}</p>}
          <p>Two independent estimates; OMPAL accuracy is compared with our pronunciation score. OMPAL uses 0–5; our rubric uses 1–5. These comparison scores do not change your progress.</p>
          <p lang="zh-Hant">兩種獨立評分：OMPAL 準確度對照本系統發音分數。OMPAL 為 0–5 分，本系統為 1–5 分；比較分數不影響學習進度。</p>
        </>
      ) : <p role="status">OMPAL is temporarily unavailable. Your current scores are still available. / OMPAL 暫時無法評分，本系統分數仍可查看。</p>}
      <p>Audio and target text are sent to the external OMPAL service. / 錄音與目標句子會傳送至外部 OMPAL 服務。</p>
    </section>
  );
}
