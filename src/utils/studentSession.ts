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

const LAST_PAGE_KEY_PREFIX = "studentLastPage:";

/** Which section a student had open, so a reload lands them back where
 * they were instead of bouncing to the practice tab. Scoped per-student
 * (like the progress mirrors above) so a shared device doesn't hand the
 * next student whoever was signed in before them left off. */
export function getLastVisitedPage(): string | null {
  try {
    return localStorage.getItem(`${LAST_PAGE_KEY_PREFIX}${getStudentScopeKey()}`);
  } catch {
    return null;
  }
}

export function saveLastVisitedPage(page: string) {
  try {
    localStorage.setItem(`${LAST_PAGE_KEY_PREFIX}${getStudentScopeKey()}`, page);
  } catch {
    /* storage unavailable — page just won't be remembered */
  }
}

export function clearLastVisitedPage() {
  try {
    localStorage.removeItem(`${LAST_PAGE_KEY_PREFIX}${getStudentScopeKey()}`);
  } catch {
    /* noop */
  }
}

const LAST_PRACTICE_TARGET_KEY_PREFIX = "studentLastPracticeTarget:";

export interface LastPracticeTarget {
  topicId: string;
  imageIndex: number;
}

/** Which story (and scene) a student had open on the practice page — the
 * page-level restore above only gets them back to the practice *tab*;
 * without this they'd land on the browse/table-of-contents view instead
 * of the story they were mid-session on. */
export function getLastPracticeTarget(): LastPracticeTarget | null {
  try {
    const raw = localStorage.getItem(`${LAST_PRACTICE_TARGET_KEY_PREFIX}${getStudentScopeKey()}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.topicId !== "string" || !parsed.topicId) return null;
    const imageIndex = typeof parsed.imageIndex === "number" ? parsed.imageIndex : 0;
    return { topicId: parsed.topicId, imageIndex };
  } catch {
    return null;
  }
}

/** Pass `null` to record that the student explicitly backed out to the
 * browse view, so a reload doesn't drop them back into the story they
 * just left. */
export function saveLastPracticeTarget(target: LastPracticeTarget | null) {
  try {
    const key = `${LAST_PRACTICE_TARGET_KEY_PREFIX}${getStudentScopeKey()}`;
    if (target) {
      localStorage.setItem(key, JSON.stringify(target));
    } else {
      localStorage.removeItem(key);
    }
  } catch {
    /* storage unavailable — session just won't be remembered */
  }
}

export function clearLastPracticeTarget() {
  try {
    localStorage.removeItem(`${LAST_PRACTICE_TARGET_KEY_PREFIX}${getStudentScopeKey()}`);
  } catch {
    /* noop */
  }
}
