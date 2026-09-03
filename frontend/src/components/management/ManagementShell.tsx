import { type ReactNode, useEffect, useRef, useState } from "react";
import useColorMode from "../../hooks/useColorMode";
import ToneMark from "../tone/ToneMark";
import Icon, { type UiIconName } from "../../shared/ui/Icon";
import "./ManagementShell.css";

export type ManagementRole = "teacher" | "admin";

export interface ManagementNavItem {
  id: string;
  label: string;
  icon: string;
  group?: string;
  count?: number;
  hot?: boolean;
}

/** One flat list, no groups and no sub-tabs: each entry owns exactly one
 * dataset, so there is only ever one place to do a given job. */
const DEFAULT_TEACHER_ITEMS: ManagementNavItem[] = [
  { id: "today", label: "Today", icon: "help" },
  // Recording evidence lives on this same view, under the submissions list —
  // both are "student work to review", so one nav entry owns both.
  { id: "submissions", label: "Submissions", icon: "inbox" },
  { id: "students", label: "Students", icon: "users" },
  { id: "materials", label: "Materials", icon: "library" },
];

const DEFAULT_ADMIN_ITEMS: ManagementNavItem[] = [
  { id: "Admin Home", label: "Admin Home", icon: "dashboard" },
  { id: "Teachers", label: "Teachers", icon: "users", group: "Accounts" },
  { id: "Students", label: "Students", icon: "users", group: "Accounts" },
  { id: "IRT / Student analytics", label: "IRT / Student analytics", icon: "analytics", group: "Insights" },
  { id: "Measurement", label: "Measurement", icon: "analytics", group: "Insights" },
  { id: "Practice Debug", label: "Practice Debug", icon: "debug", group: "Insights" },
];

const legacyIconMap: Record<string, UiIconName> = {
  "📊": "dashboard", "📥": "inbox", "🎙️": "microphone", "📚": "library", "📈": "analytics",
  "⌂": "dashboard", "◉": "users", "◎": "users", "◌": "analytics", "⌁": "debug",
};

export default function ManagementShell({
  role,
  activeView,
  onSelectView,
  children,
  navItems,
  submissionCount = 0,
  openHelpCount = 0,
  refreshing = false,
  onRefresh,
  onLogout,
}: {
  role: ManagementRole;
  activeView: string;
  onSelectView: (view: string) => void;
  children: ReactNode;
  navItems?: ManagementNavItem[];
  submissionCount?: number;
  openHelpCount?: number;
  refreshing?: boolean;
  onRefresh?: () => void;
  onLogout: () => void;
}) {
  const [colorMode, toggleColorMode] = useColorMode();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const menuToggleRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  // Only "Today" runs hot: a raised hand is the one thing that needs a reply
  // right now, so it is the only place the gold badge appears.
  const counts: Record<string, number> = {
    today: openHelpCount,
    submissions: submissionCount,
  };
  const items = (navItems ?? (role === "teacher" ? DEFAULT_TEACHER_ITEMS : DEFAULT_ADMIN_ITEMS)).map((item) => ({
    ...item,
    count: counts[item.id] ?? item.count,
    hot: item.id === "today" ? openHelpCount > 0 : item.hot,
  }));

  let currentGroup: string | undefined;

  const selectView = (view: string) => {
    onSelectView(view);
    setDrawerOpen(false);
  };

  useEffect(() => {
    if (!drawerOpen) return;
    const focusTimer = window.setTimeout(() => drawerRef.current?.querySelector<HTMLButtonElement>(".management-nav-item")?.focus(), 0);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setDrawerOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", handleKeyDown);
      menuToggleRef.current?.focus();
    };
  }, [drawerOpen]);

  return (
    <div className={`management-shell management-role-${role}`}>
      <header className="management-topbar">
        <button
          ref={menuToggleRef}
          type="button"
          className="management-menu-toggle"
          aria-label={drawerOpen ? "Close menu" : "Open menu"}
          aria-expanded={drawerOpen}
          aria-controls="management-sidebar"
          onClick={() => setDrawerOpen((open) => !open)}
        >
          <Icon name="menu" size={20} />
        </button>
        <div className="management-brand">
          <img src="/logo.png" alt="慢慢中文 logo" />
          <span>慢慢中文</span>
          <small>{role === "teacher" ? "Teacher Studio" : "Admin Console"}</small>
          <ToneMark className="management-tonemark" size={20} />
        </div>
        {/* No role badge here: the brand line already reads "Teacher Studio"
            / "Admin Console", so the badge said the same word twice. */}
        <div className="management-topbar-actions">
          <button
            type="button"
            className="management-chip"
            onClick={toggleColorMode}
            aria-pressed={colorMode === "dark"}
          >
            <Icon name={colorMode === "dark" ? "sun" : "moon"} size={16} />
            <span>{colorMode === "dark" ? "Light" : "Dark"}</span>
          </button>
          {onRefresh && (
            <button type="button" className="management-chip" disabled={refreshing} onClick={onRefresh}>
              <Icon name="refresh" size={16} />
              <span>{refreshing ? "Refreshing…" : "Refresh"}</span>
            </button>
          )}
          <button type="button" className="management-chip management-logout" onClick={onLogout}>
            Log out
          </button>
        </div>
      </header>

      <div className="management-body">
        {drawerOpen && (
          <button
            type="button"
            className="management-backdrop"
            aria-label="Close menu"
            onClick={() => setDrawerOpen(false)}
          />
        )}
        <nav ref={drawerRef} id="management-sidebar" className={`management-sidebar${drawerOpen ? " is-open" : ""}`} aria-label={role === "teacher" ? "Teacher tools" : "Admin tools"}>
          {items.map((item) => {
            const showGroup = item.group !== currentGroup;
            currentGroup = item.group;
            return (
              <div className="management-nav-block" key={item.id}>
                {showGroup && item.group && <span className="management-nav-label">{item.group}</span>}
                <button
                  type="button"
                  className={`management-nav-item${activeView === item.id ? " active" : ""}`}
                  aria-current={activeView === item.id ? "page" : undefined}
                  onClick={() => selectView(item.id)}
                >
                  <span className="management-nav-icon"><Icon name={legacyIconMap[item.icon] ?? (item.icon as UiIconName)} /></span>
                  <span className="management-nav-text">{item.label}</span>
                  {item.count !== undefined && item.count > 0 && (
                    <strong className={`management-badge${item.hot ? " hot" : ""}`}>{item.count}</strong>
                  )}
                </button>
              </div>
            );
          })}
        </nav>
        <main className="management-main">{children}</main>
      </div>
    </div>
  );
}
