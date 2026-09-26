import { describe, expect, it } from "vitest";
import { parseLessonAudioFilename } from "./myStoriesUtils";

describe("parseLessonAudioFilename", () => {
  it("reads lesson, story sub-order, and scene from a plain numeric name", () => {
    expect(parseLessonAudioFilename("5-1-01.mp3")).toEqual({
      lessonNumber: 5,
      lessonSubOrder: 1,
      sceneIndex: 1,
    });
  });

  it("ignores non-digit separators and prefixes", () => {
    expect(parseLessonAudioFilename("L6_2_s03.m4a")).toEqual({
      lessonNumber: 6,
      lessonSubOrder: 2,
      sceneIndex: 3,
    });
  });

  it("takes the first three numbers when extra numbers follow", () => {
    expect(parseLessonAudioFilename("7-3-04-take2.wav")).toEqual({
      lessonNumber: 7,
      lessonSubOrder: 3,
      sceneIndex: 4,
    });
  });

  it("returns null when fewer than three numbers are present", () => {
    expect(parseLessonAudioFilename("scene01.mp3")).toBeNull();
    expect(parseLessonAudioFilename("5-01.mp3")).toBeNull();
  });

  it("returns null when any leading number is zero", () => {
    expect(parseLessonAudioFilename("0-1-01.mp3")).toBeNull();
    expect(parseLessonAudioFilename("5-0-01.mp3")).toBeNull();
    expect(parseLessonAudioFilename("5-1-00.mp3")).toBeNull();
  });
});
