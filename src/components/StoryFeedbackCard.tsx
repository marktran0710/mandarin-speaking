import { BiLabel } from "./BiLabel";
import type { StoryFeedback, StoryFeedbackDimension } from "../services/database";
import "./StoryFeedbackCard.css";

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

function DimensionRow({
  zh,
  en,
  dimension,
}: {
  zh: string;
  en: string;
  dimension: StoryFeedbackDimension;
}) {
  const notJudged = dimension.judged === false;
  return (
    <div
      className={`story-feedback-card ${notJudged ? "not-judged" : scoreBandClass(dimension.score)}`}
    >
      <div className="story-feedback-card-head">
        <BiLabel zh={zh} en={en} />
      </div>
      <p className="story-feedback-text">{dimension.feedback}</p>
    </div>
  );
}

export default function StoryFeedbackCard({
  feedback,
  concatenatedAudioUrl,
}: {
  feedback?: StoryFeedback | null;
  concatenatedAudioUrl?: string | null;
}) {
  if (!feedback && !concatenatedAudioUrl) return null;

  return (
    <section className="story-feedback-panel" aria-label="Story-level feedback">
      <p className="story-feedback-heading">
        <BiLabel zh="整篇故事回顧" en="Whole-story review" />
      </p>
      {concatenatedAudioUrl && (
        <audio
          className="story-feedback-audio"
          controls
          src={resolveAudioUrl(concatenatedAudioUrl)}
        />
      )}
      {feedback && (
        <div className="story-feedback-cards">
          <DimensionRow
            zh="流暢與連貫"
            en="Fluency and Coherence"
            dimension={feedback.fluency_coherence}
          />
          <DimensionRow
            zh="詞彙量"
            en="Lexical Resource"
            dimension={feedback.lexical_resource}
          />
          <DimensionRow
            zh="文法廣度與準確度"
            en="Grammatical Range and Accuracy"
            dimension={feedback.grammatical_range_accuracy}
          />
          <DimensionRow
            zh="發音"
            en="Pronunciation"
            dimension={feedback.pronunciation}
          />
        </div>
      )}
    </section>
  );
}
