import { useEffect, useMemo, useState } from "react";
import {
  canUseDatabase,
  createStudent,
  createTeacher,
  listAudioRecords,
  listStudents,
  listTeachers,
  listVocabQuizAttempts,
  type Student,
  type Teacher,
  type VocabQuizAttempt,
} from "./services/database";
import AdminIrtStudentPanel from "./components/AdminIrtStudentPanel";
import TeacherBenchmarkPage from "./pages/TeacherBenchmarkPage";
import type { AudioRecord } from "./pages/MyStoriesPage";
import TeacherPracticeDebugPage from "./pages/TeacherPracticeDebugPage";
import "./admin.css";

type Role = "Teacher" | "Student";
type Account = { id: string; name: string; role: Role; status: "Active" | "Inactive" };
const ADMIN_KEY = "adminConsoleSession";
const NAV_ITEMS = [
  "Admin Home",
  "Teachers",
  "Students",
  "IRT / Student analytics",
  "Practice Debug",
  "Benchmark",
] as const;

export default function AdminApp() {
  const [authenticated, setAuthenticated] = useState(() => localStorage.getItem(ADMIN_KEY) === "true");
  const [password, setPassword] = useState("");
  const [activeNav, setActiveNav] = useState<(typeof NAV_ITEMS)[number]>("Admin Home");
  const [students, setStudents] = useState<Student[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [quizAttempts, setQuizAttempts] = useState<VocabQuizAttempt[]>([]);
  const [audioRecords, setAudioRecords] = useState<AudioRecord[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [newName, setNewName] = useState("");
  const [newPassword, setNewPassword] = useState("123456");

  const refresh = async () => {
    if (!canUseDatabase()) {
      setError("Backend is not configured.");
      return;
    }
    try {
      const [studentRows, teacherRows, attempts] = await Promise.all([
        listStudents(),
        listTeachers(),
        listVocabQuizAttempts(),
      ]);
      setStudents(studentRows);
      setTeachers(teacherRows);
      setQuizAttempts(attempts);
      setError("");
    } catch {
      setError("Could not load data from the backend.");
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (activeNav !== "Practice Debug" || !canUseDatabase()) return;
    void listAudioRecords({ limit: 1000 })
      .then(setAudioRecords)
      .catch(() => setError("Could not load audio records from the backend."));
  }, [activeNav]);

  const accounts = useMemo<Account[]>(
    () => [
      ...teachers.map((teacher) => ({
        id: teacher.id,
        name: teacher.name,
        role: "Teacher" as const,
        status: teacher.status === "active" ? "Active" as const : "Inactive" as const,
      })),
      ...students.map((student) => ({
        id: student.id,
        name: student.name,
        role: "Student" as const,
        status: "Active" as const,
      })),
    ],
    [students, teachers],
  );
  const sectionRole = activeNav === "Teachers" ? "Teacher" : activeNav === "Students" ? "Student" : null;
  const filtered = accounts.filter(
    (account) => account.name.toLowerCase().includes(query.toLowerCase()) && (!sectionRole || account.role === sectionRole),
  );

  const login = (event: React.FormEvent) => {
    event.preventDefault();
    if (password === "admin123") {
      localStorage.setItem(ADMIN_KEY, "true");
      setAuthenticated(true);
    }
  };
  const addAccount = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newName.trim()) return;
    try {
      if (activeNav === "Teachers") {
        const created = await createTeacher(newName.trim(), newPassword);
        setTeachers((current) => [...current, created]);
      } else {
        const created = await createStudent(newName.trim(), newPassword);
        setStudents((current) => [...current, created]);
      }
      setNewName("");
    } catch {
      setError("Could not create account.");
    }
  };

  if (!authenticated) {
    return <main className="admin-login"><h1>Account Control Center</h1><p>Administrator access.</p><form onSubmit={login}><label>Admin password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoFocus /></label><button>Enter admin console</button><small>Basic password: admin123</small></form></main>;
  }

  const heading = activeNav === "IRT / Student analytics" ? "IRT / Student analytics" : activeNav === "Practice Debug" ? "Practice Stage Debugger" : activeNav === "Benchmark" ? "External Benchmark" : "Account Control Center";
  const description = activeNav === "IRT / Student analytics" ? "Track student ability, response quality and calibration readiness." : activeNav === "Practice Debug" ? "Trace student attempts through the scoring pipeline." : activeNav === "Benchmark" ? "Validate tone scoring against the expert-rated corpus." : "Manage real teacher and student accounts.";

  return <div className="admin-shell"><aside className="admin-sidebar"><div className="admin-brand"><span>華</span><strong>中文學習</strong></div><nav>{NAV_ITEMS.map((item) => <button className={activeNav === item ? "active" : ""} key={item} onClick={() => setActiveNav(item)}>{item}</button>)}</nav><button className="admin-user" onClick={() => { localStorage.removeItem(ADMIN_KEY); setAuthenticated(false); }}>AD <span>Admin User<br /><small>Sign out</small></span></button></aside><main className="admin-main"><header><h1>{heading}</h1><p>{description}</p></header>{error && <p className="admin-error">{error}</p>}{activeNav === "Practice Debug" ? <TeacherPracticeDebugPage records={audioRecords} /> : activeNav === "Benchmark" ? <TeacherBenchmarkPage /> : activeNav === "IRT / Student analytics" ? <AdminIrtStudentPanel students={students} attempts={quizAttempts} /> : <><section className="admin-metrics"><div><span>Teachers</span><strong>{teachers.length}</strong></div><div><span>Students</span><strong>{students.length}</strong></div><div><span>Quiz responses</span><strong>{quizAttempts.reduce((count, attempt) => count + (attempt.questionResults?.length ?? 0), 0)}</strong></div></section><div className="admin-toolbar"><input placeholder="Search by name" value={query} onChange={(event) => setQuery(event.target.value)} /></div>{(activeNav === "Teachers" || activeNav === "Students") && <form className="add-student" onSubmit={addAccount}><input placeholder={`${activeNav === "Teachers" ? "Teacher" : "Student"} name`} value={newName} onChange={(event) => setNewName(event.target.value)} /><input type="password" placeholder="Password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /><button className="primary">Create account</button></form>}<section className="account-table"><div className="table-head"><span>Name</span><span>Role</span><span>Status</span></div>{filtered.map((account) => <div className="account-row" key={account.id}><span><b>{account.name}</b></span><span>{account.role}</span><span>{account.status}</span></div>)}</section></>}</main></div>;
}
