// The signed-in student's identity — shared by every page that greets the
// student or keys their progress (extracted from CreateStoryPage when the
// journey strip spread identity across the student shell).
//
// Now a thin read over the single session key (see utils/session.ts). The
// signatures are unchanged on purpose: these three are called from a dozen
// places across the practice pages, the progression gates and the journey
// bubble, and none of them should have to know where identity is stored.
// Each falls back as if nobody were signed in when the session belongs to a
// teacher, so a teacher session can never be read as a student one.

import { readSession } from "./session";

function studentSession() {
  const session = readSession();
  return session?.role === "student" ? session : null;
}

export function getStudentName(): string {
  return studentSession()?.name || "Student";
}

/** Client-side demo/testing backdoor: signing in with the name "admin"
 * (any casing) bypasses every progression lock — lesson order, story
 * tiers, the quiz star gate, quiz tier ladder and scene readiness. Not a
 * security boundary: anyone can type the name; it exists so the teacher
 * can click through the whole app without earning unlocks. */
export function isAdminSession(): boolean {
  return getStudentName().toLowerCase() === "admin";
}

/** The roster-assigned id (see StudentLoginPage), when the student signed
 * in via the roster picker rather than a free-typed name. */
export function getStudentId(): string | undefined {
  return studentSession()?.id;
}

/** Stable key for scoping per-student localStorage mirrors (progress,
 * stars, completed-quiz flags) so a shared classroom device doesn't leak
 * one student's unlocks into the next student's session. Prefers the
 * roster id; falls back to the typed name for free-entry logins. */
export function getStudentScopeKey(): string {
  return getStudentId() ?? getStudentName().toLowerCase().trim();
}
