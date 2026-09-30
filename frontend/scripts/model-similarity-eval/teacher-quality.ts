import fs from "node:fs";
import { buildModelOverlay } from "../../src/entities/speech/modelOverlay";
import { modelSimilarity } from "../../src/entities/speech/modelSimilarity";

const data = JSON.parse(fs.readFileSync(process.env.EXPORT as string, "utf8"));
const median = (a: number[]) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
const pct = (a: number[], p: number) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };

// ---- teacher contour quality
let tokens = 0, tailJump = 0, bigRange = 0, headJump = 0;
const ranges: number[] = [], tails: number[] = [], nPoints: number[] = [];
for (const t of data.teacher) {
  for (const tok of t.contour.tokens) {
    const pts: Array<[number, number]> = tok.points;
    if (pts.length < 8) continue;
    tokens += 1;
    nPoints.push(pts.length);
    const st = pts.map((p) => p[1]);
    const n = st.length;
    const body = median(st.slice(Math.floor(n * 0.2), Math.ceil(n * 0.8)));
    const tail = median(st.slice(-Math.max(2, Math.floor(n * 0.1))));
    const head = median(st.slice(0, Math.max(2, Math.floor(n * 0.1))));
    tails.push(tail - body);
    if (Math.abs(tail - body) > 8) tailJump += 1;
    if (Math.abs(head - body) > 8) headJump += 1;
    const range = pct(st, 0.9) - pct(st, 0.1);
    ranges.push(range);
    if (range > 12) bigRange += 1;
  }
}
console.log(`TEACHER tokens=${tokens} points/token median=${median(nPoints)}`);
console.log(`  range p90-p10 (st): p25=${pct(ranges, .25).toFixed(1)} median=${median(ranges).toFixed(1)} p75=${pct(ranges, .75).toFixed(1)} p95=${pct(ranges, .95).toFixed(1)}; >12st: ${bigRange} (${(100 * bigRange / tokens).toFixed(0)}%)`);
console.log(`  tail-vs-body |Δ|>8st: ${tailJump} (${(100 * tailJump / tokens).toFixed(0)}%); head-vs-body |Δ|>8st: ${headJump} (${(100 * headJump / tokens).toFixed(0)}%); tail Δ p5=${pct(tails, .05).toFixed(1)} median=${median(tails).toFixed(1)} p95=${pct(tails, .95).toFixed(1)}`);

// ---- real attempts through the REAL production scorer
let scored = 0, nullScores = 0, status: Record<string, number> = {};
const scores: number[] = [], rs: number[] = [];
for (const a of data.attempts) {
  const contour = data.teacher.find((t: any) => t.story === a.story && t.frame === a.frame)?.contour;
  const words = a.words.filter((w: any) => w.start_time != null && w.end_time != null).map((w: any) => ({ token: w.token, index: w.index, start_time: w.start_time, end_time: w.end_time }));
  const overlay = buildModelOverlay({ contour, targetScript: contour?.text ?? "", transcript: a.transcript, words, pitchContour: a.pitchContour });
  status[overlay.status] = (status[overlay.status] ?? 0) + 1;
  const sim = modelSimilarity(overlay, a.pitchContour);
  if (!sim) nullScores += 1; else { scored += 1; scores.push(sim.score); rs.push(sim.r); }
}
console.log(`\nREAL attempts=${data.attempts.length} overlay=${JSON.stringify(status)} scored=${scored} null=${nullScores}`);
console.log(`  production score: p10=${pct(scores, .1)} p25=${pct(scores, .25)} median=${median(scores)} p75=${pct(scores, .75)} p90=${pct(scores, .9)} mean=${(scores.reduce((s, v) => s + v, 0) / scores.length).toFixed(1)}`);
