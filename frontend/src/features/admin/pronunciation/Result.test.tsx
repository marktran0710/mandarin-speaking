import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PronunciationEvaluation } from "@shared/api/pronunciation";
import PronunciationResult from "./Result";

vi.mock("./ContourOverlayChart", () => ({ default: () => <p>Contour chart</p> }));
vi.mock("../../../components/pitch/LibrosaPitchChart", () => ({ default: () => <p>Librosa chart</p> }));

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

const rubricResult: PronunciationEvaluation = {
  status: "scored",
  reason: null,
  dimensions: {
    pronunciation: { key: "pronunciation", score: 4, out_of: 5, source: "wav2vec2_plus_praat", rubric_level: 4, rubric_description: "Close", reason: "Measured", measurements: {}, criteria: [], pronunciation_errors: [], tone_errors: [] },
    fluency: { key: "fluency", score: 3, out_of: 5, source: "praat", rubric_level: 3, rubric_description: "Moderately fluent.", reason: "Pause fraction is limiting.", feedback: "Keep the phrase moving.", measurements: { pause_count: 4, pause_ratio: 0.21 }, criteria: [] },
    prosody: { key: "prosody", score: 4, out_of: 5, source: "praat", rubric_level: 4, rubric_description: "Minor deviations.", reason: "Pitch range is limiting.", feedback: "Follow the model's sentence movement.", measurements: { pitch_range: 5.1 }, criteria: [] },
  },
  scoring_policy: { validation_status: "uncalibrated_engineering_defaults" },
  metrics: {}, words: [],
  feedback: { summary: "Repeat after the model.", focus_words: [], practice_tip: "Practise one phrase.", source: "llm", model: "gpt-6-luna" },
  model: { scoring_version: "pronunciation-rubric-v1", acoustic_pipeline_version: "v1", feedback_model: "gpt-6-luna", feedback_source: "llm" },
  reference: { key: "story:s1:scene:0", cache_hit: true },
  debug: {
    provenance: {}, policy: { validation_status: "uncalibrated_engineering_defaults" }, issues: [], comparison: null,
    reference_features: { duration_ms: 0, syllables: [] }, student_features: null, recording_quality: null,
    librosa_comparison: {
      status: "scored", backend: "librosa",
      measurements: { mfcc_similarity: 0.91, pitch_similarity: 0.84, timing_similarity: 0.76 },
      debug: { reference_pitch_contour: [[0, 0], [1, 1]], student_pitch_contour: [[0, 0], [1, 0.8]] },
    },
  },
};

describe("PronunciationResult", () => {
  it("renders independent dimensions, calculation evidence and no total", () => {
    render(<PronunciationResult result={rubricResult} />);
    expect(screen.queryByText("84")).not.toBeInTheDocument();
    expect(screen.getByText("3 / 5")).toBeInTheDocument();
    expect(screen.getAllByText("4 / 5")).toHaveLength(2);
    expect(screen.queryByText("not assessed")).not.toBeInTheDocument();
    expect(screen.getByText("Keep the phrase moving.")).toBeInTheDocument();
    fireEvent.click(screen.getAllByText("Measurements and rubric decision")[1]);
    expect(screen.getByText(/pause_ratio": 0.21/)).toBeInTheDocument();
    expect(screen.getByText(/uncalibrated_engineering_defaults/)).toBeInTheDocument();
    expect(screen.getByText("Librosa chart")).toBeInTheDocument();
    expect(screen.getByText(/MFCC similarity 91%/)).toBeInTheDocument();
  });

  it("shows the deterministic score, evidence, and feedback provenance", () => {
    render(<PronunciationResult result={scoredResult} />);

    expect(screen.getByText("84")).toBeInTheDocument();
    expect(screen.getByText("34 / 40")).toBeInTheDocument();
    expect(screen.getByText("not measured")).toBeInTheDocument();
    expect(screen.getByText(/local feedback \(llm_timeout\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Pitch stayed flatter than the reference/)).toBeInTheDocument();
    expect(screen.getByText(/tone 81%/i)).toBeInTheDocument();
  });

  it("keeps MFCC and timing evidence visible when librosa pitch is unavailable", () => {
    render(<PronunciationResult result={{
      ...rubricResult,
      debug: {
        ...rubricResult.debug!,
        librosa_comparison: {
          status: "scored", backend: "librosa", evidence_quality: "degraded",
          reason: "insufficient_aligned_pitch",
          measurements: { mfcc_similarity: .8, pitch_similarity: null, timing_similarity: .9 },
          debug: { reference_pitch_contour: [[0, null]], student_pitch_contour: [[0, null]] },
        },
      },
    }} />);
    expect(screen.queryByText("Librosa chart")).not.toBeInTheDocument();
    expect(screen.getByText(/Pitch evidence unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/MFCC similarity 80% · pitch similarity – · timing similarity 90%/)).toBeInTheDocument();
  });

  it("shows an unavailable optional comparison without affecting the rubric", () => {
    render(<PronunciationResult result={{
      ...rubricResult,
      debug: {
        ...rubricResult.debug!,
        librosa_comparison: { status: "unavailable", backend: "librosa", reason: "feature_flag_disabled", measurements: {} },
      },
    }} />);
    expect(screen.getByText(/Unavailable: feature_flag_disabled/)).toBeInTheDocument();
    expect(screen.getByText("3 / 5")).toBeInTheDocument();
    expect(screen.queryByText("Librosa chart")).not.toBeInTheDocument();
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
