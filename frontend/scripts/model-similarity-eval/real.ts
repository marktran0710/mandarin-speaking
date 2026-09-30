import fs from "node:fs";
import { buildModelOverlay } from "../../src/entities/speech/modelOverlay";
import { modelSimilarity } from "../../src/entities/speech/modelSimilarity";
import { foldOctaveBlocks } from "../../src/entities/speech/pitchCleaning";

const data = JSON.parse(fs.readFileSync(process.env.EXPORT as string, "utf8"));
const median = (a: number[]) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
const pct = (a: number[], p: number) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };

// how much of the teacher data does octave cleaning touch?
let tokens = 0, changed = 0, spanBefore: number[] = [], spanAfter: number[] = [];
const span = (v: number[]) => pct(v, 0.9) - pct(v, 0.1);
for (const t of data.teacher) for (const tok of t.contour.tokens) {
  if (tok.points.length < 8) continue;
  tokens += 1;
  const st = tok.points.map((p: number[]) => p[1]);
  const fixed = foldOctaveBlocks(st);
  if (fixed.some((v, i) => v !== st[i])) changed += 1;
  spanBefore.push(span(st)); spanAfter.push(span(fixed));
}
console.log(`teacher tokens=${tokens}; tokens with octave-folded points=${changed} (${(100 * changed / tokens).toFixed(0)}%)`);
console.log(`  teacher pitch range p90-p10 (st) median: before ${median(spanBefore).toFixed(1)} -> after ${median(spanAfter).toFixed(1)}; p75 ${pct(spanBefore, .75).toFixed(1)} -> ${pct(spanAfter, .75).toFixed(1)}; >12st ${spanBefore.filter((v) => v > 12).length} -> ${spanAfter.filter((v) => v > 12).length}`);

// real learner attempts (all from ONE student)
const rows: Array<{ id: string; legacy: number; v2: number; shape: number; range: number; words: number }> = [];
for (const a of data.attempts) {
  const contour = data.teacher.find((t: any) => t.story === a.story && t.frame === a.frame)?.contour;
  const words = a.words.filter((w: any) => w.start_time != null && w.end_time != null).map((w: any) => ({ token: w.token, index: w.index, start_time: w.start_time, end_time: w.end_time }));
  const overlay = buildModelOverlay({ contour, targetScript: contour?.text ?? "", transcript: a.transcript, words, pitchContour: a.pitchContour });
  const legacy = modelSimilarity(overlay, a.pitchContour, { algorithm: "legacy" });
  const v2 = modelSimilarity(overlay, a.pitchContour, { algorithm: "v2" });
  if (legacy && v2) rows.push({ id: a.id.slice(0, 8), legacy: legacy.score, v2: v2.score, shape: v2.shape!, range: v2.range!, words: v2.wordsCompared });
}
const L = rows.map((r) => r.legacy), V = rows.map((r) => r.v2);
console.log(`\nreal scored attempts=${rows.length} (of ${data.attempts.length}; the rest have a script/word mismatch so no score is shown)`);
console.log(`  legacy: p10=${pct(L, .1)} median=${median(L)} p90=${pct(L, .9)} mean=${(L.reduce((s, v) => s + v, 0) / L.length).toFixed(1)}`);
console.log(`  v2    : p10=${pct(V, .1)} median=${median(V)} p90=${pct(V, .9)} mean=${(V.reduce((s, v) => s + v, 0) / V.length).toFixed(1)}`);
console.log(`  mean shape factor=${(rows.reduce((s, r) => s + r.shape, 0) / rows.length).toFixed(2)}  mean range factor=${(rows.reduce((s, r) => s + r.range, 0) / rows.length).toFixed(2)}`);
const ranks = (a: number[]) => { const idx = a.map((v, i) => [v, i]).sort((x, y) => x[0] - y[0]); const r = new Array(a.length); idx.forEach(([, i], k) => { r[i] = k; }); return r; };
const rl = ranks(L), rv = ranks(V); const n = rows.length;
const mean = (a: number[]) => a.reduce((s, v) => s + v, 0) / a.length;
const ml = mean(rl), mv = mean(rv);
const rho = rl.reduce((s, v, i) => s + (v - ml) * (rv[i] - mv), 0) / Math.sqrt(rl.reduce((s, v) => s + (v - ml) ** 2, 0) * rv.reduce((s, v) => s + (v - mv) ** 2, 0));
console.log(`  Spearman legacy vs v2 = ${rho.toFixed(2)}; v2 lower than legacy in ${rows.filter((r) => r.v2 < r.legacy).length}/${n} attempts, higher in ${rows.filter((r) => r.v2 > r.legacy).length}`);
console.log("\n  distinct recordings (id): legacy -> v2 [shape/range factors]");
for (const r of rows.filter((r, i, arr) => arr.findIndex((x) => x.id === r.id) === i).slice(0, 12)) console.log(`   ${r.id}: ${r.legacy} -> ${r.v2}  [shape ${r.shape.toFixed(2)} / range ${r.range.toFixed(2)}] words=${r.words}`);
