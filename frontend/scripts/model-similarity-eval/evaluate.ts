import fs from "node:fs";
import { buildModelOverlay } from "../../src/entities/speech/modelOverlay";
import { modelSimilarity } from "../../src/entities/speech/modelSimilarity";

const data = JSON.parse(fs.readFileSync(process.env.EXPORT as string, "utf8"));

// deterministic RNG
let seed = 20260930;
const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
const uni = (a: number, b: number) => a + (b - a) * rand();
const normal = (sd: number) => { let u = 0, v = 0; while (u === 0) u = rand(); v = rand(); return sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
const median = (a: number[]) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
const pct = (a: number[], p: number) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };

type Pts = Array<[number, number]>;
interface Tok { token: string; points: Pts }
const frames: Array<{ text: string; tokens: Tok[] }> = data.teacher
  .map((t: any) => ({ text: t.contour.text, tokens: t.contour.tokens.filter((k: Tok) => k.points.length >= 8 && /[一-鿿]/u.test(k.token)) }))
  .filter((f: any) => f.tokens.length >= 2);
const allTokens: Tok[] = frames.flatMap((f) => f.tokens);

function at(points: Pts, t: number): number {
  for (let i = 1; i < points.length; i += 1) {
    if (t <= points[i][0]) { const [t0, v0] = points[i - 1]; const [t1, v1] = points[i]; return t1 === t0 ? v0 : v0 + ((t - t0) / (t1 - t0)) * (v1 - v0); }
  }
  return points[points.length - 1][1];
}
const med = (v: number[]) => median(v);

type Kind = "positive" | "flat x0.1" | "half x0.4" | "narrow x0.6 (ambiguous)" | "mirrored" | "reversed" | "other words" | "random walk" | "delayed 35% (ambiguous)";
const KINDS: Kind[] = ["positive", "flat x0.1", "half x0.4", "narrow x0.6 (ambiguous)", "mirrored", "reversed", "other words", "random walk", "delayed 35% (ambiguous)"];

function shapeFor(kind: Kind, tok: Tok): (t: number) => number {
  const body = tok.points.map((p) => p[1]);
  const m = med(body);
  const centred: Pts = tok.points.map(([t, v]) => [t, v - m]);
  switch (kind) {
    case "positive": {
      const d = uni(-0.15, 0.15); const scale = uni(0.75, 1.25);
      return (t) => scale * at(centred, Math.min(1, Math.max(0, t + (d * Math.sin(2 * Math.PI * t)) / (2 * Math.PI))));
    }
    case "flat x0.1": return (t) => 0.1 * at(centred, t);
    case "half x0.4": return (t) => 0.4 * at(centred, t);
    case "narrow x0.6 (ambiguous)": return (t) => 0.6 * at(centred, t);
    case "mirrored": return (t) => -at(centred, t);
    case "reversed": return (t) => at(centred, 1 - t);
    case "other words": {
      let other = allTokens[Math.floor(rand() * allTokens.length)];
      const om = med(other.points.map((p) => p[1]));
      const oc: Pts = other.points.map(([t, v]) => [t, v - om]);
      return (t) => at(oc, t);
    }
    case "random walk": {
      const steps = Array.from({ length: 24 }, () => normal(1)); let acc = 0; const walk = steps.map((s) => (acc += s));
      const range = Math.max(...walk) - Math.min(...walk) || 1;
      return (t) => (walk[Math.min(23, Math.floor(t * 23.999))] / range) * 3;
    }
    case "delayed 35% (ambiguous)": return (t) => at(centred, Math.max(0, (t - 0.35) / 0.65));
  }
}

function attempt(frame: { text: string; tokens: Tok[] }, kind: Kind, octaveErrors: boolean) {
  const base = [110, 150, 220][Math.floor(rand() * 3)];
  const level = uni(-2, 2);
  const words: any[] = []; const pitch: Pts = [];
  let clock = 0.1;
  frame.tokens.forEach((tok, index) => {
    const dur = uni(0.18, 0.5); const start = clock; const end = clock + dur; clock = end + 0.02;
    words.push({ token: tok.token, index, start_time: start, end_time: end });
    const shape = shapeFor(kind, tok);
    const n = Math.round(dur / 0.01);
    const tokenOffset = med(tok.points.map((p) => p[1]));
    const octaveBlock = octaveErrors && rand() < 0.25 ? { from: uni(0.5, 0.8), dir: rand() < 0.5 ? -12 : 12 } : null;
    for (let i = 0; i <= n; i += 1) {
      if (rand() < 0.04) continue;
      const t = i / n;
      let st = tokenOffset + level + shape(t) + normal(0.35);
      if (octaveBlock && t >= octaveBlock.from) st += octaveBlock.dir;
      pitch.push([start + t * dur, base * 2 ** (st / 12)]);
    }
  });
  return { words, pitch, contour: { text: frame.text, tokens: frame.tokens } };
}

function score(a: ReturnType<typeof attempt>, opts: Parameters<typeof modelSimilarity>[2]): number | null {
  const overlay = buildModelOverlay({ contour: a.contour, targetScript: a.contour.text, words: a.words, pitchContour: a.pitch });
  return modelSimilarity(overlay, a.pitch, opts)?.score ?? null;
}

function auc(pos: number[], neg: number[]): number {
  let wins = 0;
  for (const p of pos) for (const n of neg) wins += p > n ? 1 : p === n ? 0.5 : 0;
  return wins / (pos.length * neg.length);
}

// ---- build a fixed set of synthetic attempts once, reuse for every candidate
const REPS = Number(process.env.REPS ?? 8);
const octaveErrors = process.env.OCTAVE === "1";
const set: Record<string, Array<ReturnType<typeof attempt>>> = {};
for (const kind of KINDS) {
  set[kind] = [];
  for (const f of frames) for (let r = 0; r < REPS; r += 1) set[kind].push(attempt(f, kind, octaveErrors));
}

interface Candidate { name: string; opts: Parameters<typeof modelSimilarity>[2] }
const candidates: Candidate[] = JSON.parse(process.env.CANDIDATES ?? "null") ?? [
  { name: "legacy", opts: { algorithm: "legacy" } },
  { name: "v2 default", opts: { algorithm: "v2" } },
];

const results: Record<string, Record<string, number[]>> = {};
for (const c of candidates) {
  results[c.name] = {};
  for (const kind of KINDS) results[c.name][kind] = set[kind].map((a) => score(a, c.opts)).filter((v): v is number => v !== null);
}

const HARD_NEG = ["flat x0.1", "half x0.4", "mirrored", "reversed", "other words", "random walk"];
if (process.env.COMPACT === "1") {
  console.log("candidate | AUC6 | pos p10/med | other med | half AUC | half med | narrow0.6 med | flat med");
  for (const c of candidates) {
    const r = results[c.name];
    const a6 = auc(r.positive, HARD_NEG.flatMap((k) => r[k]));
    console.log(`${c.name} | ${a6.toFixed(3)} | ${pct(r.positive, .1)}/${median(r.positive)} | ${median(r["other words"])} | ${auc(r.positive, r["half x0.4"]).toFixed(3)} | ${median(r["half x0.4"])} | ${median(r["narrow x0.6 (ambiguous)"])} | ${median(r["flat x0.1"])}`);
  }
  process.exit(0);
}
console.log(`attempts per class=${set.positive.length} (octave errors injected: ${octaveErrors})\n`);
console.log("### AUC (positive vs degraded)\n");
console.log("| degraded | " + candidates.map((c) => c.name).join(" | ") + " |");
console.log("|---|" + candidates.map(() => "---|").join(""));
for (const k of [...HARD_NEG, "narrow x0.6 (ambiguous)", "delayed 35% (ambiguous)"]) {
  console.log(`| ${k} | ` + candidates.map((c) => auc(results[c.name].positive, results[c.name][k]).toFixed(3)).join(" | ") + " |");
}
console.log("| **overall (first six)** | " + candidates.map((c) => `**${auc(results[c.name].positive, HARD_NEG.flatMap((k) => results[c.name][k])).toFixed(3)}**`).join(" | ") + " |");
console.log("\n### Score distribution (what a student would see)\n");
console.log("| class | " + candidates.map((c) => `${c.name} (p10/median/p90)`).join(" | ") + " |");
console.log("|---|" + candidates.map(() => "---|").join(""));
for (const k of KINDS) {
  console.log(`| ${k} | ` + candidates.map((c) => { const v = results[c.name][k]; return `${pct(v, .1)}/${median(v)}/${pct(v, .9)}`; }).join(" | ") + " |");
}
