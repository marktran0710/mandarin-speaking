import { afterEach, describe, expect, it } from "vitest";
import { getStudentName, isAdminSession } from "./studentSession";
import { isTierUnlocked, practiceUnlocked } from "./quizTiers";
import { isStoryLevelUnlocked } from "./storyLevelProgress";
import { sceneReady } from "./storyRecorderFeedback";
import { signIn, signOut } from "./session";

// Goes through the session module rather than writing its storage key, so
// these stay about the gates' behaviour and don't re-break the next time
// identity moves.
function signInAs(name: string) {
  signIn("student", name);
}

afterEach(() => {
  signOut();
});

describe("isAdminSession", () => {
  it("matches the name 'admin' in any casing, nobody else", () => {
    signInAs("Admin");
    expect(isAdminSession()).toBe(true);
    signInAs("ADMIN");
    expect(isAdminSession()).toBe(true);
    signInAs("Minh");
    expect(isAdminSession()).toBe(false);
    signOut();
    expect(getStudentName()).toBe("Student");
    expect(isAdminSession()).toBe(false);
  });

  it("reads a teacher session as nobody, so it can never bypass a gate", () => {
    // Both roles now share one key; a teacher named "admin" must not inherit
    // the student backdoor just by being signed in on the same device.
    signIn("teacher", "admin");

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
