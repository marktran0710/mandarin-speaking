/**
 * Study recording path — the ONLY capture route used for tone-confirmation
 * attempts in the controlled validation study.
 *
 * Deliberately not MediaRecorder. MediaRecorder produces WebM/Opus, which the
 * validated backend cannot decode and which is lossy; this path captures raw
 * PCM through WebAudio and converts it once, with STUDY_PCM16K_v1, to the
 * 16 kHz mono WAV the frozen model was fitted on.
 *
 * Where resampling happens, stated plainly: the microphone and the browser's
 * audio graph run at the hardware rate (`AudioContext.sampleRate`, commonly
 * 48000). We do NOT request `new AudioContext({sampleRate: 16000})`, because
 * that would hand the conversion to each browser's own resampler and we would
 * no longer have one implementation. Instead we capture at the hardware rate
 * and convert in `pcm16k.ts`. The physical microphone is not claimed to produce
 * 16 kHz.
 */

import {
  STUDY_PCM_SPEC_VERSION,
  TARGET_SAMPLE_RATE,
  buildStudyWav,
  type StudyAudioMetadata,
} from "./pcm16k";

export { STUDY_PCM_SPEC_VERSION, TARGET_SAMPLE_RATE };

export interface StudyRecording {
  blob: Blob;
  metadata: StudyAudioMetadata;
  /** True when the capture produced no frames at all — a technical failure. */
  empty: boolean;
}

/** Emitted by the worklet: raw Float32 frames at the graph's sample rate. */
const WORKLET_SOURCE = `
class StudyCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      this.port.postMessage(channel.slice(0));
    }
    return true;
  }
}
registerProcessor('study-capture', StudyCaptureProcessor);
`;

function concatenate(chunks: Float32Array[]): Float32Array {
  let total = 0;
  for (const chunk of chunks) total += chunk.length;
  const merged = new Float32Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

export class StudyRecorder {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private chunks: Float32Array[] = [];
  private recording = false;

  get isRecording(): boolean {
    return this.recording;
  }

  /** The hardware/graph rate actually in use, once recording has started. */
  get captureSampleRate(): number | null {
    return this.context?.sampleRate ?? null;
  }

  async start(): Promise<void> {
    if (this.recording) return;
    this.chunks = [];

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        // Leave the browser's own processing off: the frozen model was fitted
        // on unprocessed corpus audio, and these filters are not part of it.
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });

    // No sampleRate option: see the module comment. One resampler, ours.
    const AudioContextClass =
      window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    this.context = new AudioContextClass();
    this.source = this.context.createMediaStreamSource(this.stream);

    if (this.context.audioWorklet) {
      const url = URL.createObjectURL(
        new Blob([WORKLET_SOURCE], { type: "application/javascript" }),
      );
      try {
        await this.context.audioWorklet.addModule(url);
        const worklet = new AudioWorkletNode(this.context, "study-capture");
        worklet.port.onmessage = (event: MessageEvent<Float32Array>) => {
          if (this.recording) this.chunks.push(new Float32Array(event.data));
        };
        this.node = worklet;
      } finally {
        URL.revokeObjectURL(url);
      }
    } else {
      const processor = this.context.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (event) => {
        if (this.recording) {
          this.chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
        }
      };
      this.node = processor;
    }

    this.source.connect(this.node);
    // A destination connection keeps the graph pulling in every browser; a
    // zero-gain node prevents the participant hearing themselves.
    const silence = this.context.createGain();
    silence.gain.value = 0;
    this.node.connect(silence);
    silence.connect(this.context.destination);

    this.recording = true;
  }

  async stop(): Promise<StudyRecording> {
    if (!this.recording || !this.context) {
      return {
        blob: new Blob([], { type: "audio/wav" }),
        metadata: {
          pcm_spec_version: STUDY_PCM_SPEC_VERSION,
          capture_sample_rate: 0,
          output_sample_rate: TARGET_SAMPLE_RATE,
          conversion: "identity",
          input_frames: 0,
          output_frames: 0,
          input_duration_ms: 0,
          output_duration_ms: 0,
        },
        empty: true,
      };
    }
    this.recording = false;

    const captureRate = this.context.sampleRate;
    const frames = concatenate(this.chunks);
    this.teardown();

    if (frames.length === 0) {
      return {
        blob: new Blob([], { type: "audio/wav" }),
        metadata: {
          pcm_spec_version: STUDY_PCM_SPEC_VERSION,
          capture_sample_rate: captureRate,
          output_sample_rate: TARGET_SAMPLE_RATE,
          conversion: "identity",
          input_frames: 0,
          output_frames: 0,
          input_duration_ms: 0,
          output_duration_ms: 0,
        },
        empty: true,
      };
    }

    const { blob, metadata } = buildStudyWav(frames, captureRate);
    return { blob, metadata, empty: false };
  }

  private teardown(): void {
    try {
      this.node?.disconnect();
      this.source?.disconnect();
    } catch {
      /* graph already torn down */
    }
    this.stream?.getTracks().forEach((track) => track.stop());
    void this.context?.close();
    this.context = null;
    this.stream = null;
    this.node = null;
    this.source = null;
    this.chunks = [];
  }
}

export interface ToneAttemptResponse {
  decision: "PASS" | "RETRY";
  message: string;
  technical_retry: boolean;
}

/**
 * Submit one attempt. The response carries only what a participant may see;
 * the internal score never crosses this boundary.
 */
export async function submitToneAttempt(
  recording: StudyRecording,
  expectedTone: string,
  itemId: string,
  endpoint = "/api/pronunciation/tone-attempt",
): Promise<ToneAttemptResponse> {
  const form = new FormData();
  form.append("audio", recording.blob, "attempt.wav");
  form.append("expected_tone", expectedTone);
  form.append("item_id", itemId);
  form.append("capture_sample_rate", String(recording.metadata.capture_sample_rate));
  form.append("pcm_spec_version", recording.metadata.pcm_spec_version);

  const response = await fetch(endpoint, { method: "POST", body: form });
  return (await response.json()) as ToneAttemptResponse;
}
