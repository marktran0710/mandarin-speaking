import { FormEvent, useState } from "react";
import { BiLabel, BiText } from "../components/BiLabel";
import ToneMark from "../components/ToneMark";
import "../components/BiLabel.css";
import "./LoginPage.css";
import "./StudentLoginPage.css";
import { loginStudent } from "../services/database";
import { signIn } from "../utils/session";
import StudentIcon from "../components/StudentIcon";

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
  const [error, setError] = useState<"empty" | "password" | "server" | null>(
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
      const flags = err as { wrongCredentials?: boolean };
      if (flags.wrongCredentials) {
        setError("password");
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
            <BiLabel k="student_portal" />
          </p>
          <h1>
            <BiLabel k="student_login" />
          </h1>
          <p className="login-description">
            <BiText
              zh="輸入你的名字和密碼，開始練習。"
              pinyin="Shūrù nǐ de míngzi hé mìmǎ, kāishǐ liànxí."
              en="Enter your name and password to begin practicing."
            />
          </p>

          <ol className="login-trail" aria-label="Sign-in steps">
            <li className={trailState(1)}>
              <span className="login-trail-dot" aria-hidden="true">{step1Done ? <StudentIcon name="check" size={15} /> : "1"}</span>
              <span className="login-trail-label">
                <span lang="zh-Hant">輸入名字</span>
                <small lang="en">Name</small>
              </span>
            </li>
            <li className={trailState(2)}>
              <span className="login-trail-dot" aria-hidden="true">{step2Done ? <StudentIcon name="check" size={15} /> : "2"}</span>
              <span className="login-trail-label">
                <span lang="zh-Hant">輸入密碼</span>
                <small lang="en">Password</small>
              </span>
            </li>
            <li className={trailState(3)}>
              <span className="login-trail-dot" aria-hidden="true">3</span>
              <span className="login-trail-label">
                <span lang="zh-Hant">開始練習</span>
                <small lang="en">Start</small>
              </span>
            </li>
          </ol>

          <form className="login-form" onSubmit={handleSubmit}>
            <label htmlFor="student-name">
              <BiLabel zh="學生名字" pinyin="Xuéshēng míngzi" en="Student name" />
              <input
                id="student-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="打上你的名字 · Enter your name"
                autoComplete="username"
              />
            </label>

            <label htmlFor="student-password">
              <BiLabel zh="密碼" pinyin="Mìmǎ" en="Password" />
              <div className="login-password-field">
                <input
                  id="student-password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="輸入教師提供的密碼 · Enter your password"
                  autoComplete="current-password"
                  aria-invalid={error === "password" || undefined}
                />
                <button
                  type="button"
                  className="login-password-toggle"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-label={showPassword ? "隱藏密碼 · Hide password" : "顯示密碼 · Show password"}
                >
                  <StudentIcon name={showPassword ? "eye-off" : "eye"} size={18} />
                </button>
              </div>
            </label>

            {error && (
              <p className="login-error" role="alert">
                {error === "empty" && (
                  <BiLabel
                    zh="請輸入名字和密碼。"
                    pinyin="Qǐng shūrù míngzi hé mìmǎ."
                    en="Please enter a name and password."
                  />
                )}
                {error === "password" && (
                  <BiLabel
                    zh="密碼不對，再試一次。"
                    pinyin="Mìmǎ bú duì, zài shì yí cì."
                    en="Wrong password — try again."
                  />
                )}
                {error === "server" && (
                  <BiLabel
                    zh="連不上伺服器，等一下再試。"
                    pinyin="Lián bú shàng fúwùqì, děng yíxià zài shì."
                    en="Could not reach the server — try again in a moment."
                  />
                )}
              </p>
            )}

            <button type="submit" className="login-submit" disabled={busy}>
              <BiLabel
                zh="進入學生模式"
                pinyin="Jìnrù xuéshēng móshì"
                en="Enter Student Mode"
              />
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
