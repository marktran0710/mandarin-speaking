import { describe, expect, it } from "vitest";
import { pushHistorySnapshot, replaceHistorySnapshot } from "./studentHistory";

describe("student history snapshots", () => {
  it("replaces the visible origin before pushing one destination entry", () => {
    window.history.replaceState({ preserved: "browser-state" }, "", "/");

    replaceHistorySnapshot("mandarinApp", { currentPage: "student-workspace" });
    const origin = window.history.state;
    pushHistorySnapshot("mandarinApp", { currentPage: "voice-test" });

    expect(origin).toMatchObject({
      preserved: "browser-state",
      mandarinApp: { currentPage: "student-workspace" },
    });
    expect(window.history.state).toMatchObject({
      preserved: "browser-state",
      mandarinApp: { currentPage: "voice-test" },
    });
  });
});
