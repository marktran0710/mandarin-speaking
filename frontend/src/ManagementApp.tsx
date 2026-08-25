import { useEffect, useState } from "react";
import AdminApp from "./AdminApp";
import TeacherApp from "./TeacherApp";
import LoginPage from "./pages/LoginPage";
import { loginAdmin } from "./services/database";
import { currentRole } from "./utils/session";
import "./styles/management-login.css";

type ManagementRole = "teacher" | "admin";
const ADMIN_KEY = "adminConsoleSession";

function readRole(): ManagementRole | null {
  if (currentRole("teacher") === "teacher") return "teacher";
  if (localStorage.getItem(ADMIN_KEY) === "true") return "admin";
  return null;
}

function AdminLogin({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await loginAdmin(password);
      localStorage.setItem(ADMIN_KEY, "true");
      onLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not log in.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="management-login admin-login">
      <div className="management-login-card">
        <span className="management-login-mark">華</span>
        <p className="management-login-kicker">Management portal</p>
        <h1>Admin Console</h1>
        <p>Manage accounts, analytics and system operations.</p>
        <form onSubmit={submit}>
          <label>Admin password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" autoFocus /></label>
          <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Enter admin console"}</button>
          {error && <small className="management-login-error">{error}</small>}
        </form>
      </div>
    </main>
  );
}

export default function ManagementApp({ initialRole }: { initialRole?: ManagementRole } = {}) {
  const [role, setRole] = useState<ManagementRole | null>(() => readRole());
  const [loginRole, setLoginRole] = useState<ManagementRole>(() => initialRole ?? readRole() ?? "teacher");

  useEffect(() => {
    if (!role) setRole(readRole());
  }, [role]);

  if (role === "teacher") return <TeacherApp embedded onExit={() => setRole(null)} />;
  if (role === "admin") return <AdminApp embedded onExit={() => setRole(null)} />;

  if (loginRole === "teacher") {
    return (
      <div className="management-login-stage">
        <div className="management-login-switcher" role="tablist" aria-label="Management role">
          <button type="button" className="active" role="tab" aria-selected="true">Teacher</button>
          <button type="button" role="tab" aria-selected="false" onClick={() => setLoginRole("admin")}>Admin</button>
        </div>
        <LoginPage role="teacher" onLogin={() => setRole("teacher")} />
      </div>
    );
  }

  return (
    <div className="management-login-stage">
      <div className="management-login-switcher" role="tablist" aria-label="Management role">
        <button type="button" role="tab" aria-selected="false" onClick={() => setLoginRole("teacher")}>Teacher</button>
        <button type="button" className="active" role="tab" aria-selected="true">Admin</button>
      </div>
      <AdminLogin onLogin={() => setRole("admin")} />
    </div>
  );
}
