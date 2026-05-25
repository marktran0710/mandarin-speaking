import { FormEvent, useState } from "react";
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
      setError("Please enter a name.");
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
    <main className="login-page">
      <section className="login-shell">
        <button type="button" className="login-back" onClick={onBack}>
          Back to portals
        </button>

        <div className="login-card">
          <div className={`login-icon ${isStudent ? "student" : "teacher"}`}>
            {isStudent ? "學" : "師"}
          </div>
          <p className="login-kicker">
            {isStudent ? "Student Portal" : "Teacher Portal"}
          </p>
          <h1>{isStudent ? "學生登入" : "教師登入"}</h1>
          <p className="login-description">
            {isStudent
              ? "Use the default profile or enter a student name to start training."
              : "Use the default profile or enter a teacher name to review progress."}
          </p>

          <form className="login-form" onSubmit={handleSubmit}>
            <label>
              {isStudent ? "Student name" : "Teacher name"}
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={
                  isStudent ? "Enter student name" : "Enter teacher name"
                }
              />
            </label>

            {error && <p className="login-error">{error}</p>}

            <button type="submit" className="login-submit">
              Enter {isStudent ? "Student" : "Teacher"} Mode
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
