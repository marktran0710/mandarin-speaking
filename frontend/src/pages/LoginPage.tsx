import { FormEvent, useEffect, useState } from "react";
import { BiLabel, BiText } from "../components/BiLabel";
import ToneMark from "../components/tone/ToneMark";
import ToneField from "../components/tone/ToneField";
import "../components/BiLabel.css";
import "./LoginPage.css";
import { canUseDatabase, listStudents, loginStudent, loginTeacher, type Student } from "../services/database";
import { signIn } from "../utils/session";

export type LoginRole = "student" | "teacher";

interface LoginPageProps {
  role: LoginRole;
  onLogin: (role: LoginRole) => void;
  /** Omit to render no back button. The teacher app does exactly that —
   * it has no route to the student site by design. */
  onBack?: () => void;
}

export default function LoginPage({ role, onLogin, onBack }: LoginPageProps) {
  const isStudent = role === "student";
  const defaultName = isStudent ? "Student Demo" : "Teacher Demo";
  const [name, setName] = useState(defaultName);
  const [error, setError] = useState(false);
  const [password, setPassword] = useState("");

  // Student roster — a stable id per student instead of a free-typed name,
  // so per-student practice data (quiz attempts, tone scores) can actually
  // be joined and analyzed. Teacher login stays free-text (out of scope).
  const [roster, setRoster] = useState<Student[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [rosterError, setRosterError] = useState(false);
  // The roster loads asynchronously, after the free-text input has already
  // rendered — if a student starts typing before it resolves, the roster
  // picker swapping in shouldn't discard what they typed.
  const [nameTouched, setNameTouched] = useState(false);

  useEffect(() => {
    if (!isStudent || !canUseDatabase()) return;
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
  }, [isStudent]);

  const usingRoster = isStudent && canUseDatabase() && !rosterError;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();

    const trimmed = name.trim();
    if (!trimmed) {
      setError(true);
      return;
    }

    if (!isStudent) {
      try {
        const teacher = await loginTeacher(trimmed, password);
        signIn("teacher", teacher.name, teacher.id);
        onLogin(role);
      } catch {
        setError(true);
      }
      return;
    }

    try {
      const student = await loginStudent(
        selectedId && usingRoster
          ? { studentId: selectedId, password }
          : { name: trimmed, password },
      );
      signIn("student", student.name, student.id);
      onLogin(role);
    } catch {
      setError(true);
    }
  };

  return (
    <main className={`login-page ${isStudent ? "student" : "teacher"}`}>
      <ToneField variant={isStudent ? "student" : "teacher"} />
      <section className="login-shell">
        {onBack && (
          <button type="button" className="login-back" onClick={onBack}>
            <BiLabel k="back_to_portals" />
          </button>
        )}

        <div className="login-card">
          <ToneMark className="login-tonemark" size={isStudent ? 96 : 80} animated />
          <p className="login-kicker">
            <BiLabel k={isStudent ? "student_portal" : "teacher_portal"} />
          </p>
          <h1>
            <BiLabel k={isStudent ? "student_login" : "teacher_login"} />
          </h1>
          <p className="login-description">
            <BiText
              zh={isStudent
                ? "從名單選你的名字，使用管理員提供的密碼開始練習。"
                : "使用預設帳號或輸入教師姓名查看學習進度。"}
              pinyin={isStudent
                ? "Cóng míngdān xuǎn nǐ de míngzi, shǐyòng guǎnlǐyuán tígōng de mìmǎ kāishǐ liànxí."
                : "Shǐyòng yùshè zhànghào huò shūrù jiàoshī xìngmíng chákàn xuéxí jìndù."}
              en={isStudent
                ? "Pick your name from the list and use the password provided by your admin."
                : "Use the default profile or enter a teacher name to review progress."}
            />
          </p>

          <form className="login-form" onSubmit={handleSubmit}>
            {usingRoster && roster.length > 0 && (
              <label>
                <BiLabel zh="學生名字" pinyin="Xuéshēng míngzi" en="Student name" />
                <select
                  value={selectedId}
                  onChange={(event) => {
                    const next = event.target.value;
                    setNameTouched(true);
                    setSelectedId(next);
                    const match = roster.find((s) => s.id === next);
                    setName(match?.name ?? "");
                  }}
                >
                  {roster.map((student) => (
                    <option key={student.id} value={student.id}>
                      {student.name}
                    </option>
                  ))}
                </select>
              </label>
            )}

            {(!usingRoster || roster.length === 0) && (
              <label>
                <BiLabel
                  zh={isStudent ? "學生名字" : "教師姓名"}
                  pinyin={isStudent ? "Xuéshēng míngzi" : "Jiàoshī xìngmíng"}
                  en={isStudent ? "Student name" : "Teacher name"}
                />
                <input
                  value={name}
                  onChange={(event) => {
                    setNameTouched(true);
                    setName(event.target.value);
                  }}
                  placeholder={isStudent ? "打上學生的名字 · Enter student name" : "輸入教師姓名 · Enter teacher name"}
                  aria-invalid={error || undefined}
                  aria-describedby={error ? "login-name-error" : undefined}
                />
              </label>
            )}

            <label>
              <BiLabel
                zh="密碼"
                pinyin="Mìmǎ"
                en={isStudent ? "Student password" : "Teacher password"}
              />
              <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
            </label>

            {error && (
              <p className="login-error" id="login-name-error" role="alert">
                <BiLabel k="please_enter_a_name" />
              </p>
            )}

            <button type="submit" className="login-submit">
              <BiLabel
                zh={isStudent ? "進入學生模式" : "進入教師模式"}
                pinyin={isStudent ? "Jìnrù xuéshēng móshì" : "Jìnrù jiàoshī móshì"}
                en={isStudent ? "Enter Student Mode" : "Enter Teacher Mode"}
              />
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
