import { useEffect, useMemo, useRef } from "react";
import Chart from "chart.js/auto";
import { BiLabel } from "./BiLabel";
import type { SceneSubmission, StoryFeedback, StoryFeedbackDimension } from "../services/database";
import "./StoryFeedbackCard.css";

// Resolved hex values for the app's "Tone Colors" tokens — Chart.js draws to
// a <canvas>, which can't read CSS custom properties, so these are copied
// from index.css's :root. Keep in sync if those change.
const COLOR = {
  ink: "#201d29",
  muted: "#6f697c",
  mutedSoft: "#a79eb8",
  hairline: "#f2e4ce",
  seal: "#7c3aed",
  jade: "#1c9a5b",
  jadeDeep: "#106b45",
  gold: "#ffa726",
  goldDeep: "#8a5a12",
  error: "#c81e3a",
};

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

function resolveAudioUrl(url: string): string {
  if (!url) return url;
  if (url.startsWith("/uploads/")) return `${BACKEND_URL}${url}`;
  return url;
}

function scoreBandClass(score: number): string {
  if (score >= 75) return "good";
  if (score >= 50) return "fix";
  return "next";
}

function scoreBandColor(score: number): string {
  if (score >= 75) return COLOR.jadeDeep;
  if (score >= 50) return COLOR.goldDeep;
  return COLOR.error;
}

function average(nums: number[]): number {
  return nums.length ? nums.reduce((sum, n) => sum + n, 0) / nums.length : 0;
}

interface PronunciationAxis {
  score: number;
  judged: boolean;
  detail: string;
}

/** Four pronunciation-specific measures computed straight from each scene's
 * Praat numbers — not the IELTS-style vocabulary/grammar dimensions, which
 * don't mean much once a scene can hand the student a sentence to read
 * rather than compose. Tone/Rhythm/Stress are direct scene-score averages;
 * Pausing is derived from the real pause_analysis counts (pauseCount/
 * longestPause) added alongside them, since neither Chart.js nor the radar
 * itself can show "how many times you stopped" as a percentage on its own. */
function computePronunciationProfile(scenes: SceneSubmission[]): Record<
  "tone" | "rhythm" | "stress" | "pausing",
  PronunciationAxis
> {
  const attempted = scenes.filter((s) => s.transcription.trim());
  const hasSpeech = attempted.length > 0;

  const toneAvg = average(attempted.map((s) => s.toneAccuracy));
  const rhythmAvg = average(attempted.map((s) => s.fluencyScore ?? 0));
  const stressAvg = average(attempted.map((s) => s.pronScore));

  const pauseScenes = attempted.filter((s) => s.pauseCount !== undefined);
  const pausingJudged = pauseScenes.length > 0;
  let pausingScore = 0;
  let pausingDetail = "No pause data recorded for this story.";
  if (pausingJudged) {
    const avgPauses = average(pauseScenes.map((s) => s.pauseCount ?? 0));
    const longest = Math.max(0, ...pauseScenes.map((s) => s.longestPause ?? 0));
    pausingScore = Math.max(
      0,
      Math.min(100, 100 - avgPauses * 12 - (longest >= 1.5 ? 20 : longest >= 0.8 ? 10 : 0)),
    );
    pausingDetail = `${avgPauses.toFixed(1)} pauses/scene on average, longest ${longest.toFixed(1)}s`;
  }

  return {
    tone: { score: Math.round(toneAvg), judged: hasSpeech, detail: `${Math.round(toneAvg)}% tone-contour match` },
    rhythm: { score: Math.round(rhythmAvg), judged: hasSpeech, detail: `${Math.round(rhythmAvg)}% fluency score` },
    stress: { score: Math.round(stressAvg), judged: hasSpeech, detail: `${Math.round(stressAvg)}% word-stress accuracy` },
    pausing: { score: Math.round(pausingScore), judged: pausingJudged, detail: pausingDetail },
  };
}

/** Four-axis "at a glance" pronunciation profile of the whole story, one
 * point per measure colored by its own score band — the same jade/gold/red
 * bands as the text cards below, so the shape and the cards read as one
 * system. A skewed shape (one axis pulled in) is a lot faster to spot than
 * scanning four separate percentages, which is why this sits above the
 * cards rather than replacing them — the feedback text is what actually
 * says what to do about the shape. */
function FeedbackRadarChart({ scenes }: { scenes: SceneSubmission[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);

  const dimensions = useMemo(
    () => [
      { key: "tone" as const, zh: "聲調", en: "Tone" },
      { key: "rhythm" as const, zh: "節奏", en: "Rhythm" },
      { key: "stress" as const, zh: "重音", en: "Word Stress" },
      { key: "pausing" as const, zh: "停頓", en: "Pausing" },
    ],
    [],
  );

  const profile = useMemo(() => computePronunciationProfile(scenes), [scenes]);

  useEffect(() => {
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    chartRef.current?.destroy();

    const axes = dimensions.map((d) => profile[d.key]);
    chartRef.current = new Chart(ctx, {
      type: "radar",
      data: {
        labels: dimensions.map((d) => [d.zh, d.en]),
        datasets: [
          {
            label: "Score",
            data: axes.map((a) => a.score),
            backgroundColor: "rgba(124, 58, 237, 0.14)",
            borderColor: COLOR.seal,
            borderWidth: 2,
            pointBackgroundColor: axes.map((a) => (a.judged ? scoreBandColor(a.score) : COLOR.mutedSoft)),
            pointBorderColor: "#ffffff",
            pointBorderWidth: 2,
            pointRadius: 6,
            pointHoverRadius: 8,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => {
                const d = dimensions[items[0].dataIndex];
                return `${d.zh} ${d.en}`;
              },
              label: (item) => {
                const a = axes[item.dataIndex];
                return a.judged ? a.detail : "Not enough data yet";
              },
            },
          },
        },
        scales: {
          r: {
            min: 0,
            max: 100,
            ticks: { display: false, stepSize: 25 },
            pointLabels: { font: { size: 12, weight: 600 }, color: COLOR.ink },
            grid: { color: COLOR.hairline },
            angleLines: { color: COLOR.hairline },
          },
        },
      },
    });

    return () => chartRef.current?.destroy();
  }, [profile, dimensions]);

  return (
    <div className="story-feedback-radar" role="img" aria-label="Pronunciation profile across tone, rhythm, word stress, and pausing">
      <canvas ref={canvasRef} />
    </div>
  );
}

function DimensionRow({
  zh,
  pinyin,
  en,
  dimension,
}: {
  zh: string;
  pinyin: string;
  en: string;
  dimension: StoryFeedbackDimension;
}) {
  const notJudged = dimension.judged === false;
  return (
    <div
      className={`story-feedback-card ${notJudged ? "not-judged" : scoreBandClass(dimension.score)}`}
    >
      <div className="story-feedback-card-head">
        <BiLabel zh={zh} pinyin={pinyin} en={en} />
      </div>
      <p className="story-feedback-text">{dimension.feedback}</p>
    </div>
  );
}

export default function StoryFeedbackCard({
  feedback,
  concatenatedAudioUrl,
  scenes = [],
}: {
  feedback?: StoryFeedback | null;
  concatenatedAudioUrl?: string | null;
  scenes?: SceneSubmission[];
}) {
  if (!feedback && !concatenatedAudioUrl) return null;

  return (
    <section className="story-feedback-panel" aria-label="Story-level feedback">
      <p className="story-feedback-heading">
        <BiLabel zh="整個故事回顧" pinyin="Zhěnggè gùshì huígù" en="Whole-story review" />
      </p>
      {concatenatedAudioUrl && (
        <audio
          className="story-feedback-audio"
          controls
          src={resolveAudioUrl(concatenatedAudioUrl)}
        />
      )}
      {scenes.length > 0 && <FeedbackRadarChart scenes={scenes} />}
      {feedback && (
        <div className="story-feedback-cards">
          <DimensionRow
            zh="流暢和連貫"
            pinyin="Liúchàng hé liánguàn"
            en="Fluency and Coherence"
            dimension={feedback.fluency_coherence}
          />
          <DimensionRow
            zh="詞彙量"
            pinyin="Cíhuì liàng"
            en="Lexical Resource"
            dimension={feedback.lexical_resource}
          />
          <DimensionRow
            zh="文法廣度和準確度"
            pinyin="Wénfǎ guǎngdù hé zhǔnquè dù"
            en="Grammatical Range and Accuracy"
            dimension={feedback.grammatical_range_accuracy}
          />
          <DimensionRow
            zh="發音"
            pinyin="Fāyīn"
            en="Pronunciation"
            dimension={feedback.pronunciation}
          />
        </div>
      )}
    </section>
  );
}
