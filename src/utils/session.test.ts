import { beforeEach, describe, expect, it } from "vitest";
import { currentRole, readSession, signIn, signOut } from "./session";

describe("session", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("round-trips a signed-in student, roster id included", () => {
    signIn("student", "Minh", "stu-7");

    expect(readSession()).toMatchObject({
      role: "student",
      name: "Minh",
      id: "stu-7",
    });
    expect(currentRole()).toBe("student");
  });

  it("holds exactly one session — signing in as teacher replaces the student", () => {
    // The whole point of the single key: two roles can't coexist, so the
    // guards can't be handed a browser that is somehow both.
    signIn("student", "Minh", "stu-7");
    signIn("teacher", "Hau");

    expect(currentRole()).toBe("teacher");
    expect(readSession()?.name).toBe("Hau");
    expect(readSession()?.id).toBeUndefined();
  });

  it("sweeps the pre-single-key storage on sign-in and sign-out", () => {
    // A leftover activeRole/studentSession pair must not outlive the change
    // and get read by anything that hasn't been migrated.
    localStorage.setItem("activeRole", "teacher");
    localStorage.setItem("studentSession", JSON.stringify({ name: "Old" }));
    localStorage.setItem("teacherSession", JSON.stringify({ name: "Old" }));

    signIn("student", "Minh");

    expect(localStorage.getItem("activeRole")).toBeNull();
    expect(localStorage.getItem("studentSession")).toBeNull();
    expect(localStorage.getItem("teacherSession")).toBeNull();
  });

  it("ignores legacy keys entirely — they no longer grant a session", () => {
    localStorage.setItem("activeRole", "student");
    localStorage.setItem("studentSession", JSON.stringify({ name: "Minh" }));

    expect(readSession()).toBeNull();
    expect(currentRole()).toBeNull();
  });

  it("signs out completely", () => {
    signIn("teacher", "Hau");
    signOut();

    expect(readSession()).toBeNull();
    expect(currentRole()).toBeNull();
  });

  it("treats malformed or incomplete storage as signed out", () => {
    localStorage.setItem("session", "{not json");
    expect(readSession()).toBeNull();

    localStorage.setItem("session", JSON.stringify({ role: "wizard", name: "X" }));
    expect(readSession()).toBeNull();

    localStorage.setItem("session", JSON.stringify({ role: "student", name: "   " }));
    expect(readSession()).toBeNull();
  });
});
