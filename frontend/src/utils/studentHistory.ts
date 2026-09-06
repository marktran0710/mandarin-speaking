/** Small, framework-free helpers for the student SPA's stateful history.
 *
 * A state transition must replace the entry being left before it pushes the
 * destination. Otherwise Forward replays the old snapshot and the browser
 * accumulates entries that never represented a visible student screen.
 */
export function historyStateWith<T>(key: string, snapshot: T): Record<string, unknown> {
  const current = window.history.state;
  const base = current && typeof current === "object" ? current : {};
  return { ...base, [key]: snapshot };
}

export function replaceHistorySnapshot<T>(key: string, snapshot: T) {
  window.history.replaceState(historyStateWith(key, snapshot), "", window.location.href);
}

export function pushHistorySnapshot<T>(key: string, snapshot: T) {
  window.history.pushState(historyStateWith(key, snapshot), "", window.location.href);
}
