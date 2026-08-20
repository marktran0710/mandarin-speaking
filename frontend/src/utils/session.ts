// Who is signed in, in one place.
//
// The student app (index.html) and the teacher app (teacher.html) are two
// Vite entry points on the SAME origin, so they share one localStorage.
// This used to be three keys — `activeRole` plus a `studentSession` /
// `teacherSession` pair — and both apps wrote `activeRole`, so signing into
// one silently reassigned the other's role. "Which role am I" had two
// sources of truth that could disagree.
//
// Each role keeps its own browser session so a teacher can monitor the class
// while a student remains signed in on the same device/browser.

export type Role = "student" | "teacher";

export interface Session {
  role: Role;
  name: string;
  /** Roster-assigned student id, when the student signed in through the
   * roster picker rather than a free-typed name. Teachers have none. */
  id?: string;
  signedInAt: string;
}

const SESSION_KEYS: Record<Role, string> = { student: "studentSession", teacher: "teacherSession" };
const SESSION_KEY = "session";

/** Pre-single-key storage. Swept on every write rather than migrated: the
 * cost is one re-login for anyone signed in at upgrade time, and in return
 * no stale role can outlive the change and reappear during debugging. */
const LEGACY_KEYS = ["activeRole", "studentSession", "teacherSession"];

function clearLegacyKeys() {
  for (const key of LEGACY_KEYS) {
    localStorage.removeItem(key);
  }
}

function isRole(value: unknown): value is Role {
  return value === "student" || value === "teacher";
}

/** The current session, or null when nobody is signed in. Returns null for
 * malformed storage too — a session that can't be parsed is one nobody is
 * in, which is the safe reading for a value that gates access. */
export function readSession(role?: Role): Session | null {
  try {
    const raw = role
      ? localStorage.getItem(SESSION_KEYS[role])
      : localStorage.getItem(SESSION_KEY) ?? localStorage.getItem(SESSION_KEYS.student) ?? localStorage.getItem(SESSION_KEYS.teacher);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!isRole(parsed?.role)) return null;
    const name = typeof parsed.name === "string" ? parsed.name.trim() : "";
    if (!name) return null;
    return {
      role: parsed.role,
      name,
      id: typeof parsed.id === "string" && parsed.id ? parsed.id : undefined,
      signedInAt:
        typeof parsed.signedInAt === "string"
          ? parsed.signedInAt
          : new Date().toISOString(),
    };
  } catch {
    return null;
  }
}

/**
 * The role visible to an app, or null. An app only owns its own role session;
 * the other app's session must not block it.
 */
export function currentRole(role?: Role): Role | null {
  if (!role) return readSession()?.role ?? null;
  return readSession(role)?.role ?? null;
}

/** Replaces whatever was there — there is only ever one session. */
export function signIn(role: Role, name: string, id?: string): Session {
  const session: Session = {
    role,
    name: name.trim(),
    id,
    signedInAt: new Date().toISOString(),
  };
  localStorage.setItem(SESSION_KEYS[role], JSON.stringify(session));
  localStorage.removeItem(SESSION_KEY);
  return session;
}

export function signOut(role?: Role) {
  if (role) localStorage.removeItem(SESSION_KEYS[role]);
  else {
    localStorage.removeItem(SESSION_KEY);
    localStorage.removeItem(SESSION_KEYS.student);
    localStorage.removeItem(SESSION_KEYS.teacher);
    clearLegacyKeys();
  }
}
