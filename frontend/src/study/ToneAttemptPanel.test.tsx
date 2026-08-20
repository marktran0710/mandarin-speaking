/**
 * Participant-output leak tests.
 *
 * These assert what the study frontend actually RENDERS, not what the backend
 * returns. A server that leaked the score would still fail here only if the
 * component displayed it — so these tests deliberately feed the component
 * hostile responses containing every forbidden field and check the rendered
 * DOM stays clean.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ToneAttemptPanel, {
  PASS_MESSAGE,
  RETRY_MESSAGE,
  TECHNICAL_MESSAGE,
} from "./ToneAttemptPanel";

/** Everything a participant must never see, in any casing. */
const FORBIDDEN = [
  "raw_score",
  "0.42274",
  "0.418",
  "probability",
  "detected_tone",
  "Tone 1",
  "Tone 2",
  "Tone 3",
  "Tone 4",
  "you produced",
  "instead of",
  "your pitch fell",
  "should rise",
  "incorrect",
  "wrong",
  "%",
  "coefficient",
  "threshold",
  "Traceback",
  "insufficient_voiced_frames",
  "sample_rate_not_native",
];

const started = { value: false };
const stopResult = {
  value: {
    blob: new Blob(["fake"], { type: "audio/wav" }),
    metadata: {
      pcm_spec_version: "STUDY_PCM16K_v1",
      capture_sample_rate: 48000,
      output_sample_rate: 16000,
      conversion: "blackman_sinc_polyphase" as const,
      input_frames: 9600,
      output_frames: 3200,
      input_duration_ms: 200,
      output_duration_ms: 200,
    },
    empty: false,
  },
};

vi.mock("./studyRecorder", async () => {
  const actual = await vi.importActual<typeof import("./studyRecorder")>(
    "./studyRecorder",
  );
  return {
    ...actual,
    StudyRecorder: class {
      async start() {
        started.value = true;
      }
      async stop() {
        return stopResult.value;
      }
    },
    submitToneAttempt: vi.fn(),
  };
});

const { submitToneAttempt } = await import("./studyRecorder");

function assertNoLeak() {
  const rendered = document.body.textContent ?? "";
  const html = document.body.innerHTML;
  for (const term of FORBIDDEN) {
    expect(rendered.toLowerCase()).not.toContain(term.toLowerCase());
    expect(html.toLowerCase()).not.toContain(term.toLowerCase());
  }
}

async function recordOnce() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /record/i }));
  await user.click(await screen.findByRole("button", { name: /stop/i }));
}

beforeEach(() => {
  started.value = false;
  stopResult.value = { ...stopResult.value, empty: false };
  vi.mocked(submitToneAttempt).mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("ToneAttemptPanel participant output", () => {
  it("renders the frozen PASS message and nothing else", async () => {
    vi.mocked(submitToneAttempt).mockResolvedValue({
      decision: "PASS",
      message: PASS_MESSAGE,
      technical_retry: false,
    });
    render(<ToneAttemptPanel expectedTone="T2" itemId="I01" prompt="話" />);
    await recordOnce();
    expect(await screen.findByText(PASS_MESSAGE)).toBeInTheDocument();
    assertNoLeak();
  });

  it("renders the frozen RETRY message and nothing else", async () => {
    vi.mocked(submitToneAttempt).mockResolvedValue({
      decision: "RETRY",
      message: RETRY_MESSAGE,
      technical_retry: false,
    });
    render(<ToneAttemptPanel expectedTone="T3" itemId="I02" prompt="馬" />);
    await recordOnce();
    expect(await screen.findByText(RETRY_MESSAGE)).toBeInTheDocument();
    assertNoLeak();
  });

  it("ignores extra fields a server might add", async () => {
    // A hostile / buggy backend response carrying every forbidden field.
    vi.mocked(submitToneAttempt).mockResolvedValue({
      decision: "PASS",
      message: PASS_MESSAGE,
      technical_retry: false,
      raw_score: 0.4180147,
      probability: 0.58,
      detected_tone: 3,
      failure_code: "insufficient_voiced_frames",
      threshold: 0.42274,
      diagnosis: "Your pitch fell — Tone 2 rises",
      traceback: "Traceback (most recent call last): ...",
    } as never);
    render(<ToneAttemptPanel expectedTone="T2" itemId="I03" prompt="電" />);
    await recordOnce();
    expect(await screen.findByText(PASS_MESSAGE)).toBeInTheDocument();
    assertNoLeak();
  });

  it("never shows a PASS message when the decision is RETRY", async () => {
    vi.mocked(submitToneAttempt).mockResolvedValue({
      decision: "RETRY",
      message: PASS_MESSAGE, // server contradicting itself
      technical_retry: false,
    });
    render(<ToneAttemptPanel expectedTone="T4" itemId="I04" prompt="快" />);
    await recordOnce();
    expect(await screen.findByText(RETRY_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByText(PASS_MESSAGE)).not.toBeInTheDocument();
  });

  it("shows a neutral technical message for an empty capture", async () => {
    stopResult.value = { ...stopResult.value, empty: true };
    render(<ToneAttemptPanel expectedTone="T2" itemId="I05" prompt="話" />);
    await recordOnce();
    expect(await screen.findByText(TECHNICAL_MESSAGE)).toBeInTheDocument();
    expect(submitToneAttempt).not.toHaveBeenCalled();
    assertNoLeak();
  });

  it("shows a neutral technical message when the request fails", async () => {
    vi.mocked(submitToneAttempt).mockRejectedValue(new Error("network down"));
    render(<ToneAttemptPanel expectedTone="T2" itemId="I06" prompt="話" />);
    await recordOnce();
    expect(await screen.findByText(TECHNICAL_MESSAGE)).toBeInTheDocument();
    assertNoLeak();
  });

  it("technical failure never implies a pronunciation error", async () => {
    stopResult.value = { ...stopResult.value, empty: true };
    render(<ToneAttemptPanel expectedTone="T2" itemId="I07" prompt="話" />);
    await recordOnce();
    const text = (await screen.findByText(TECHNICAL_MESSAGE)).textContent ?? "";
    for (const term of ["wrong", "incorrect", "tone", "pronunciation"]) {
      expect(text.toLowerCase()).not.toContain(term);
    }
  });

  it("marks the decision only in a data attribute, never as visible text", async () => {
    vi.mocked(submitToneAttempt).mockResolvedValue({
      decision: "PASS",
      message: PASS_MESSAGE,
      technical_retry: false,
    });
    render(<ToneAttemptPanel expectedTone="T2" itemId="I08" prompt="話" />);
    await recordOnce();
    const result = await screen.findByText(PASS_MESSAGE);
    expect(result.getAttribute("data-decision")).toBe("PASS");
    expect(result.textContent).toBe(PASS_MESSAGE);
  });

  it("reports the decision to the host without exposing internals", async () => {
    const onAttemptComplete = vi.fn();
    vi.mocked(submitToneAttempt).mockResolvedValue({
      decision: "RETRY",
      message: RETRY_MESSAGE,
      technical_retry: false,
    });
    render(
      <ToneAttemptPanel
        expectedTone="T2"
        itemId="I09"
        prompt="話"
        onAttemptComplete={onAttemptComplete}
      />,
    );
    await recordOnce();
    await waitFor(() => expect(onAttemptComplete).toHaveBeenCalledWith("RETRY"));
    expect(onAttemptComplete).toHaveBeenCalledTimes(1);
    expect(onAttemptComplete.mock.calls[0]).toHaveLength(1);
  });

  it("applies no duration or loudness gate of its own", async () => {
    // A 40 ms capture must still be submitted: inventing a duration rule here
    // would add a pronunciation-quality threshold that was never frozen.
    stopResult.value = {
      ...stopResult.value,
      empty: false,
      metadata: { ...stopResult.value.metadata, output_frames: 640, output_duration_ms: 40 },
    };
    vi.mocked(submitToneAttempt).mockResolvedValue({
      decision: "RETRY",
      message: RETRY_MESSAGE,
      technical_retry: true,
    });
    render(<ToneAttemptPanel expectedTone="T2" itemId="I10" prompt="話" />);
    await recordOnce();
    await waitFor(() => expect(submitToneAttempt).toHaveBeenCalledTimes(1));
  });
});
