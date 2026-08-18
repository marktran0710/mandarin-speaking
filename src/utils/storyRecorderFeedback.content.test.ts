import { describe, expect, it } from "vitest";
import { isContentAccepted, sceneContentGatePassed } from "./storyRecorderFeedback";

describe("target content gates", () => {
  it("require a verified match when a target script exists", () => {
    const unverified = { content_match: null } as never;
    const mismatch = { content_match: false } as never;
    const match = { content_match: true } as never;

    expect(isContentAccepted(unverified, true)).toBe(false);
    expect(sceneContentGatePassed(unverified, true)).toBe(false);
    expect(isContentAccepted(mismatch, true)).toBe(false);
    expect(sceneContentGatePassed(match, true)).toBe(true);
  });

  it("keeps targetless legacy semantic feedback behavior", () => {
    expect(isContentAccepted({ content_match: null } as never)).toBe(true);
    expect(sceneContentGatePassed({ content_match: null } as never)).toBe(true);
  });
});
