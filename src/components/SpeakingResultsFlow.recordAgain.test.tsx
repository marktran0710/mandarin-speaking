import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SpeakingResultsFlow from "./SpeakingResultsFlow";
import type { PraatMetrics, Topic } from "./StoryRecorder";

/**
 * Regression: a student could reach a screen with no way to record again.
 *
 * The footer's record-again button used to live inside `{ready && (...)}`
 * together with the forward actions. Before a scene unlocked, the footer was
 * a 🔒 note and nothing else — while that same note told the student to
 * "re-record the whole sentence". The overview CTAs in the meaning / vocab /
 * pronounce-with-practice branches only move to another step, so there was no
 * escape hatch anywhere on screen.
 *
 * Re-recording is not progression. The mastery gate still decides what
 * unlocks; these tests only pin that the door is never locked from inside.
 */

// The drills record audio and call the backend; the flow only consumes their
// pass callback.
vi.mock("./WordPracticeDrill", () => ({
  default: () => <div>word-drill</div>,
}));
vi.mock("./PhrasePracticeDrill", () => ({
  default: () => <div>phrase-drill</div>,
}));
vi.mock("./RecordingPlayback", () => ({ default: () => <div>playback</div> }));

function metrics(overrides: Partial<PraatMetrics> = {}): PraatMetrics {
  return {
    transcription: "我在家",
    pitch_contour: [[0, 200]],
    word_prosody: [
      {
        token: "在家",
        index: 0,
        start_time: 0,
        end_time: 1,
        pitch_contour: [],
        mean_pitch: 200,
        pitch_range: 30,
        start_pitch: 210,
        end_pitch: 190,
        contour_shape: "falling",
        feedback: "",
        passed: false,
        judged: true,
        tone_accuracy: 40,
        shape_accuracy: 40,
        syllables: [
          { char: "在", tone: 4, score: 40, passed: false },
          { char: "家", tone: 1, score: 80, passed: true },
        ],
      },
    ],
    ...overrides,
  } as unknown as PraatMetrics;
}

function renderFlow(overrides: Record<string, unknown> = {}) {
  const onRecordAgain = vi.fn();
  render(
    <SpeakingResultsFlow
      selectedImage="/img.png"
      selectedImageIndex={0}
      totalScenes={3}
      narrativeMode={"scene" as Topic["narrativeMode"]}
      attempts={1}
      ready={false}
      masteryPassed={false}
      praatMetrics={metrics()}
      analysisAudioBlob={null}
      submittedAudioName=""
      clearedWords={[]}
      onWordDrillPass={vi.fn()}
      hasNextScene
      onNextScene={vi.fn()}
      onViewSummary={vi.fn()}
      onRecordAgain={onRecordAgain}
      {...overrides}
    />,
  );
  return { onRecordAgain };
}

function recordAgainButtons() {
  return screen
    .getAllByRole("button")
    .filter((node) => node.textContent?.includes("再錄一次"));
}

describe("SpeakingResultsFlow record-again", () => {
  it("offers a way to record again even when the scene has not unlocked", () => {
    // This is the exact dead end: not ready, words still to practise.
    const { onRecordAgain } = renderFlow({ ready: false });
    const buttons = recordAgainButtons();
    expect(buttons.length).toBeGreaterThan(0);
    expect(onRecordAgain).not.toHaveBeenCalled();
  });

  it("calls back when the footer button is pressed", async () => {
    const user = userEvent.setup();
    const { onRecordAgain } = renderFlow({ ready: false });
    const footerButton = document.querySelector(".sfc-btn-again") as HTMLElement;
    expect(footerButton).not.toBeNull();
    await user.click(footerButton);
    expect(onRecordAgain).toHaveBeenCalledTimes(1);
  });

  it("still shows the forward action only once the scene is ready", () => {
    renderFlow({ ready: true });
    expect(document.querySelector(".sfc-btn-again")).not.toBeNull();
    expect(document.querySelector(".sfc-btn-next")).not.toBeNull();
  });

  it("keeps the forward action hidden while locked", () => {
    renderFlow({ ready: false });
    expect(document.querySelector(".sfc-btn-again")).not.toBeNull();
    // The unlock rules are unchanged — only the escape hatch was added.
    expect(document.querySelector(".sfc-footer-actions .sfc-btn-next")).toBeNull();
  });
});
