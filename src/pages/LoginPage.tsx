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
  const [error, setError] = useState(false);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();

    if (!name.trim()) {
      setError(true);
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
            <BiLabel k={isStudent ? "student_portal" : "teacher_portal"} />
          </p>
          <h1>
            <BiLabel k={isStudent ? "student_login" : "teacher_login"} />
          </h1>
          <p className="login-description">
            <BiText
              zh={isStudent
                ? "你可以直接開始，或打上你的名字再開始練習。"
                : "使用預設帳號或輸入教師姓名查看學習進度。"}
              pinyin={isStudent
                ? "Nǐ kěyǐ zhíjiē kāishǐ, huò dǎshàng nǐ de míngzi zài kāishǐ liànxí."
                : "Shǐyòng yùshè zhànghào huò shūrù jiàoshī xìngmíng chákàn xuéxí jìndù."}
              en={isStudent
                ? "You can start right away, or type your name to begin practicing."
                : "Use the default profile or enter a teacher name to review progress."}
            />
          </p>

          <form className="login-form" onSubmit={handleSubmit}>
            <label>
              <BiLabel
                zh={isStudent ? "學生名字" : "教師姓名"}
                pinyin={isStudent ? "Xuéshēng míngzi" : "Jiàoshī xìngmíng"}
                en={isStudent ? "Student name" : "Teacher name"}
              />
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={isStudent ? "打上學生的名字 · Enter student name" : "輸入教師姓名 · Enter teacher name"}
              />
            </label>

            {error && (
              <p className="login-error">
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
