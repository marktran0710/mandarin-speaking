import { describe, expect, it } from "vitest";
import { isContentAccepted, sceneContentGatePassed } from "./storyRecorderFeedback";

describe("target content gates", () => {
  it("trusts an explicit content_match verdict either way", () => {
    expect(isContentAccepted({ content_match: true } as never)).toBe(true);
    expect(sceneContentGatePassed({ content_match: true } as never)).toBe(true);
    expect(isContentAccepted({ content_match: false } as never)).toBe(false);
    expect(sceneContentGatePassed({ content_match: false } as never)).toBe(false);
  });

  it("fails open on a null/unverified content_match — a verification hiccup never blocks a pass", () => {
    expect(isContentAccepted({ content_match: null } as never)).toBe(true);
    expect(sceneContentGatePassed({ content_match: null } as never)).toBe(true);
  });
});
