import { FormEvent, useState } from "react";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";
import "./LoginPage.css";

export type LoginRole = "student" | "teacher";

interface LoginPageProps {
  role: LoginRole;
  onLogin: (role: LoginRole) => void;
  onBack: () => void;
}

export default function LoginPage({ role, onLogin, onBack }: LoginPageProps) {
  const isStudent = role === "student";
  const defaultName = isStudent ? "Student Demo" : "Teacher Demo";
  const [name, setName] = useState(defaultName);
  const [error, setError] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();

    if (!name.trim()) {
      setError("請輸入名稱 · Please enter a name.");
      return;
    }

    localStorage.setItem(
      `${role}Session`,
      JSON.stringify({
        name: name.trim(),
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
          <div className={`login-icon ${isStudent ? "student" : "teacher"}`}>
            {isStudent ? "學" : "師"}
          </div>
          <p className="login-kicker">
            <BiLabel zh={isStudent ? "學生入口" : "教師入口"} en={isStudent ? "Student Portal" : "Teacher Portal"} />
          </p>
          <h1>{isStudent ? "學生登入" : "教師登入"}</h1>
          <p className="login-description">
            <BiText
              zh={isStudent
                ? "使用預設帳號或輸入學生姓名開始練習。"
                : "使用預設帳號或輸入教師姓名查看學習進度。"}
              en={isStudent
                ? "Use the default profile or enter a student name to start training."
                : "Use the default profile or enter a teacher name to review progress."}
            />
          </p>

          <form className="login-form" onSubmit={handleSubmit}>
            <label>
              <BiLabel zh={isStudent ? "學生姓名" : "教師姓名"} en={isStudent ? "Student name" : "Teacher name"} />
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={isStudent ? "輸入學生姓名 · Enter student name" : "輸入教師姓名 · Enter teacher name"}
              />
            </label>

            {error && <p className="login-error">{error}</p>}

            <button type="submit" className="login-submit">
              <BiLabel
                zh={isStudent ? "進入學生模式" : "進入教師模式"}
                en={isStudent ? "Enter Student Mode" : "Enter Teacher Mode"}
              />
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
