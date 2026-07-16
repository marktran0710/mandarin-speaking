import { FormEvent, useEffect, useState } from "react";
import { BiLabel, BiText } from "../components/BiLabel";
import ToneMark from "../components/ToneMark";
import "../components/BiLabel.css";
import "./LoginPage.css";
import { canUseDatabase, createStudent, listStudents, type Student } from "../services/database";

export type LoginRole = "student" | "teacher";

interface LoginPageProps {
  role: LoginRole;
  onLogin: (role: LoginRole) => void;
  onBack: () => void;
}

const NEW_STUDENT_VALUE = "__new__";

export default function LoginPage({ role, onLogin, onBack }: LoginPageProps) {
  const isStudent = role === "student";
  const defaultName = isStudent ? "Student Demo" : "Teacher Demo";
  const [name, setName] = useState(defaultName);
  const [error, setError] = useState(false);

  // Student roster — a stable id per student instead of a free-typed name,
  // so per-student practice data (quiz attempts, tone scores) can actually
  // be joined and analyzed. Teacher login stays free-text (out of scope).
  const [roster, setRoster] = useState<Student[]>([]);
  const [selectedId, setSelectedId] = useState<string>(NEW_STUDENT_VALUE);
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

    let studentId: string | undefined;
    if (usingRoster) {
      if (selectedId !== NEW_STUDENT_VALUE) {
        studentId = selectedId;
      } else {
        // New name, not yet on the roster — add it so it gets a stable id
        // going forward. A save failure shouldn't block sign-in; the
        // student just falls back to name-only for this session.
        try {
          const created = await createStudent(trimmed);
          studentId = created.id;
        } catch {
          /* fall back to name-only below */
        }
      }
    }

    localStorage.setItem(
      `${role}Session`,
      JSON.stringify({
        name: trimmed,
        id: studentId,
        signedInAt: new Date().toISOString(),
      }),
    );
    onLogin(role);
  };

  return (
    <main className={`login-page ${isStudent ? "student" : "teacher"}`}>
      <section className="login-shell">
        <button type="button" className="login-back" onClick={onBack}>
          <BiLabel k="back_to_portals" />
        </button>

        <div className="login-card">
          <ToneMark className="login-tonemark" size={72} animated />
          <p className="login-kicker">
            <BiLabel k={isStudent ? "student_portal" : "teacher_portal"} />
          </p>
          <h1>
            <BiLabel k={isStudent ? "student_login" : "teacher_login"} />
          </h1>
          <p className="login-description">
            <BiText
              zh={isStudent
                ? "從名單選你的名字，或加入新名字再開始練習。"
                : "使用預設帳號或輸入教師姓名查看學習進度。"}
              pinyin={isStudent
                ? "Cóng míngdān xuǎn nǐ de míngzi, huò jiārù xīn míngzi zài kāishǐ liànxí."
                : "Shǐyòng yùshè zhànghào huò shūrù jiàoshī xìngmíng chákàn xuéxí jìndù."}
              en={isStudent
                ? "Pick your name from the list, or add yourself to begin practicing."
                : "Use the default profile or enter a teacher name to review progress."}
            />
          </p>

          <form className="login-form" onSubmit={handleSubmit}>
            {usingRoster && roster.length > 0 && selectedId !== NEW_STUDENT_VALUE && (
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
                  <option value={NEW_STUDENT_VALUE}>
                    {isStudent ? "+ 其他人 · Someone new" : "+ Someone new"}
                  </option>
                </select>
              </label>
            )}

            {(!usingRoster || roster.length === 0 || selectedId === NEW_STUDENT_VALUE) && (
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
