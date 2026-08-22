import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  canUseDatabase,
  createStudent,
  createTeacher,
  deleteStudent,
  deleteTeacher,
  listAudioRecords,
  listStudents,
  listTeachers,
  listVocabQuizAttempts,
  loginAdmin,
  logoutAdmin,
  updateStudent,
  updateTeacher,
  type Student,
  type Teacher,
  type VocabQuizAttempt,
} from "./services/database";
import AdminIrtStudentPanel from "./components/AdminIrtStudentPanel";
import type { AudioRecord } from "./pages/MyStoriesPage";
import TeacherPracticeDebugPage from "./pages/TeacherPracticeDebugPage";
import "./admin.css";

type Role = "Teacher" | "Student";
type AccountStatus = "Active" | "Inactive";
type Account = { id: string; name: string; role: Role; status: AccountStatus; createdAt: string };

const ADMIN_KEY = "adminConsoleSession";
const NAV_ITEMS = ["Admin Home", "Teachers", "Students", "IRT / Student analytics", "Practice Debug"] as const;

function initialPassword() {
  return import.meta.env.DEV ? "123456" : "";
}

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
  const [refreshing, setRefreshing] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [newName, setNewName] = useState("");
  const [newPassword, setNewPassword] = useState(initialPassword);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [editName, setEditName] = useState("");
  const [editStatus, setEditStatus] = useState<AccountStatus>("Active");
  const [editPassword, setEditPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState("");
  const minimumPasswordLength = import.meta.env.DEV ? 6 : 8;

  const refresh = async () => {
    if (!canUseDatabase()) {
      setError("Backend is not configured.");
      return;
    }
    setRefreshing(true);
    try {
      const [studentRows, teacherRows, attempts] = await Promise.all([listStudents(), listTeachers(), listVocabQuizAttempts()]);
      setStudents(studentRows);
      setTeachers(teacherRows);
      setQuizAttempts(attempts);
      setError("");
    } catch {
      setError("Could not load data from the backend. Your admin session may have expired.");
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (authenticated) void refresh();
  }, [authenticated]);

  useEffect(() => {
    if (activeNav !== "Practice Debug" || !canUseDatabase()) return;
    void listAudioRecords({ limit: 1000 }).then(setAudioRecords).catch(() => setError("Could not load audio records from the backend."));
  }, [activeNav]);

  const accounts = useMemo<Account[]>(() => [
    ...teachers.map((teacher) => ({ id: teacher.id, name: teacher.name, role: "Teacher" as const, status: teacher.status === "active" ? "Active" as const : "Inactive" as const, createdAt: teacher.createdAt })),
    ...students.map((student) => ({ id: student.id, name: student.name, role: "Student" as const, status: student.status === "active" ? "Active" as const : "Inactive" as const, createdAt: student.createdAt })),
  ], [students, teachers]);
  const sectionRole = activeNav === "Teachers" ? "Teacher" : activeNav === "Students" ? "Student" : null;
  const filtered = accounts.filter((account) => account.name.toLowerCase().includes(query.toLowerCase()) && (!sectionRole || account.role === sectionRole));

  const login = async (event: FormEvent) => {
    event.preventDefault();
    setLoginError("");
    try {
      await loginAdmin(password);
      localStorage.setItem(ADMIN_KEY, "true");
      setAuthenticated(true);
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Could not log in.");
    }
  };

  const addAccount = async (event: FormEvent) => {
    event.preventDefault();
    if (!newName.trim()) {
      setError("Provide an account name.");
      return;
    }
    if (newPassword.length < minimumPasswordLength) {
      setError(`Password must be at least ${minimumPasswordLength} characters.`);
      return;
    }
    try {
      if (activeNav === "Teachers") {
        const created = await createTeacher(newName.trim(), newPassword);
        setTeachers((current) => [...current, created]);
      } else {
        const created = await createStudent(newName.trim(), newPassword);
        setStudents((current) => [...current, created]);
      }
      setNewName("");
      setNewPassword(initialPassword());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create account.");
    }
  };

  const beginEdit = (account: Account) => {
    setEditingAccount(account);
    setEditName(account.name);
    setEditStatus(account.status);
    setEditPassword("");
    setError("");
  };

  const cancelEdit = () => {
    setEditingAccount(null);
    setEditPassword("");
  };

  const saveAccount = async (event: FormEvent) => {
    event.preventDefault();
    if (!editingAccount) return;
    const name = editName.trim();
    if (!name) {
      setError("Provide an account name.");
      return;
    }
    if (editPassword && editPassword.length < minimumPasswordLength) {
      setError(`Password must be at least ${minimumPasswordLength} characters.`);
      return;
    }
    setSaving(true);
    try {
      const status = editStatus === "Active" ? "active" : "inactive";
      if (editingAccount.role === "Teacher") {
        const updated = await updateTeacher(editingAccount.id, { name, status, ...(editPassword ? { password: editPassword } : {}) });
        setTeachers((current) => current.map((teacher) => teacher.id === updated.id ? updated : teacher));
      } else {
        const updated = await updateStudent(editingAccount.id, { name, status, ...(editPassword ? { password: editPassword } : {}) });
        setStudents((current) => current.map((student) => student.id === updated.id ? updated : student));
      }
      cancelEdit();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update account.");
    } finally {
      setSaving(false);
    }
  };

  const removeAccount = async (account: Account) => {
    if (!window.confirm(`Delete ${account.role.toLowerCase()} account “${account.name}”? This cannot be undone.`)) return;
    setDeletingId(account.id);
    try {
      if (account.role === "Teacher") {
        await deleteTeacher(account.id);
        setTeachers((current) => current.filter((teacher) => teacher.id !== account.id));
      } else {
        await deleteStudent(account.id);
        setStudents((current) => current.filter((student) => student.id !== account.id));
      }
      if (editingAccount?.id === account.id) cancelEdit();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete account.");
    } finally {
      setDeletingId("");
    }
  };

  if (!authenticated) {
    return <main className="admin-login"><h1>Account Control Center</h1><p>Administrator access.</p><form onSubmit={login}><label>Admin password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" autoFocus /></label><button>Enter admin console</button>{loginError && <small className="admin-error">{loginError}</small>}</form></main>;
  }

  const heading = activeNav === "IRT / Student analytics" ? "IRT / Student analytics" : activeNav === "Practice Debug" ? "Practice Stage Debugger" : "Account Control Center";
  const description = activeNav === "IRT / Student analytics" ? "Track student ability, response quality and calibration readiness." : activeNav === "Practice Debug" ? "Trace student attempts through the scoring pipeline." : "Manage teacher and student accounts.";

  return <div className="admin-shell"><aside className="admin-sidebar"><div className="admin-brand"><span>華</span><strong>中文學習</strong></div><nav>{NAV_ITEMS.map((item) => <button className={activeNav === item ? "active" : ""} key={item} onClick={() => { setActiveNav(item); cancelEdit(); }}>{item}</button>)}</nav><button className="admin-user" onClick={() => { void logoutAdmin(); localStorage.removeItem(ADMIN_KEY); setAuthenticated(false); }}>AD <span>Admin User<br /><small>Sign out</small></span></button></aside><main className="admin-main"><header className="admin-header"><div><h1>{heading}</h1><p>{description}</p></div><button type="button" className="admin-refresh" onClick={() => void refresh()} disabled={refreshing}>{refreshing ? "Refreshing…" : "Refresh data"}</button></header>{error && <p className="admin-error">{error}</p>}{activeNav === "Practice Debug" ? <TeacherPracticeDebugPage records={audioRecords} /> : activeNav === "IRT / Student analytics" ? <AdminIrtStudentPanel students={students} attempts={quizAttempts} /> : <><section className="admin-metrics"><div><span>Teachers</span><strong>{teachers.length}</strong></div><div><span>Students</span><strong>{students.length}</strong></div><div><span>Quiz responses</span><strong>{quizAttempts.reduce((count, attempt) => count + (attempt.questionResults?.length ?? 0), 0)}</strong></div></section><div className="admin-toolbar"><input placeholder="Search by name" value={query} onChange={(event) => setQuery(event.target.value)} /></div>{(activeNav === "Teachers" || activeNav === "Students") && <form className="add-student" onSubmit={addAccount}><input placeholder={`${activeNav === "Teachers" ? "Teacher" : "Student"} name`} value={newName} onChange={(event) => setNewName(event.target.value)} /><input type="password" autoComplete="new-password" placeholder="Password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /><button className="primary">Create account</button></form>}{editingAccount && <form className="account-editor" onSubmit={saveAccount}><div className="account-editor-heading"><div><strong>Edit {editingAccount.role.toLowerCase()} account</strong><small>Password is never shown. Enter a new one only to reset it.</small></div><button type="button" className="close" onClick={cancelEdit} aria-label="Cancel editing">×</button></div><label>Name<input value={editName} onChange={(event) => setEditName(event.target.value)} /></label><label>Status<select value={editStatus} onChange={(event) => setEditStatus(event.target.value as AccountStatus)}><option>Active</option><option>Inactive</option></select></label><label>New password<input type="password" autoComplete="new-password" value={editPassword} onChange={(event) => setEditPassword(event.target.value)} placeholder="Leave blank to keep current password" /></label><div className="account-editor-actions"><button type="button" className="secondary" onClick={cancelEdit}>Cancel</button><button className="primary" disabled={saving}>{saving ? "Saving…" : "Save changes"}</button></div></form>}<section className="account-table"><div className="table-head"><span>Name</span><span>Role</span><span>Status</span><span>Actions</span></div>{filtered.length === 0 ? <div className="empty">No accounts found.</div> : filtered.map((account) => <div className="account-row" key={account.id}><span><b>{account.name}</b><small>{account.createdAt}</small></span><span>{account.role}</span><span className={account.status.toLowerCase()}>{account.status}</span><span className="account-actions"><button type="button" className="account-action" onClick={() => beginEdit(account)}>Edit</button><button type="button" className="account-action danger" disabled={deletingId === account.id} onClick={() => void removeAccount(account)}>{deletingId === account.id ? "Deleting…" : "Delete"}</button></span></div>)}</section></>}</main></div>;
}
