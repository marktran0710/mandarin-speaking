import { type ReactNode, useState } from "react";
import useColorMode from "../../hooks/useColorMode";
import ToneMark from "../ToneMark";
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

const DEFAULT_TEACHER_ITEMS: ManagementNavItem[] = [
  { id: "overview", label: "Overview", icon: "📊" },
  { id: "submissions", label: "Submissions", icon: "📥", group: "Review" },
  { id: "recordingsHelp", label: "Recordings & Help", icon: "🎙️", group: "Review" },
  { id: "materials", label: "Materials", icon: "📚", group: "Teaching" },
  { id: "analytics", label: "Analytics", icon: "📈", group: "Data" },
];

const DEFAULT_ADMIN_ITEMS: ManagementNavItem[] = [
  { id: "Admin Home", label: "Admin Home", icon: "⌂" },
  { id: "Teachers", label: "Teachers", icon: "◉", group: "Accounts" },
  { id: "Students", label: "Students", icon: "◎", group: "Accounts" },
  { id: "IRT / Student analytics", label: "IRT / Student analytics", icon: "◌", group: "Insights" },
  { id: "Practice Debug", label: "Practice Debug", icon: "⌁", group: "Insights" },
];

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
  const items = (navItems ?? (role === "teacher" ? DEFAULT_TEACHER_ITEMS : DEFAULT_ADMIN_ITEMS)).map((item) => ({
    ...item,
    count: item.id === "submissions" ? submissionCount : item.id === "recordingsHelp" ? openHelpCount : item.count,
    hot: item.id === "recordingsHelp" ? openHelpCount > 0 : item.hot,
  }));

  let currentGroup: string | undefined;

  const selectView = (view: string) => {
    onSelectView(view);
    setDrawerOpen(false);
  };

  return (
    <div className={`management-shell management-role-${role}`}>
      <header className="management-topbar">
        <button
          type="button"
          className="management-menu-toggle"
          aria-label={drawerOpen ? "Close menu" : "Open menu"}
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen((open) => !open)}
        >
          ☰
        </button>
        <div className="management-brand">
          <img src="/logo.png" alt="慢慢中文 logo" />
          <span>慢慢中文</span>
          <small>{role === "teacher" ? "Teacher Studio" : "Admin Console"}</small>
          <ToneMark className="management-tonemark" size={20} />
        </div>
        <div className="management-topbar-actions">
          <span className="management-role-badge">{role === "teacher" ? "Teacher" : "Admin"}</span>
          <button
            type="button"
            className="management-chip"
            onClick={toggleColorMode}
            aria-pressed={colorMode === "dark"}
          >
            {colorMode === "dark" ? "☀️ Light" : "🌙 Dark"}
          </button>
          {onRefresh && (
            <button type="button" className="management-chip" disabled={refreshing} onClick={onRefresh}>
              {refreshing ? "Refreshing…" : "↺ Refresh"}
            </button>
          )}
          <button type="button" className="management-chip management-logout" onClick={onLogout}>
            Log out
          </button>
        </div>
      </header>

      <div className="management-body">
        {drawerOpen && <div className="management-backdrop" aria-hidden="true" onClick={() => setDrawerOpen(false)} />}
        <nav className={`management-sidebar${drawerOpen ? " is-open" : ""}`} aria-label={role === "teacher" ? "Teacher tools" : "Admin tools"}>
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
                  <span className="management-nav-icon" aria-hidden="true">{item.icon}</span>
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
