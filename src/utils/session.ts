// Who is signed in, in one place.
//
// The student app (index.html) and the teacher app (teacher.html) are two
// Vite entry points on the SAME origin, so they share one localStorage.
// This used to be three keys — `activeRole` plus a `studentSession` /
// `teacherSession` pair — and both apps wrote `activeRole`, so signing into
// one silently reassigned the other's role. "Which role am I" had two
// sources of truth that could disagree.
//
// One key, with the role inside it, makes "only one mode at a time" true by
// construction instead of a rule each app has to remember to check.

export type Role = "student" | "teacher";

export interface Session {
  role: Role;
  name: string;
  /** Roster-assigned student id, when the student signed in through the
   * roster picker rather than a free-typed name. Teachers have none. */
  id?: string;
  signedInAt: string;
}

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
export function readSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
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

/** The signed-in role, or null. The one comparison each app's guard makes. */
export function currentRole(): Role | null {
  return readSession()?.role ?? null;
}

/** Replaces whatever was there — there is only ever one session. */
export function signIn(role: Role, name: string, id?: string): Session {
  const session: Session = {
    role,
    name: name.trim(),
    id,
    signedInAt: new Date().toISOString(),
  };
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  clearLegacyKeys();
  return session;
}

export function signOut() {
  localStorage.removeItem(SESSION_KEY);
  clearLegacyKeys();
}
