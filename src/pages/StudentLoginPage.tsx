import { FormEvent, useEffect, useState } from "react";
import { BiLabel, BiText } from "../components/BiLabel";
import ToneMark from "../components/ToneMark";
import "../components/BiLabel.css";
import "./LoginPage.css";
import {
  canUseDatabase,
  createStudent,
  listStudents,
  loginStudent,
  type Student,
} from "../services/database";

const NEW_STUDENT_VALUE = "__new__";
const DEFAULT_PASSWORD = "123456";

/** Dedicated student sign-in: pick (or type) your name, enter the password
 * (default 123456 for every student, teacher-resettable in the backend).
 * The teacher page keeps the old passwordless LoginPage.
 *
 * A classroom friction gate, not real auth — verification happens against
 * the roster's plaintext password column; without a backend it falls back
 * to the shared default so offline demos still work. */
export default function StudentLoginPage({
  onLogin,
  onBack,
}: {
  onLogin: () => void;
  onBack: () => void;
}) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<"empty" | "password" | "server" | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  const [roster, setRoster] = useState<Student[]>([]);
  const [selectedId, setSelectedId] = useState<string>(NEW_STUDENT_VALUE);
  const [rosterError, setRosterError] = useState(false);
  const [nameTouched, setNameTouched] = useState(false);

  useEffect(() => {
    if (!canUseDatabase()) return;
    listStudents()
      .then((students) => {
        setRoster(students);
        if (students.length > 0 && !nameTouched) {
          setSelectedId(students[0].id);
          setName(students[0].name);
        }
      })
      .catch(() => setRosterError(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const usingRoster = canUseDatabase() && !rosterError;

  const startSession = (finalName: string, studentId?: string) => {
    localStorage.setItem(
      "studentSession",
      JSON.stringify({
        name: finalName,
        id: studentId,
        signedInAt: new Date().toISOString(),
      }),
    );
    onLogin();
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || !password) {
      setError("empty");
      return;
    }

    // The admin demo backdoor stays off the roster — checking it locally
    // avoids creating an "admin" student the teacher would see.
    const isAdminName = trimmed.toLowerCase() === "admin";
    if (isAdminName || !usingRoster) {
      if (password !== DEFAULT_PASSWORD) {
        setError("password");
        return;
      }
      startSession(trimmed);
      return;
    }

    setBusy(true);
    setError(null);
    try {
      if (selectedId !== NEW_STUDENT_VALUE) {
        const student = await loginStudent({
          studentId: selectedId,
          password,
        });
        startSession(student.name, student.id);
        return;
      }
      // New name: joining the roster requires the shared default password —
      // checked before the record is created so a typo'd password doesn't
      // add a stray student.
      if (password !== DEFAULT_PASSWORD) {
        setError("password");
        return;
      }
      const created = await createStudent(trimmed);
      startSession(created.name, created.id);
    } catch (err) {
      if ((err as { wrongCredentials?: boolean }).wrongCredentials) {
        setError("password");
      } else {
        setError("server");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login-page student">
      <section className="login-shell">
        <button type="button" className="login-back" onClick={onBack}>
          <BiLabel k="back_to_portals" />
        </button>

        <div className="login-card">
          <ToneMark className="login-tonemark" size={72} animated />
          <p className="login-kicker">
            <BiLabel k="student_portal" />
          </p>
          <h1>
            <BiLabel k="student_login" />
          </h1>
          <p className="login-description">
            <BiText
              zh="選你的名字，輸入密碼再開始練習。"
              pinyin="Xuǎn nǐ de míngzi, shūrù mìmǎ zài kāishǐ liànxí."
              en="Pick your name and enter your password to begin practicing."
            />
          </p>

          <form className="login-form" onSubmit={handleSubmit}>
            {usingRoster && roster.length > 0 && selectedId !== NEW_STUDENT_VALUE ? (
              <label>
                <BiLabel zh="學生名字" pinyin="Xuéshēng míngzi" en="Student name" />
                <select
                  value={selectedId}
                  onChange={(event) => {
                    const next = event.target.value;
                    setNameTouched(true);
                    setSelectedId(next);
                    if (next !== NEW_STUDENT_VALUE) {
                      const match = roster.find((s) => s.id === next);
                      setName(match?.name ?? "");
                    } else {
                      setName("");
                    }
                  }}
                >
                  {roster.map((student) => (
                    <option key={student.id} value={student.id}>
                      {student.name}
                    </option>
                  ))}
                  <option value={NEW_STUDENT_VALUE}>+ 其他人 · Someone new</option>
                </select>
              </label>
            ) : (
              <label>
                <BiLabel zh="學生名字" pinyin="Xuéshēng míngzi" en="Student name" />
                <input
                  value={name}
                  onChange={(event) => {
                    setNameTouched(true);
                    setName(event.target.value);
                  }}
                  placeholder="打上學生的名字 · Enter student name"
                  autoComplete="username"
                />
              </label>
            )}

            <label>
              <BiLabel zh="密碼" pinyin="Mìmǎ" en="Password" />
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="預設 123456 · Default 123456"
                autoComplete="current-password"
                aria-invalid={error === "password" || undefined}
              />
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
