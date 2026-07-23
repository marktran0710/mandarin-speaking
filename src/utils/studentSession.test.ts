import { afterEach, describe, expect, it } from "vitest";
import { getStudentName, isAdminSession } from "./studentSession";
import { isTierUnlocked, practiceUnlocked } from "./quizTiers";
import { isStoryLevelUnlocked } from "./storyLevelProgress";
import { sceneReady } from "./storyRecorderFeedback";

function signInAs(name: string) {
  localStorage.setItem("studentSession", JSON.stringify({ name }));
}

afterEach(() => {
  localStorage.removeItem("studentSession");
});

describe("isAdminSession", () => {
  it("matches the name 'admin' in any casing, nobody else", () => {
    signInAs("Admin");
    expect(isAdminSession()).toBe(true);
    signInAs("ADMIN");
    expect(isAdminSession()).toBe(true);
    signInAs("Minh");
    expect(isAdminSession()).toBe(false);
    localStorage.removeItem("studentSession");
    expect(getStudentName()).toBe("Student");
    expect(isAdminSession()).toBe(false);
  });

  it("bypasses the progression gates while signed in as admin", () => {
    signInAs("Minh");
    expect(isTierUnlocked(3, 0)).toBe(false);
    expect(practiceUnlocked(0)).toBe(false);
    expect(isStoryLevelUnlocked("s1", "hard")).toBe(false);
    expect(sceneReady({ attempts: 0, bestTone: 0, bestFluency: 0 })).toBe(false);

    signInAs("admin");
    expect(isTierUnlocked(3, 0)).toBe(true);
    expect(practiceUnlocked(0)).toBe(true);
    expect(isStoryLevelUnlocked("s1", "hard")).toBe(true);
    expect(sceneReady({ attempts: 0, bestTone: 0, bestFluency: 0 })).toBe(true);
  });
});
