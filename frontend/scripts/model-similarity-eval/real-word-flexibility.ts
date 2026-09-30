import fs from "node:fs";
import { foldOctaveBlocks } from "../../src/entities/speech/pitchCleaning";

const data = JSON.parse(fs.readFileSync(process.env.EXPORT as string, "utf8"));
type Pt = [number, number];
const median = (a: number[]) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
const mean = (a: number[]) => a.reduce((s, v) => s + v, 0) / a.length;
const pct = (a: number[], p: number) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };
let seed = 7; const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };

const st = (hz: number) => 12 * Math.log2(hz / 100);
function interp(points: Pt[], t: number, maxGap = Infinity): number | null {
  for (let i = 1; i < points.length; i += 1) {
    const [t0, v0] = points[i - 1]; const [t1, v1] = points[i];
    if (t >= t0 && t <= t1) { if (t1 - t0 > maxGap) return null; return t1 === t0 ? v0 : v0 + ((t - t0) / (t1 - t0)) * (v1 - v0); }
  }
  return null;
}
function pearson(x: number[], y: number[]) {
  const n = x.length, mx = mean(x), my = mean(y); let c = 0, vx = 0, vy = 0;
  for (let i = 0; i < n; i += 1) { c += (x[i] - mx) * (y[i] - my); vx += (x[i] - mx) ** 2; vy += (y[i] - my) ** 2; }
  return vx < 1e-9 || vy < 1e-9 ? 0 : c / Math.sqrt(vx * vy);
}
const ranks = (a: number[]) => { const idx = a.map((v, i) => [v, i]).sort((x, y) => x[0] - y[0]); const r = new Array(a.length); idx.forEach(([, i], k) => { r[i] = k; }); return r; };
const spearman = (x: number[], y: number[]) => pearson(ranks(x), ranks(y));
const smooth = (v: number[], w: number) => v.map((_, i) => mean(v.slice(Math.max(0, i - w), i + w + 1)));
const range = (v: number[]) => Math.max(...v) - Math.min(...v);
function auc(pos: number[], neg: number[]) { let w = 0; for (const p of pos) for (const n of neg) w += p > n ? 1 : p === n ? 0.5 : 0; return w / (pos.length * neg.length); }

interface Word { token: string; syl: number; start: number; end: number; learner: Pt[]; model: Pt[]; frame: string }
const words: Word[] = [];
for (const a of data.attempts) {
  const tf = data.teacher.find((t: any) => t.story === a.story && t.frame === a.frame)?.contour;
  if (!tf) continue;
  const voicedRaw: Pt[] = a.pitchContour.filter((p: Pt) => p[1] > 0);
  if (voicedRaw.length < 5) continue;
  const folded = foldOctaveBlocks(voicedRaw.map((p) => st(p[1])));
  const learner: Pt[] = voicedRaw.map((p, i) => [p[0], folded[i]]);
  const used = new Set<number>();
  for (const w of a.words) {
    if (w.start_time == null || w.end_time == null) continue;
    const mi = tf.tokens.findIndex((t: any, i: number) => !used.has(i) && t.token === w.token && t.points.length >= 8);
    if (mi < 0) continue; used.add(mi);
    const mp: Pt[] = tf.tokens[mi].points as Pt[];
    const model: Pt[] = mp.map((p, i) => [p[0], foldOctaveBlocks(mp.map((q) => q[1]))[i]] as Pt);
    words.push({ token: w.token, syl: Array.from(w.token).filter((c: string) => /[一-鿿]/u.test(c)).length, start: w.start_time, end: w.end_time, learner, model, frame: `${a.story}#${a.frame}` });
  }
}
console.log(`matched real words=${words.length} distinct recordings-frames=${new Set(words.map((w) => w.frame)).size} distinct tokens=${new Set(words.map((w) => w.token)).size}`);

function samples(w: Word, model: Pt[], shift: number, n = 20) {
  const span = w.end - w.start; const s: number[] = [], m: number[] = [];
  const mm: Pt[] = model.map(([t, v]) => [w.start + t * span, v]);
  for (let i = 0; i < n; i += 1) {
    const t = w.start + ((i + 0.5) / n) * span;
    const a = interp(w.learner, t + shift * span, 0.1); const b = interp(mm, t);
    if (a !== null && b !== null) { s.push(a); m.push(b); }
  }
  return s.length >= n / 2 ? { s, m } : null;
}
const SH = (max: number) => { const out: number[] = []; for (let x = -max; x <= max + 1e-9; x += 0.05) out.push(Number(x.toFixed(2))); return out; };

type Scorer = (w: Word, model: Pt[]) => number | null;
const bestOver = (shifts: number[], f: (s: number[], m: number[]) => number): Scorer => (w, model) => {
  let best: number | null = null;
  for (const sh of shifts) { const p = samples(w, model, sh); if (!p) continue; if (range(p.m) < 1) return null; const v = f(p.s, p.m); if (best === null || v > best) best = v; }
  return best;
};
// coarse "tone letter" agreement: K segments, direction of each step (flat if |step| < thr st)
const signAgree = (K: number, thr: number) => (s: number[], m: number[]) => {
  const seg = (v: number[]) => Array.from({ length: K }, (_, k) => mean(v.slice(Math.floor((k * v.length) / K), Math.floor(((k + 1) * v.length) / K) || 1)));
  const a = seg(s), b = seg(m); let agree = 0, tot = 0;
  for (let k = 1; k < K; k += 1) {
    const da = a[k] - a[k - 1], db = b[k] - b[k - 1];
    const sa = Math.abs(da) < thr ? 0 : Math.sign(da), sb = Math.abs(db) < thr ? 0 : Math.sign(db);
    tot += 1; agree += sa === sb ? 1 : (sa === 0 || sb === 0) ? 0.4 : 0;
  }
  return agree / tot;
};
const scorers: Record<string, Scorer> = {
  "A base Pearson, shifts +-0.15": bestOver(SH(0.15), pearson),
  "B Pearson, shifts +-0.30": bestOver(SH(0.3), pearson),
  "C Pearson, smoothed(2), +-0.15": bestOver(SH(0.15), (s, m) => pearson(smooth(s, 2), smooth(m, 2))),
  "D Spearman, +-0.15": bestOver(SH(0.15), spearman),
  "E sign-agreement K=4 thr1st": bestOver(SH(0.15), signAgree(4, 1)),
  "F sign-agreement K=5 thr1.5st": bestOver(SH(0.15), signAgree(5, 1.5)),
  "G mean(Pearson+, sign K=4)": bestOver(SH(0.15), (s, m) => (Math.max(0, pearson(s, m)) + signAgree(4, 1)(s, m)) / 2),
  "H Pearson on smoothed, +-0.30": bestOver(SH(0.3), (s, m) => pearson(smooth(s, 2), smooth(m, 2))),
};

// multi-anchor warp: one free breakpoint per syllable boundary (timing differs between speakers INSIDE a word)
function warpedSamples(w: Word, model: Pt[], deltas: number[], n = 20) {
  const span = w.end - w.start; const syl = Math.max(1, w.syl);
  const knots = [0, ...deltas.map((d, k) => Math.min(0.95, Math.max(0.05, (k + 1) / syl + d))), 1];
  const s: number[] = [], m: number[] = [];
  const mm: Pt[] = model.map(([t, v]) => [w.start + t * span, v]);
  for (let i = 0; i < n; i += 1) {
    const u = (i + 0.5) / n; // model relative time
    // map model-time u (breakpoints at k/syl) onto learner-time via the piecewise-linear knots
    const seg = Math.min(syl - 1, Math.floor(u * syl)); const f = u * syl - seg;
    const learnerRel = knots[seg] + f * (knots[seg + 1] - knots[seg]);
    const a = interp(w.learner, w.start + learnerRel * span, 0.1); const b = interp(mm, w.start + u * span);
    if (a !== null && b !== null) { s.push(a); m.push(b); }
  }
  return s.length >= n / 2 ? { s, m } : null;
}
function gridDeltas(count: number, step: number, max: number): number[][] {
  const vals: number[] = []; for (let x = -max; x <= max + 1e-9; x += step) vals.push(Number(x.toFixed(2)));
  let out: number[][] = [[]]; for (let k = 0; k < count; k += 1) out = out.flatMap((p) => vals.map((v) => [...p, v]));
  return out;
}
const syllableAware = (max: number): Scorer => (w, model) => {
  if (w.syl < 2) return bestOver(SH(0.15), pearson)(w, model);
  let best: number | null = null;
  for (const d of gridDeltas(Math.min(w.syl - 1, 3), 0.05, max)) {
    // also allow a small global shift by shifting all breakpoints equally is covered by the grid
    const p = warpedSamples(w, model, d); if (!p) continue; if (range(p.m) < 1) return null;
    const v = pearson(p.s, p.m); if (best === null || v > best) best = v;
  }
  return best;
};
scorers["I syllable-aware warp (+-0.15/breakpoint)"] = syllableAware(0.15);
scorers["J syllable-aware warp (+-0.25/breakpoint)"] = syllableAware(0.25);
// chance-corrected: subtract this word's own chance level (learner window vs random smooth curves)
function randomCurve(n: number): Pt[] { const k = 4; const c = Array.from({ length: k }, () => (rand() - 0.5) * 10); return Array.from({ length: 24 }, (_, i) => [i / 23, c[Math.min(k - 1, Math.floor((i / 23) * k))] + (rand() - 0.5) * 2] as Pt); }
const chanceCache = new Map<Word, number>();
const chanceOf = (w: Word) => { let c = chanceCache.get(w); if (c === undefined) { const vals: number[] = []; for (let i = 0; i < 25; i += 1) { const v = bestOver(SH(0.15), pearson)(w, randomCurve(24)); if (v !== null) vals.push(v); } c = vals.length ? median(vals) : 0.4; chanceCache.set(w, c); } return c; };
scorers["K chance-corrected Pearson (per word)"] = (w, model) => { const v = bestOver(SH(0.15), pearson)(w, model); if (v === null) return null; const c = chanceOf(w); return (v - c) / (1 - c); };

// matched vs mismatched control (different teacher word, same syllable count, other frame)
const pool = words;
console.log("\n| variant | matched median | mismatched median | mismatched p90 | AUC(matched>mismatched) | share matched >=0.7 |");
console.log("|---|---|---|---|---|---|");
for (const [name, sc] of Object.entries(scorers)) {
  const matched: number[] = [], mism: number[] = [];
  for (const w of words) {
    const v = sc(w, w.model); if (v === null) continue; matched.push(Math.max(0, v));
    for (let k = 0; k < 6; k += 1) {
      const other = pool[Math.floor(rand() * pool.length)];
      if (other.token === w.token || other.syl !== w.syl) { k -= 0; continue; }
      const u = sc(w, other.model); if (u !== null) mism.push(Math.max(0, u));
    }
  }
  console.log(`| ${name} | ${median(matched).toFixed(2)} | ${median(mism).toFixed(2)} | ${pct(mism, .9).toFixed(2)} | ${auc(matched, mism).toFixed(3)} | ${(100 * matched.filter((v) => v >= 0.7).length / matched.length).toFixed(0)}% |`);
}

// why is r low? break the base Pearson down by word properties
const base = scorers["A base Pearson, shifts +-0.15"];
const rows = words.map((w) => ({ w, r: base(w, w.model), dur: w.end - w.start, mrange: range(w.model.map((p) => p[1])) })).filter((x) => x.r !== null) as Array<{ w: Word; r: number; dur: number; mrange: number }>;
const grp = (name: string, pick: (x: (typeof rows)[number]) => boolean) => { const g = rows.filter(pick).map((x) => Math.max(0, x.r)); console.log(`  ${name}: n=${g.length} median r=${g.length ? median(g).toFixed(2) : "-"}`); };
console.log("\nbase Pearson r by word property:");
grp("1 syllable", (x) => x.w.syl === 1); grp("2 syllables", (x) => x.w.syl === 2); grp("3+ syllables", (x) => x.w.syl >= 3);
grp("duration < 0.25s", (x) => x.dur < 0.25); grp("0.25-0.45s", (x) => x.dur >= 0.25 && x.dur < 0.45); grp("> 0.45s", (x) => x.dur >= 0.45);
grp("model range < 4st", (x) => x.mrange < 4); grp("4-8 st", (x) => x.mrange >= 4 && x.mrange < 8); grp("> 8 st", (x) => x.mrange >= 8);
