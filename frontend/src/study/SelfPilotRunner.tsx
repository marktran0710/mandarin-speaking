/**
 * Researcher self-pilot runner — workflow rehearsal, not validation.
 *
 * Walks the researcher through the 16 prompts for Run A (natural), Run B
 * (repeat) and Run C (deliberate challenge productions), recording through the
 * same StudyRecorder and scoring through the same frozen engine as the study
 * route.
 *
 * This screen is for the RESEARCHER, not a participant, so it deliberately does
 * show the internal score — they need it to judge whether the system reacted
 * plausibly. `ToneAttemptPanel` remains the participant-facing component and
 * still shows nothing but the decision message.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { StudyRecorder } from "./studyRecorder";

const RUNS = [
  { id: "A_natural", label: "Run A — natural production" },
  { id: "B_repeat", label: "Run B — repeat" },
  { id: "C_challenge", label: "Run C — deliberate challenge" },
] as const;

interface Item {
  item_id: string;
  traditional_character: string;
  expected_pinyin: string;
  expected_tone: string;
  english_gloss: string;
  teacher_approved: boolean;
}

interface ChallengeEntry {
  item_id: string;
  expected_tone: string;
  challenge_type: string;
  intended_manipulation: string;
}

interface AttemptResult {
  trial_uid: string;
  decision: "PASS" | "RETRY";
  message: string;
  technical_retry: boolean;
  raw_score_internal: number | null;
  trajectory_available: boolean;
  failure_code: string;
  latency_ms: number;
  token_duration_ms: number | null;
}

export interface SelfPilotRunnerProps {
  apiBase?: string;
}

export default function SelfPilotRunner({ apiBase = "" }: SelfPilotRunnerProps) {
  const [items, setItems] = useState<Item[]>([]);
  const [challengePlan, setChallengePlan] = useState<ChallengeEntry[]>([]);
  const [run, setRun] = useState<string>(RUNS[0].id);
  const [index, setIndex] = useState(0);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [notes, setNotes] = useState("");
  const [log, setLog] = useState<string[]>([]);
  const recorderRef = useRef<StudyRecorder | null>(null);

  useEffect(() => {
    void fetch(`${apiBase}/api/self-pilot/items`)
      .then((response) => response.json())
      .then((body) => {
        setItems(body.items ?? []);
        setChallengePlan(body.challenge_plan ?? []);
      })
      .catch(() => setLog((entries) => [...entries, "could not load items"]));
  }, [apiBase]);

  // Run C only visits the items on the fixed challenge plan.
  const activeItems =
    run === "C_challenge"
      ? items.filter((item) => challengePlan.some((c) => c.item_id === item.item_id))
      : items;
  const item = activeItems[index];
  const challenge = challengePlan.find((c) => c.item_id === item?.item_id);
  const repetition = run === "B_repeat" ? 2 : 1;

  const start = useCallback(async () => {
    setResult(null);
    const recorder = new StudyRecorder();
    recorderRef.current = recorder;
    try {
      await recorder.start();
      setRecording(true);
    } catch (error) {
      setLog((entries) => [...entries, `microphone unavailable: ${error}`]);
    }
  }, []);

  const stop = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder || !item) return;
    setRecording(false);
    setBusy(true);
    try {
      const capture = await recorder.stop();
      if (capture.empty) {
        setLog((entries) => [...entries, `${item.item_id}: empty capture`]);
        setBusy(false);
        return;
      }
      const form = new FormData();
      form.append("audio", capture.blob, "attempt.wav");
      form.append("item_id", item.item_id);
      form.append("expected_tone", item.expected_tone);
      form.append("run", run);
      form.append("repetition", String(repetition));
      form.append("capture_sample_rate", String(capture.metadata.capture_sample_rate));
      form.append("pcm_spec_version", capture.metadata.pcm_spec_version);
      form.append("researcher_notes", notes);
      if (run === "C_challenge" && challenge) {
        form.append("challenge_type", challenge.challenge_type);
        form.append("intended_manipulation", challenge.intended_manipulation);
      }
      const response = await fetch(`${apiBase}/api/self-pilot/attempt`, {
        method: "POST",
        body: form,
      });
      const body = (await response.json()) as AttemptResult;
      setResult(body);
      setLog((entries) => [
        ...entries,
        `${body.trial_uid} ${item.item_id} ${item.expected_tone} -> ${body.decision}` +
          (body.raw_score_internal === null
            ? ` (${body.failure_code})`
            : ` (score ${body.raw_score_internal.toFixed(4)})`),
      ]);
    } catch (error) {
      setLog((entries) => [...entries, `${item.item_id}: request failed ${error}`]);
    } finally {
      setBusy(false);
    }
  }, [apiBase, challenge, item, notes, repetition, run]);

  const advance = useCallback(() => {
    setResult(null);
    setNotes("");
    setIndex((current) => Math.min(current + 1, activeItems.length - 1));
  }, [activeItems.length]);

  if (!item) {
    return <p>Loading self-pilot items…</p>;
  }

  return (
    <section className="self-pilot" aria-label="Researcher self-pilot">
      <header>
        <h1>Researcher self-pilot</h1>
        <p role="note">
          Workflow rehearsal only. These recordings are PILOT_ONLY and may never
          be used for accuracy, PASS precision, agreement or kappa. The 16 items
          are still awaiting teacher review; running them here is not approval.
        </p>
      </header>

      <label>
        Run
        <select
          value={run}
          onChange={(event) => {
            setRun(event.target.value);
            setIndex(0);
            setResult(null);
          }}
        >
          {RUNS.map((entry) => (
            <option key={entry.id} value={entry.id}>
              {entry.label}
            </option>
          ))}
        </select>
      </label>

      <p>
        Item {index + 1} of {activeItems.length}
      </p>

      <div className="self-pilot__prompt">
        <span lang="zh-Hant" style={{ fontSize: "4rem" }}>
          {item.traditional_character}
        </span>
        <span>{item.expected_pinyin}</span>
        <span>{item.english_gloss}</span>
        <span>{item.expected_tone}</span>
      </div>

      {run === "C_challenge" && challenge ? (
        <p className="self-pilot__challenge">
          <strong>Challenge:</strong> {challenge.intended_manipulation}
          <br />
          <em>
            Diagnostic probe only — this is not a verified Mandarin tone error.
          </em>
        </p>
      ) : null}

      {recording ? (
        <p role="status" aria-live="assertive">
          ● Recording — speak now
        </p>
      ) : null}

      <div>
        {!recording ? (
          <button type="button" onClick={start} disabled={busy}>
            Record
          </button>
        ) : (
          <button type="button" onClick={stop}>
            Stop
          </button>
        )}
        <button type="button" onClick={advance} disabled={recording || busy}>
          Next item
        </button>
      </div>

      <label>
        Researcher notes
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          rows={2}
        />
      </label>

      {result ? (
        <div className="self-pilot__result" data-decision={result.decision}>
          <p>
            <strong>Participant would see:</strong> {result.message}
          </p>
          <p>
            <strong>Researcher diagnostics:</strong> decision {result.decision};
            score{" "}
            {result.raw_score_internal === null
              ? "n/a"
              : result.raw_score_internal.toFixed(6)}
            ; trajectory {result.trajectory_available ? "yes" : "no"}; code{" "}
            {result.failure_code}; {result.latency_ms.toFixed(1)} ms
          </p>
        </div>
      ) : null}

      <details>
        <summary>Session log ({log.length})</summary>
        <pre>{log.join("\n")}</pre>
      </details>
    </section>
  );
}
