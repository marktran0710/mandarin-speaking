import { BiLabel, BiText } from "./BiLabel";
import ToneMark from "./ToneMark";
import { readSession, signOut, type Role } from "../utils/session";
import "./BiLabel.css";
import "../pages/LoginPage.css";
import "./WrongMode.css";

/** Shown when a session for the *other* role reaches an app: a student
 * session landing on teacher.html, or a teacher session landing on the
 * student site.
 *
 * The only way forward is an explicit sign-out — deliberately no link to
 * the other app, since a one-click hop between modes is exactly what this
 * screen exists to prevent. Signing out reloads this app's own root, which
 * lands on its login screen with a session that is now genuinely empty.
 *
 * Not a security boundary (teacher login has no password and the backend
 * has no auth) — it stops a signed-in student on this device from wandering
 * across, and makes the crossing a visible, deliberate act. */
export default function WrongMode({ expected }: { expected: Role }) {
  const session = readSession();
  const signedInAs = session?.role === "teacher" ? "teacher" : "student";

  const handleSignOut = () => {
    signOut();
    // Full reload rather than a state reset: both apps read the session once
    // on mount, and reloading is the one path that can't leave a stale role
    // in memory behind a now-empty session.
    window.location.reload();
  };

  return (
    <main
      className={`wrong-mode-page ${
        expected === "teacher" ? "expects-teacher" : "expects-student"
      }`}
    >
      <section className="login-shell">
        <div className="login-card">
          <ToneMark className="wrong-mode-tonemark" size={72} />
          <p className="login-kicker">
            <BiLabel zh="換一個身分" pinyin="Huàn yí ge shēnfèn" en="Wrong mode" />
          </p>
          <h1>
            {signedInAs === "student" ? (
              <BiLabel
                zh="你現在是學生"
                pinyin="Nǐ xiànzài shì xuéshēng"
                en="You're signed in as a student"
              />
            ) : (
              <BiLabel
                zh="你現在是老師"
                pinyin="Nǐ xiànzài shì lǎoshī"
                en="You're signed in as a teacher"
              />
            )}
          </h1>
          <p className="login-description">
            <BiText
              zh={
                signedInAs === "student"
                  ? "這裡是老師的地方。要進來，先登出學生帳號。"
                  : "這裡是學生的地方。要進來，先登出老師帳號。"
              }
              pinyin={
                signedInAs === "student"
                  ? "Zhèlǐ shì lǎoshī de dìfāng. Yào jìnlái, xiān dēngchū xuéshēng zhànghào."
                  : "Zhèlǐ shì xuéshēng de dìfāng. Yào jìnlái, xiān dēngchū lǎoshī zhànghào."
              }
              en={
                signedInAs === "student"
                  ? "This side is for teachers. Sign out of the student account to continue."
                  : "This side is for students. Sign out of the teacher account to continue."
              }
            />
          </p>
          {session?.name && <p className="wrong-mode-who">{session.name}</p>}

          <button type="button" className="login-submit" onClick={handleSignOut}>
            <BiLabel zh="登出" pinyin="Dēngchū" en="Sign out" />
          </button>
        </div>
      </section>
    </main>
  );
}
