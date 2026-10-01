import { getStudentScopeKey } from "../../utils/studentSession";

const KEY_PREFIX = "studentOnboardingSeen:";

function flagKey(): string {
  return `${KEY_PREFIX}${getStudentScopeKey()}`;
}

/** Whether this student already went through the intro. Kept in localStorage
 * per student (like the lesson phase flags): the intro is only shown to new
 * accounts, so losing the flag just shows it once more. */
export function hasSeenOnboarding(): boolean {
  try {
    return localStorage.getItem(flagKey()) === "1";
  } catch {
    return false;
  }
}

export function markOnboardingSeen(): void {
  try {
    localStorage.setItem(flagKey(), "1");
  } catch {
    /* storage unavailable; the intro would simply show again */
  }
}
