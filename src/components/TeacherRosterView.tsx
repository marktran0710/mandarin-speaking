import { FormEvent, useEffect, useState } from "react";
import {
  createStudent,
  deleteStudent,
  listStudents,
  type Student,
} from "../services/database";

/** The class roster — a stable id per student instead of the free-typed
 * name every practice record used to carry. Students pick their name from
 * this list at login; a teacher curates it here. This is what per-student
 * analytics (IRT ability, FREX weak-word identification) is keyed on going
 * forward, so it needs to exist before that analysis can be trusted. */
export default function TeacherRosterView() {
  const [students, setStudents] = useState<Student[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const refresh = () => {
    setLoading(true);
    listStudents()
      .then((data) => {
        setStudents(data);
        setLoadError(false);
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const handleAdd = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setSaving(true);
    setFormError(null);
    try {
      await createStudent(trimmed);
      setName("");
      refresh();
    } catch {
      setFormError("Could not add that student. Try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (student: Student) => {
    if (!window.confirm(`Remove ${student.name} from the roster?`)) return;
    setStudents((prev) => prev.filter((s) => s.id !== student.id));
    try {
      await deleteStudent(student.id);
    } catch {
      refresh(); // put it back if the delete didn't actually go through
    }
  };

  return (
    <section className="teacher-panel roster-panel">
      <div className="teacher-panel-header">
        <div>
          <p className="stories-kicker">Class roster</p>
          <h2>Students</h2>
        </div>
        <span className="queue-count">{students.length}</span>
      </div>

      <form className="roster-add-form" onSubmit={handleAdd}>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Student name"
          aria-label="New student name"
        />
        <button type="submit" className="btn btn-small btn-secondary" disabled={saving || !name.trim()}>
          {saving ? "Adding…" : "Add"}
        </button>
      </form>
      {formError && <p className="roster-form-error">{formError}</p>}

      {loading ? (
        <p className="roster-status">Loading roster…</p>
      ) : loadError ? (
        <p className="roster-status">Could not load the roster.</p>
      ) : students.length === 0 ? (
        <div className="teacher-empty-panel">
          <strong>No students yet</strong>
          <p>Add students above — they'll appear in the login picker.</p>
        </div>
      ) : (
        <ul className="roster-list">
          {students.map((student) => (
            <li key={student.id} className="roster-row">
              <span>{student.name}</span>
              <button
                type="button"
                className="btn btn-small btn-danger"
                aria-label={`Remove ${student.name}`}
                onClick={() => handleDelete(student)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
