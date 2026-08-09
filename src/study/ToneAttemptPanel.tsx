/**
 * Participant-facing panel for one tone-confirmation attempt.
 *
 * This is the only component the study participant sees for the experimental
 * output. It renders exactly two things: the frozen decision and its frozen
 * message. It never receives, stores or renders the internal score, the
 * probability, a detected tone, a threshold, a failure code or an exception.
 *
 * The only UI gate is technical: did the capture produce audio at all? There is
 * deliberately no duration or loudness threshold here — inventing one would add
 * a pronunciation-quality rule that was never frozen scientifically.
 */

import { useCallback, useRef, useState } from "react";

import { StudyRecorder, submitToneAttempt, type ToneAttemptResponse } from "./studyRecorder";

/** Frozen learner-facing strings. Must match the backend constants exactly. */
export const PASS_MESSAGE = "Your tone sounds acceptable. You can continue.";
export const RETRY_MESSAGE =
  "I'm not confident enough to confirm this attempt. Please try once more.";
export const TECHNICAL_MESSAGE =
  "The recording could not be processed. Please record again.";

export interface ToneAttemptPanelProps {
  /** "T1" | "T2" | "T3" | "T4" — validated again on the server. */
  expectedTone: string;
  itemId: string;
  /** The character the participant is asked to say. */
  prompt: string;
  pinyin?: string;
  onAttemptComplete?: (decision: "PASS" | "RETRY") => void;
}

type PanelState = "idle" | "recording" | "submitting" | "answered";

export default function ToneAttemptPanel({
  expectedTone,
  itemId,
  prompt,
  pinyin,
  onAttemptComplete,
}: ToneAttemptPanelProps) {
  const recorderRef = useRef<StudyRecorder | null>(null);
  const [state, setState] = useState<PanelState>("idle");
  const [result, setResult] = useState<ToneAttemptResponse | null>(null);

  const beginRecording = useCallback(async () => {
    setResult(null);
    const recorder = new StudyRecorder();
    recorderRef.current = recorder;
    try {
      await recorder.start();
      setState("recording");
    } catch {
      // Microphone refused or unavailable: a technical failure, never a
      // statement about the participant's pronunciation.
      setResult({
        decision: "RETRY",
        message: TECHNICAL_MESSAGE,
        technical_retry: true,
      });
      setState("answered");
    }
  }, []);

  const finishRecording = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;
    setState("submitting");
    try {
      const recording = await recorder.stop();
      if (recording.empty) {
        setResult({
          decision: "RETRY",
          message: TECHNICAL_MESSAGE,
          technical_retry: true,
        });
        setState("answered");
        onAttemptComplete?.("RETRY");
        return;
      }
      const response = await submitToneAttempt(recording, expectedTone, itemId);
      // Only these three fields are read. Anything else the server sends is
      // ignored here by construction.
      const safe: ToneAttemptResponse = {
        decision: response.decision === "PASS" ? "PASS" : "RETRY",
        message:
          response.decision === "PASS"
            ? PASS_MESSAGE
            : response.technical_retry
              ? TECHNICAL_MESSAGE
              : RETRY_MESSAGE,
        technical_retry: Boolean(response.technical_retry),
      };
      setResult(safe);
      setState("answered");
      onAttemptComplete?.(safe.decision);
    } catch {
      setResult({
        decision: "RETRY",
        message: TECHNICAL_MESSAGE,
        technical_retry: true,
      });
      setState("answered");
      onAttemptComplete?.("RETRY");
    }
  }, [expectedTone, itemId, onAttemptComplete]);

  return (
    <section className="tone-attempt-panel" aria-label="Tone practice">
      <div className="tone-attempt-panel__prompt">
        <span className="tone-attempt-panel__character" lang="zh-Hant">
          {prompt}
        </span>
        {pinyin ? (
          <span className="tone-attempt-panel__pinyin">{pinyin}</span>
        ) : null}
      </div>

      {state === "idle" || state === "answered" ? (
        <button type="button" onClick={beginRecording}>
          {state === "answered" ? "Record again" : "Record"}
        </button>
      ) : null}

      {state === "recording" ? (
        <button type="button" onClick={finishRecording}>
          Stop
        </button>
      ) : null}

      {state === "submitting" ? (
        <p className="tone-attempt-panel__status" role="status">
          Checking…
        </p>
      ) : null}

      {result ? (
        <p
          className={`tone-attempt-panel__result tone-attempt-panel__result--${result.decision.toLowerCase()}`}
          role="status"
          data-decision={result.decision}
        >
          {result.message}
        </p>
      ) : null}
    </section>
  );
}
