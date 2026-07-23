// The signed-in student's identity, read from the localStorage session the
// login screen writes — shared by every page that greets the student or
// keys their progress (extracted from CreateStoryPage when the journey
// strip spread identity across the student shell).

export function getStudentName(): string {
  try {
    const session = JSON.parse(localStorage.getItem("studentSession") || "{}");
    return typeof session.name === "string" && session.name.trim()
      ? session.name.trim()
      : "Student";
  } catch {
    return "Student";
  }
}

/** Client-side demo/testing backdoor: signing in with the name "admin"
 * (any casing) bypasses every progression lock — lesson order, story
 * tiers, the quiz star gate, quiz tier ladder and scene readiness. Not a
 * security boundary: anyone can type the name; it exists so the teacher
 * can click through the whole app without earning unlocks. */
export function isAdminSession(): boolean {
  return getStudentName().toLowerCase() === "admin";
}

/** The roster-assigned id (see LoginPage), when the student signed in via
 * the roster picker rather than a name typed before the roster existed. */
export function getStudentId(): string | undefined {
  try {
    const session = JSON.parse(localStorage.getItem("studentSession") || "{}");
    return typeof session.id === "string" && session.id ? session.id : undefined;
  } catch {
    return undefined;
  }
}
