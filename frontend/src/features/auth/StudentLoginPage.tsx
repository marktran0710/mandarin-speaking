import { FormEvent, useState } from "react";
import ToneMark from "../../components/tone/ToneMark";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import "./LoginPage.css";
import "./StudentLoginPage.css";
import { loginStudent, registerStudent } from "../../services/database";
import { studentUiCopy } from "../../i18n/student-ui-copy";
import { signIn } from "../../utils/session";
import StudentIcon from "../../components/navigation/StudentIcon";
import SourceAttribution from "@shared/ui/SourceAttribution";

type Mode = "login" | "signup";
type LoginError = "empty" | "password" | "inactive" | "resetRequired" | "server";
type SignupError = "nameTaken" | "nameInvalid" | "passwordInvalid" | "tooMany";
type FormError = LoginError | SignupError;

/** Sort a failed signup into the one message the student can act on: the name
 * is taken, the name or the password is refused, or they should wait. */
function signupError(err: unknown): FormError {
  const { status, detail } = err as { status?: number; detail?: string };
  if (status === 409) return "nameTaken";
  if (status === 429) return "tooMany";
  if (status === 400 && /name/i.test(detail ?? "")) return "nameInvalid";
  if (status === 400 || status === 422) return "passwordInvalid";
  return "server";
}

/** Dedicated student sign-in, with a basic name + password signup on the same
 * page: a new account is created and signed in at once. */
export default function StudentLoginPage({
  onLogin,
}: {
  onLogin: () => void;
}) {
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [busy, setBusy] = useState(false);
  const signingUp = mode === "signup";

  const startSession = (finalName: string, studentId?: string) => {
    signIn("student", finalName, studentId);
    onLogin();
  };

  const switchMode = () => {
    setMode(signingUp ? "login" : "signup");
    setError(null);
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
      const student = signingUp
        ? await registerStudent({ name: trimmed, password })
        : await loginStudent({ name: trimmed, password });
      startSession(student.name, student.id);
    } catch (err) {
      if (signingUp) {
        setError(signupError(err));
        return;
      }
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
            <StudentSystemText k={signingUp ? "createAccount" : "studentLogin"} />
          </h1>
          <p className="login-description">
            <StudentSystemText k={signingUp ? "createAccountDescription" : "loginDescription"} />
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
                  placeholder={signingUp ? studentUiCopy.choosePasswordPlaceholder.zh : "輸入教師提供的密碼"}
                  autoComplete={signingUp ? "new-password" : "current-password"}
                  aria-invalid={error === "password" || error === "passwordInvalid" || undefined}
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
                {error === "nameTaken" && <StudentSystemText k="signupNameTakenError" />}
                {error === "nameInvalid" && <StudentSystemText k="signupNameError" />}
                {error === "passwordInvalid" && <StudentSystemText k="signupPasswordError" />}
                {error === "tooMany" && <StudentSystemText k="signupTooManyError" />}
              </p>
            )}

            <button type="submit" className="login-submit" disabled={busy}>
              <StudentSystemText k={signingUp ? "createAccountAndStart" : "enterStudentMode"} withinControl />
            </button>
            <button type="button" className="login-switch" onClick={switchMode} disabled={busy}>
              <StudentSystemText k={signingUp ? "switchToLogin" : "switchToSignup"} withinControl />
            </button>
          </form>
        </div>
      </section>
      <SourceAttribution />
    </main>
  );
}
