import { beforeEach, describe, expect, it } from "vitest";
import { currentRole, readSession, signIn, signOut } from "./session";

describe("independent role sessions", () => {
  beforeEach(() => localStorage.clear());

  it("round-trips a student session", () => {
    signIn("student", "Minh", "stu-7");
    expect(readSession("student")).toMatchObject({ role: "student", name: "Minh", id: "stu-7" });
    expect(currentRole("student")).toBe("student");
  });

  it("keeps teacher and student sessions active at the same time", () => {
    signIn("student", "Minh", "stu-7");
    signIn("teacher", "Hau", "teacher-1");
    expect(readSession("student")?.name).toBe("Minh");
    expect(readSession("teacher")?.name).toBe("Hau");
    expect(currentRole("student")).toBe("student");
    expect(currentRole("teacher")).toBe("teacher");
  });

  it("clears only the requested role on sign out", () => {
    signIn("student", "Minh");
    signIn("teacher", "Hau");
    signOut("teacher");
    expect(readSession("teacher")).toBeNull();
    expect(readSession("student")?.name).toBe("Minh");
  });

  it("ignores legacy keys", () => {
    localStorage.setItem("activeRole", "student");
    localStorage.setItem("studentSession", JSON.stringify({ name: "Old" }));
    expect(readSession("student")).toBeNull();
  });

  it("clears both sessions when signing out without a role", () => {
    signIn("student", "Minh");
    signIn("teacher", "Hau");
    signOut();
    expect(readSession("student")).toBeNull();
    expect(readSession("teacher")).toBeNull();
  });

  it("does not treat the opposite role as this app's session", () => {
    signIn("teacher", "Hau");
    expect(currentRole("student")).toBeNull();

    signOut("teacher");
    signIn("student", "Minh");
    expect(currentRole("teacher")).toBeNull();
  });
});
