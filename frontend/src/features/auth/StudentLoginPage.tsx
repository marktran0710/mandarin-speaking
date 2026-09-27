import { FormEvent, useState } from "react";
import ToneMark from "../../components/tone/ToneMark";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import "./LoginPage.css";
import "./StudentLoginPage.css";
import { loginStudent } from "../../services/database";
import { signIn } from "../../utils/session";
import StudentIcon from "../../components/navigation/StudentIcon";
import SourceAttribution from "@shared/ui/SourceAttribution";

/** Dedicated student sign-in. Student accounts are provisioned by an admin;
 * the public student portal never creates roster accounts. */
export default function StudentLoginPage({
  onLogin,
}: {
  onLogin: () => void;
}) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<"empty" | "password" | "inactive" | "resetRequired" | "server" | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  const startSession = (finalName: string, studentId?: string) => {
    signIn("student", finalName, studentId);
    onLogin();
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || !password) {
      setError("empty");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const student = await loginStudent({ name: trimmed, password });
      startSession(student.name, student.id);
    } catch (err) {
      const flags = err as { wrongCredentials?: boolean; status?: number; detail?: string };
      if (flags.wrongCredentials) {
        setError("password");
      } else if (flags.status === 403 && flags.detail?.toLowerCase().includes("reset")) {
        setError("resetRequired");
      } else if (flags.status === 403) {
        setError("inactive");
      } else {
        setError("server");
      }
    } finally {
      setBusy(false);
    }
  };

  const step1Done = name.trim().length > 0;
  const step2Done = password.length > 0;
  const trailState = (step: 1 | 2 | 3) => {
    if (step === 1) return step1Done ? "is-done" : "is-active";
    if (step === 2) return !step1Done ? "" : step2Done ? "is-done" : "is-active";
    return step1Done && step2Done ? "is-active" : "";
  };

  return (
    <main className="login-page student">
      <section className="login-shell">
        <div className="login-card">
          <ToneMark className="login-tonemark" size={96} animated />
          <p className="login-kicker">
            <StudentSystemText k="studentPortal" />
          </p>
          <h1>
            <StudentSystemText k="studentLogin" />
          </h1>
          <p className="login-description">
            <StudentSystemText k="loginDescription" />
          </p>

          <ol className="login-trail" aria-label="登入步驟">
            <li className={trailState(1)}>
              <span className="login-trail-dot" aria-hidden="true">{step1Done ? <StudentIcon name="check" size={15} /> : "1"}</span>
              <span className="login-trail-label">
                <StudentSystemText k="enterName" />
              </span>
            </li>
            <li className={trailState(2)}>
              <span className="login-trail-dot" aria-hidden="true">{step2Done ? <StudentIcon name="check" size={15} /> : "2"}</span>
              <span className="login-trail-label">
                <StudentSystemText k="enterPassword" />
              </span>
            </li>
            <li className={trailState(3)}>
              <span className="login-trail-dot" aria-hidden="true">3</span>
              <span className="login-trail-label">
                <StudentSystemText k="startPractice" />
              </span>
            </li>
          </ol>

          <form className="login-form" onSubmit={handleSubmit}>
            <label htmlFor="student-name">
              <StudentSystemText k="studentName" />
              <input
                id="student-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="打上你的名字"
                autoComplete="username"
              />
            </label>

            <label htmlFor="student-password">
              <StudentSystemText k="password" />
              <div className="login-password-field">
                <input
                  id="student-password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="輸入教師提供的密碼"
                  autoComplete="current-password"
                  aria-invalid={error === "password" || undefined}
                />
                <button
                  type="button"
                  className="login-password-toggle"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-label={showPassword ? "隱藏密碼" : "顯示密碼"}
                >
                  <StudentIcon name={showPassword ? "eye-off" : "eye"} size={18} />
                </button>
              </div>
            </label>

            {error && (
              <p className="login-error" role="alert">
                {error === "empty" && (
                  <StudentSystemText k="loginEmptyError" />
                )}
                {error === "password" && (
                  <StudentSystemText k="loginPasswordError" />
                )}
                {error === "resetRequired" && (
                  <StudentSystemText k="loginResetRequiredError" />
                )}
                {error === "inactive" && (
                  <StudentSystemText k="loginInactiveError" />
                )}
                {error === "server" && (
                  <StudentSystemText k="loginServerError" />
                )}
              </p>
            )}

            <button type="submit" className="login-submit" disabled={busy}>
              <StudentSystemText k="enterStudentMode" withinControl />
            </button>
          </form>
        </div>
      </section>
      <SourceAttribution />
    </main>
  );
}
