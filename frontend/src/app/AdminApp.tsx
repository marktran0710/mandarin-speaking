import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  canUseDatabase,
  createStudent,
  createTeacher,
  deleteStudent,
  deleteTeacher,
  getAdminRosterOverview,
  getAudioRecordCount,
  listAudioRecords,
  listMeasurementEvents,
  loginAdmin,
  logoutAdmin,
  updateStudent,
  updateTeacher,
  deleteAudioRecordFromDatabase,
  SESSION_EXPIRED_EVENT,
  type SessionExpiredEventDetail,
  type Student,
  type Teacher,
  type VocabQuizAttempt,
} from "../services/database";
import AdminIrtStudentPanel from "../components/analytics/AdminIrtStudentPanel";
import MeasurementAnalyticsPanel from "../components/analytics/MeasurementAnalyticsPanel";
import type { MeasurementEvent } from "../utils/measurement";
import KnowledgeModelPilotPanel from "../components/analytics/KnowledgeModelPilotPanel";
import type { AudioRecord } from "../types/audioRecord";
import TeacherPracticeDebugPage from "../pages/TeacherPracticeDebugPage";
import AdminAsrComparePage from "../pages/AdminAsrComparePage";
import AdminBktDebugPage from "../pages/AdminBktDebugPage";
import AdminResearchPage from "../pages/AdminResearchPage";
import AdminMaterialsPage from "../pages/AdminMaterialsPage";
import AdminVocabularyPage from "../pages/AdminVocabularyPage";
import AdminAudioLibraryPage from "../pages/AdminAudioLibraryPage";
import ManagementShell from "../components/management/ManagementShell";
import Icon from "../shared/ui/Icon";
import { isDevelopmentRuntime, isTestRuntime } from "../config/runtimeEnv";
import "../styles/apps/admin.css";

type Role = "Teacher" | "Student";
type AccountStatus = "Active" | "Inactive";
type Account = { id: string; name: string; role: Role; status: AccountStatus; createdAt: string };

const ADMIN_KEY = "adminConsoleSession";
// "Measurement" moved here from the teacher sidebar: it is research tooling
// about instrument health, not part of a teacher's daily loop.
const NAV_ITEMS = ["Admin Home", "Materials", "Audio Library", "Vocabulary", "Teachers", "Students", "IRT / Student analytics", "Measurement", "Practice Debug", "ASR Compare", "BKT Debug", "Research"] as const;
export type AdminNav = typeof NAV_ITEMS[number];

function initialPassword() {
  return isTestRuntime() || isDevelopmentRuntime() ? "123456" : "";
}

export default function AdminApp({ embedded = false, onExit, initialNav = "Admin Home" }: { embedded?: boolean; onExit?: () => void; initialNav?: AdminNav } = {}) {
  const [authenticated, setAuthenticated] = useState(() => localStorage.getItem(ADMIN_KEY) === "true");
  const [password, setPassword] = useState("");
  const [activeNav, setActiveNav] = useState<AdminNav>(initialNav);
  const [students, setStudents] = useState<Student[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [quizAttempts, setQuizAttempts] = useState<VocabQuizAttempt[]>([]);
  const [audioRecords, setAudioRecords] = useState<AudioRecord[]>([]);
  const [audioRecordCount, setAudioRecordCount] = useState(0);
  const [measurementEvents, setMeasurementEvents] = useState<MeasurementEvent[]>([]);
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
  const [vocabularyRefresh, setVocabularyRefresh] = useState(0);
  const [deletingId, setDeletingId] = useState("");
  const minimumPasswordLength = isDevelopmentRuntime() ? 6 : 8;

  const refresh = async () => {
    if (!canUseDatabase()) {
      setError("Backend is not configured.");
      return;
    }
    setRefreshing(true);
    try {
      const { students: studentRows, teachers: teacherRows, quizAttempts: attempts } = await getAdminRosterOverview();
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

  // The "am I logged in" flag above is a plain localStorage read, checked
  // once at mount - it has no way to notice the actual session cookie
  // expiring or getting cleared later. Without this, that leaves the app
  // stuck showing the authenticated shell with every request failing the
  // same generic way until the user thinks to log out and back in by hand.
  useEffect(() => {
    const handleSessionExpired = (event: Event) => {
      const detail = (event as CustomEvent<SessionExpiredEventDetail>).detail;
      if (detail?.role !== "admin") return;
      localStorage.removeItem(ADMIN_KEY);
      setAuthenticated(false);
      setLoginError("Your session expired. Please log in again.");
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, []);

  useEffect(() => {
    if (!["Audio Library", "Practice Debug", "Measurement"].includes(activeNav) || !canUseDatabase()) return;
    const limit = activeNav === "Audio Library" ? 100 : 1000;
    void listAudioRecords({ limit }).then(setAudioRecords).catch(() => setError("Could not load audio records from the backend."));
    if (activeNav === "Audio Library") {
      void getAudioRecordCount().then(setAudioRecordCount).catch(() => setError("Could not load the audio record count."));
    }
    if (activeNav === "Measurement") void listMeasurementEvents().then(setMeasurementEvents).catch(() => {});
  }, [activeNav]);

  const refreshAudioRecords = async () => {
    if (!canUseDatabase()) {
      setError("Backend is not configured.");
      return;
    }
    try {
      const [records, total] = await Promise.all([
        listAudioRecords({ limit: 100 }),
        getAudioRecordCount(),
      ]);
      setAudioRecords(records);
      setAudioRecordCount(total);
      setError("");
    } catch {
      setError("Could not load audio records from the backend.");
    }
  };

  const loadMoreAudioRecords = async () => {
    if (!canUseDatabase() || audioRecords.length >= audioRecordCount) return;
    try {
      const records = await listAudioRecords({ limit: 100, skip: audioRecords.length });
      setAudioRecords((current) => [...current, ...records]);
    } catch {
      setError("Could not load more audio records from the backend.");
    }
  };

  const deleteAudioRecord = async (id: string) => {
    try {
      await deleteAudioRecordFromDatabase(id);
      setAudioRecords((current) => current.filter((record) => record.id !== id));
      setAudioRecordCount((current) => Math.max(0, current - 1));
      setError("");
    } catch {
      setError("Could not delete this audio record.");
    }
  };

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

  if (embedded && !authenticated) return null;

  if (!authenticated) {
    return <main className="admin-login"><h1>Account Control Center</h1><p>Administrator access.</p><form onSubmit={login}><label>Admin password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" autoFocus /></label><button>Enter admin console</button>{loginError && <small className="admin-error">{loginError}</small>}</form></main>;
  }

  const isAccountWorkspace = activeNav === "Admin Home" || activeNav === "Teachers" || activeNav === "Students";
  const heading = activeNav === "Admin Home" ? "Admin overview" : activeNav === "Teachers" ? "Teachers" : activeNav === "Students" ? "Students" : activeNav === "Vocabulary" ? "Content Bank" : activeNav === "Materials" ? "Materials" : activeNav === "Audio Library" ? "Audio Library" : activeNav === "IRT / Student analytics" ? "IRT / Student analytics" : activeNav === "Measurement" ? "Measurement health" : activeNav === "Practice Debug" ? "Practice Stage Debugger" : activeNav === "ASR Compare" ? "ASR Compare" : activeNav === "BKT Debug" ? "BKT Debug" : activeNav === "Research" ? "Research study" : "Admin workspace";
  const description = activeNav === "Admin Home" ? "A calm starting point for people, curriculum, and research operations." : activeNav === "Teachers" ? "Create, review, and maintain teacher access." : activeNav === "Students" ? "Create, review, and maintain student access." : activeNav === "Vocabulary" ? "Manage vocabulary and questions together from one canonical import format." : activeNav === "Materials" ? "Create and review the story content available to students." : activeNav === "Audio Library" ? "Review and remove student recording evidence and uploaded media." : activeNav === "IRT / Student analytics" ? "Track student ability, response quality and calibration readiness." : activeNav === "Measurement" ? "Check how much of the scoring pipeline produced usable evidence." : activeNav === "Practice Debug" ? "Trace student attempts through the scoring pipeline." : activeNav === "ASR Compare" ? "Compare ASR models on the same recording through the real scoring pipeline." : activeNav === "BKT Debug" ? "Inject fake answers and watch BKT mastery replay, step by step." : activeNav === "Research" ? "Study status, assignment balance, and protocol fidelity - never shown on the Teacher Dashboard." : "Manage the Mandarin learning workspace.";
  const accountScope = activeNav === "Teachers" ? "teachers" : activeNav === "Students" ? "students" : "people";

  return <ManagementShell
    role="admin"
    activeView={activeNav}
    onSelectView={(view) => { setActiveNav(view as (typeof NAV_ITEMS)[number]); cancelEdit(); }}
    refreshing={refreshing}
    onRefresh={() => activeNav === "Vocabulary" ? setVocabularyRefresh(value => value + 1) : activeNav === "Audio Library" ? void refreshAudioRecords() : void refresh()}
    onLogout={() => { void logoutAdmin(); localStorage.removeItem(ADMIN_KEY); setAuthenticated(false); onExit?.(); }}
  ><div className={`admin-main${activeNav === "Vocabulary" ? " admin-vocabulary-main" : ""}`}>
    <header className="admin-header">
      <div>
        <span className="admin-eyebrow">{activeNav === "Admin Home" ? "Workspace" : isAccountWorkspace ? "Accounts" : "Operations"}</span>
        <h1>{heading}</h1>
        {activeNav !== "Vocabulary" && <p>{description}</p>}
      </div>
    </header>
    {error && activeNav !== "Vocabulary" && <p className="admin-error" role="alert">{error}</p>}
    {activeNav === "Vocabulary" ? <AdminVocabularyPage refreshKey={vocabularyRefresh} onOpenMaterials={() => setActiveNav("Materials")} /> : activeNav === "Materials" ? <AdminMaterialsPage /> : activeNav === "Audio Library" ? <AdminAudioLibraryPage records={audioRecords} hasMoreRecords={audioRecords.length < audioRecordCount} onDeleteRecord={(id) => void deleteAudioRecord(id)} onLoadMoreRecords={loadMoreAudioRecords} /> : activeNav === "Practice Debug" ? <TeacherPracticeDebugPage records={audioRecords} /> : activeNav === "ASR Compare" ? <AdminAsrComparePage /> : activeNav === "BKT Debug" ? <AdminBktDebugPage students={students} /> : activeNav === "Research" ? <AdminResearchPage /> : activeNav === "Measurement" ? <MeasurementAnalyticsPanel records={audioRecords} events={measurementEvents} /> : activeNav === "IRT / Student analytics" ? <><AdminIrtStudentPanel students={students} attempts={quizAttempts} /><KnowledgeModelPilotPanel /></> : <>
      <section className="admin-metrics" aria-label="Account totals">
        <div><span>Teachers</span><strong>{teachers.length}</strong><small>active directory</small></div>
        <div><span>Students</span><strong>{students.length}</strong><small>active directory</small></div>
        <div><span>Quiz responses</span><strong>{quizAttempts.reduce((count, attempt) => count + (attempt.questionResults?.length ?? 0), 0)}</strong><small>recorded attempts</small></div>
      </section>
      {activeNav === "Admin Home" && <section className="admin-quick-actions" aria-labelledby="admin-quick-actions-title">
        <div className="admin-quick-actions-copy"><span className="admin-eyebrow">Next steps</span><h2 id="admin-quick-actions-title">Keep the learning workspace moving</h2><p>Open the area you need without losing the current admin context.</p></div>
        <div className="admin-quick-actions-links">
          <button type="button" className="admin-action-card" onClick={() => setActiveNav("Materials")}><Icon name="library" size={20} /><span><strong>Materials</strong><small>Stories and lesson content</small></span><Icon name="arrow-right" size={18} /></button>
          <button type="button" className="admin-action-card" onClick={() => setActiveNav("Vocabulary")}><Icon name="book" size={20} /><span><strong>Content Bank</strong><small>Vocabulary and questions</small></span><Icon name="arrow-right" size={18} /></button>
        </div>
      </section>}
      <div className="admin-toolbar">
        <label className="admin-search"><span>Search {accountScope}</span><input aria-label={`Search ${accountScope}`} placeholder={`Search ${accountScope} by name`} value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <span className="admin-result-count">{filtered.length} shown</span>
      </div>
      {(activeNav === "Teachers" || activeNav === "Students") && <form className="add-student" onSubmit={addAccount}><label><span>Name</span><input aria-label={`${activeNav === "Teachers" ? "Teacher" : "Student"} name`} placeholder={`${activeNav === "Teachers" ? "Teacher" : "Student"} name`} value={newName} onChange={(event) => setNewName(event.target.value)} /></label><label><span>Password</span><input aria-label="Password" type="password" autoComplete="new-password" placeholder="Password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></label><button className="primary">Create account</button></form>}
      {editingAccount && <form className="account-editor" onSubmit={saveAccount}><div className="account-editor-heading"><div><strong>Edit {editingAccount.role.toLowerCase()} account</strong><small>Password is never shown. Enter a new one only to reset it.</small></div><button type="button" className="close" onClick={cancelEdit} aria-label="Cancel editing">×</button></div><label>Name<input value={editName} onChange={(event) => setEditName(event.target.value)} /></label><label>Status<select value={editStatus} onChange={(event) => setEditStatus(event.target.value as AccountStatus)}><option>Active</option><option>Inactive</option></select></label><label>New password<input type="password" autoComplete="new-password" value={editPassword} onChange={(event) => setEditPassword(event.target.value)} placeholder="Leave blank to keep current password" /></label><div className="account-editor-actions"><button type="button" className="secondary" onClick={cancelEdit}>Cancel</button><button className="primary" disabled={saving}>{saving ? "Saving…" : "Save changes"}</button></div></form>}
      <section className="account-table" aria-labelledby="admin-account-list-title"><div className="admin-table-heading"><div><span className="admin-eyebrow">Directory</span><h2 id="admin-account-list-title">{activeNav === "Admin Home" ? "All accounts" : `${activeNav} accounts`}</h2></div><span>{filtered.length} {filtered.length === 1 ? "account" : "accounts"}</span></div><div className="table-head"><span>Name</span><span>Role</span><span>Status</span><span>Actions</span></div>{filtered.length === 0 ? <div className="empty"><Icon name="users" size={24} /><strong>No {accountScope} found</strong><span>{query ? "Try a different search." : "Accounts will appear here once the backend is connected."}</span></div> : filtered.map((account) => <div className="account-row" key={account.id}><span><b>{account.name}</b><small>{account.createdAt}</small></span><span>{account.role}</span><span className={account.status.toLowerCase()}>{account.status}</span><span className="account-actions"><button type="button" className="account-action" onClick={() => beginEdit(account)}>Edit</button><button type="button" className="account-action danger" disabled={deletingId === account.id} onClick={() => void removeAccount(account)}>{deletingId === account.id ? "Deleting…" : "Delete"}</button></span></div>)}</section>
    </>}</div></ManagementShell>;
}
