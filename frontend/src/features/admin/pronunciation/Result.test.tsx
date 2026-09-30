import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PronunciationEvaluation } from "@shared/api/pronunciation";
import PronunciationResult from "./Result";

vi.mock("./ContourOverlayChart", () => ({ default: () => <p>Contour chart</p> }));

const scoredResult: PronunciationEvaluation = {
  status: "scored",
  reason: null,
  score: {
    total: 84,
    renormalized: true,
    dimensions: [
      { key: "tone", basis: "measured", points: 34, out_of: 40, note: "Measured from normalized pitch." },
      { key: "segmental", basis: "unavailable", points: null, out_of: null, note: "Not measured." },
    ],
  },
  metrics: { tone_similarity: 0.81, rhythm_similarity: 0.87, duration_similarity: 0.78, pause_similarity: 0.91 },
  words: [{
    word: "有",
    pinyin: "you3",
    expected_tone: 3,
    tone_similarity: 0.73,
    reference_shape: "dip",
    student_shape: "flat",
    duration_ratio: 0.74,
    evidence: "moderate",
    flags: ["tone_contour_too_flat"],
  }],
  feedback: {
    summary: "Your pronunciation was clear overall.",
    focus_words: [{ word: "有", feedback: "Let the pitch dip more clearly." }],
    practice_tip: "Repeat 有 slowly, then in the sentence.",
    source: "local",
    fallback_reason: "llm_timeout",
  },
  model: {
    scoring_version: "pronunciation-score-v1",
    acoustic_pipeline_version: "pronunciation-features-v1",
    feedback_model: null,
    feedback_source: "local",
  },
  reference: { key: "story:s1:scene:0", cache_hit: true },
};

describe("PronunciationResult", () => {
  it("shows the deterministic score, evidence, and feedback provenance", () => {
    render(<PronunciationResult result={scoredResult} />);

    expect(screen.getByText("84")).toBeInTheDocument();
    expect(screen.getByText("34 / 40")).toBeInTheDocument();
    expect(screen.getByText("not measured")).toBeInTheDocument();
    expect(screen.getByText(/local feedback \(llm_timeout\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Pitch stayed flatter than the reference/)).toBeInTheDocument();
    expect(screen.getByText(/tone 81%/i)).toBeInTheDocument();
  });

  it("explains why an unusable recording has no score", () => {
    render(<PronunciationResult result={{
      ...scoredResult,
      status: "unscorable",
      reason: "no_voiced_speech",
      score: { total: null, renormalized: false, dimensions: [] },
      words: [],
    }} />);

    expect(screen.getByText("Not scored")).toBeInTheDocument();
    expect(screen.getByText("No speech pitch could be measured")).toBeInTheDocument();
  });
});
