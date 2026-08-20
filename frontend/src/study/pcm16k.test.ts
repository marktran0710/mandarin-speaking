import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  STUDY_PCM_SPEC_VERSION,
  TARGET_SAMPLE_RATE,
  buildStudyWav,
  designFilter,
  encodeWav,
  resampleTo16k,
  toPcm16,
} from "./pcm16k";

/** Deterministic test signal — no Math.random anywhere in this suite. */
function tone(frequency: number, seconds: number, rate: number): Float64Array {
  const samples = new Float64Array(Math.round(seconds * rate));
  for (let index = 0; index < samples.length; index += 1) {
    samples[index] = 0.3 * Math.sin((2 * Math.PI * frequency * index) / rate);
  }
  return samples;
}

describe("STUDY_PCM16K_v1 conversion", () => {
  it("passes 16 kHz input through untouched (identity rule)", () => {
    const input = tone(200, 0.1, TARGET_SAMPLE_RATE);
    const output = resampleTo16k(input, TARGET_SAMPLE_RATE);
    expect(output.length).toBe(input.length);
    for (let index = 0; index < input.length; index += 1) {
      expect(output[index]).toBe(input[index]);
    }
  });

  it("preserves duration when converting 48 kHz to 16 kHz", () => {
    const input = tone(200, 0.2, 48000);
    const { metadata } = buildStudyWav(input, 48000);
    expect(metadata.input_duration_ms).toBeCloseTo(200, 6);
    expect(metadata.output_duration_ms).toBeCloseTo(200, 6);
    expect(metadata.output_frames).toBe(3200);
    expect(metadata.conversion).toBe("blackman_sinc_polyphase");
  });

  it("preserves duration when converting 44.1 kHz to 16 kHz", () => {
    const input = tone(200, 0.2, 44100);
    const { metadata } = buildStudyWav(input, 44100);
    expect(metadata.output_duration_ms).toBeCloseTo(200, 6);
    expect(metadata.output_frames).toBe(3200);
  });

  it("never merely relabels the header — frame count actually changes", () => {
    const input = tone(200, 0.2, 48000);
    const { metadata } = buildStudyWav(input, 48000);
    expect(metadata.input_frames).toBe(9600);
    expect(metadata.output_frames).toBe(3200);
    expect(metadata.output_frames).not.toBe(metadata.input_frames);
  });

  it("writes a well-formed 16 kHz mono 16-bit WAV header", () => {
    const { buffer, metadata } = buildStudyWav(tone(200, 0.1, 48000), 48000);
    const view = new DataView(buffer);
    const text = (offset: number, length: number) =>
      String.fromCharCode(
        ...Array.from({ length }, (_, index) => view.getUint8(offset + index)),
      );
    expect(text(0, 4)).toBe("RIFF");
    expect(text(8, 4)).toBe("WAVE");
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(TARGET_SAMPLE_RATE);
    expect(view.getUint16(34, true)).toBe(16); // bit depth
    expect(view.getUint32(40, true)).toBe(metadata.output_frames * 2);
  });

  it("is deterministic across repeated conversions", () => {
    const input = tone(180, 0.15, 48000);
    const first = new Uint8Array(buildStudyWav(input, 48000).buffer);
    const second = new Uint8Array(buildStudyWav(input, 48000).buffer);
    expect(Array.from(first)).toEqual(Array.from(second));
  });

  it("clamps and quantises without wrapping", () => {
    const pcm = toPcm16([2.0, -2.0, 0.0, 1.0, -1.0]);
    expect(Array.from(pcm)).toEqual([32767, -32767, 0, 32767, -32767]);
  });

  it("attenuates energy above the 8 kHz Nyquist limit", () => {
    // A 12 kHz tone at 48 kHz cannot survive honest conversion to 16 kHz.
    // Measured in the interior, away from the edge transient the constant
    // extension produces at the boundaries (asserted separately below).
    const converted = resampleTo16k(tone(12000, 0.1, 48000), 48000);
    let interior = 0;
    for (let index = 200; index < converted.length - 200; index += 1) {
      interior = Math.max(interior, Math.abs(converted[index]));
    }
    expect(interior).toBeLessThan(0.001); // ~ -89 dB against a 0.3 input
  });

  it("bounds the edge transient introduced by constant extension", () => {
    // Constant edge extension puts a step at each boundary, so the first and
    // last few milliseconds ring. This bounds it rather than hiding it.
    const converted = resampleTo16k(tone(12000, 0.1, 48000), 48000);
    let peak = 0;
    for (const value of converted) peak = Math.max(peak, Math.abs(value));
    expect(peak).toBeLessThan(0.1);
  });

  it("keeps a 200 Hz tone essentially intact", () => {
    const converted = resampleTo16k(tone(200, 0.1, 48000), 48000);
    let peak = 0;
    // Skip the filter's edge transient at both ends.
    for (let index = 200; index < converted.length - 200; index += 1) {
      peak = Math.max(peak, Math.abs(converted[index]));
    }
    expect(peak).toBeGreaterThan(0.28);
    expect(peak).toBeLessThan(0.32);
  });

  it("handles empty input without throwing", () => {
    expect(resampleTo16k(new Float64Array(0), 48000).length).toBe(0);
    expect(encodeWav(new Int16Array(0)).byteLength).toBe(44);
  });

  it("rejects a nonsensical source rate", () => {
    expect(() => resampleTo16k(tone(200, 0.01, 48000), 0)).toThrow();
    expect(() => resampleTo16k(tone(200, 0.01, 48000), -48000)).toThrow();
  });

  it("designs a linear-phase symmetric filter", () => {
    const taps = designFilter(1, 3);
    expect(taps.length).toBe(2 * 16 * 3 + 1);
    for (let index = 0; index < taps.length; index += 1) {
      expect(taps[index]).toBeCloseTo(taps[taps.length - 1 - index], 12);
    }
  });

  /**
   * Emits the vectors that verify_human_exposure_path.py compares against the
   * Python mirror. This is how "exactly one deterministic implementation"
   * becomes a checked property rather than a claim.
   */
  it("emits cross-language verification vectors", () => {
    const cases = [
      { name: "identity_16k", rate: TARGET_SAMPLE_RATE, frequency: 200, seconds: 0.05 },
      { name: "from_48k", rate: 48000, frequency: 200, seconds: 0.05 },
      { name: "from_44100", rate: 44100, frequency: 220, seconds: 0.05 },
      { name: "short_80ms_48k", rate: 48000, frequency: 180, seconds: 0.08 },
    ];
    const payload = {
      pcm_spec_version: STUDY_PCM_SPEC_VERSION,
      cases: cases.map((entry) => {
        const input = tone(entry.frequency, entry.seconds, entry.rate);
        const converted = resampleTo16k(input, entry.rate);
        return {
          name: entry.name,
          source_rate: entry.rate,
          frequency: entry.frequency,
          seconds: entry.seconds,
          input_frames: input.length,
          output_frames: converted.length,
          output: Array.from(converted),
          pcm16: Array.from(toPcm16(converted)),
        };
      }),
    };
    const target = resolve(
      __dirname,
      "../../backend/pronunciation/wav2vec_tone/data/technical_verification/tv3_ts_vectors.json",
    );
    if (!existsSync(dirname(target))) mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, JSON.stringify(payload), "utf-8");
    expect(payload.cases.length).toBe(4);
  });
});
