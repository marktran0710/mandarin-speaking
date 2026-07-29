import { ReactNode, useState } from "react";
import useColorMode from "../../hooks/useColorMode";
import ToneMark from "../ToneMark";
import "./TeacherShell.css";

/** The six consolidated teacher workspace sections (2026-07 admin-shell
 * redesign — formerly ten flat pill tabs). */
export type TeacherView =
  | "overview"
  | "submissions"
  | "recordingsHelp"
  | "materials"
  | "students"
  | "analytics";

interface SidebarItem {
  id: TeacherView;
  icon: string;
  label: string;
  count?: number;
  /** Marks the badge as needs-attention (seal/red) instead of neutral. */
  hot?: boolean;
}

interface SidebarGroup {
  label: string | null;
  items: SidebarItem[];
}

export default function TeacherShell({
  activeView,
  onSelectView,
  submissionCount,
  openHelpCount,
  refreshing = false,
  onRefresh,
  onLogout,
  children,
}: {
  activeView: TeacherView;
  onSelectView: (view: TeacherView) => void;
  submissionCount: number;
  openHelpCount: number;
  refreshing?: boolean;
  onRefresh?: () => void;
  onLogout: () => void;
  children: ReactNode;
}) {
  const [colorMode, toggleColorMode] = useColorMode();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const groups: SidebarGroup[] = [
    { label: null, items: [{ id: "overview", icon: "📊", label: "Overview" }] },
    {
      label: "Review",
      items: [
        { id: "submissions", icon: "📥", label: "Submissions", count: submissionCount },
        {
          id: "recordingsHelp",
          icon: "🎙️",
          label: "Recordings & Help",
          count: openHelpCount,
          hot: openHelpCount > 0,
        },
      ],
    },
    {
      label: "Teaching",
      items: [
        { id: "materials", icon: "📚", label: "Materials" },
        { id: "students", icon: "🧑‍🎓", label: "Students" },
      ],
    },
    {
      label: "Data",
      items: [{ id: "analytics", icon: "📈", label: "Analytics" }],
    },
  ];

  const selectView = (view: TeacherView) => {
    onSelectView(view);
    setDrawerOpen(false);
  };

  return (
    <div className="tshell">
      <header className="tshell-topbar">
        <button
          type="button"
          className="tshell-menu-toggle"
          aria-label={drawerOpen ? "Close menu" : "Open menu"}
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen((open) => !open)}
        >
          ☰
        </button>
        <div className="tshell-brand">
          <img src="/logo.png" alt="慢慢中文 logo" />
          <span>Teacher Studio</span>
          <ToneMark className="tshell-tonemark" size={22} />
        </div>
        <div className="tshell-topbar-actions">
          <button
            type="button"
            className="tshell-chip"
            onClick={toggleColorMode}
            aria-pressed={colorMode === "dark"}
            title={colorMode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {colorMode === "dark" ? "☀️ Light" : "🌙 Dark"}
          </button>
          {onRefresh && (
            <button
              type="button"
              className="tshell-chip"
              disabled={refreshing}
              onClick={onRefresh}
            >
              {refreshing ? "Refreshing…" : "↺ Refresh"}
            </button>
          )}
          <button type="button" className="tshell-chip tshell-logout" onClick={onLogout}>
            Log out
          </button>
        </div>
      </header>

      <div className="tshell-body">
        {drawerOpen && (
          <div
            className="tshell-backdrop"
            aria-hidden="true"
            onClick={() => setDrawerOpen(false)}
          />
        )}
        <nav
          className={`tshell-sidebar${drawerOpen ? " is-open" : ""}`}
          aria-label="Teacher tools"
        >
          {groups.map((group, groupIndex) => (
            <div className="tshell-nav-group" key={group.label ?? `group-${groupIndex}`}>
              {group.label && <span className="tshell-nav-label">{group.label}</span>}
              {group.items.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className={`tshell-nav-item${activeView === item.id ? " active" : ""}`}
                  aria-current={activeView === item.id ? "page" : undefined}
                  onClick={() => selectView(item.id)}
                >
                  <span className="tshell-nav-icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  <span className="tshell-nav-text">{item.label}</span>
                  {item.count !== undefined && item.count > 0 && (
                    <strong className={`tshell-badge${item.hot ? " hot" : ""}`}>
                      {item.count}
                    </strong>
                  )}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <main className="tshell-main">{children}</main>
      </div>
    </div>
  );
}
