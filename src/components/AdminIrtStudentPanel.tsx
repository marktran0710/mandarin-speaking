import { useMemo, useState } from "react";
import type { Student, VocabQuizAttempt } from "../services/database";

type Props = { students: Student[]; attempts: VocabQuizAttempt[] };
type AbilityMode = "accuracy" | "time" | "joint";

const formatMs = (value: number | null) => value === null ? "--" : `${(value / 1000).toFixed(1)}s`;
const median = (values: number[]) => {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};

export default function AdminIrtStudentPanel({ students, attempts }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<AbilityMode>("joint");
  const rows = students.map((student) => {
    const studentAttempts = attempts.filter((attempt) => attempt.studentId === student.id || (!attempt.studentId && attempt.studentName === student.name));
    const responses = studentAttempts.flatMap((attempt) => attempt.questionResults ?? []);
    const correct = responses.filter((response) => response.correct).length;
    const accuracy = responses.length ? correct / responses.length : null;
    const ability = accuracy === null ? null : Math.max(-4, Math.min(4, Math.log(Math.max(0.01, accuracy) / Math.max(0.01, 1 - accuracy))));
    const items = new Set(responses.map((response) => response.word)).size;
    const times = responses.map((response) => response.timeMs).filter((time): time is number => Number.isFinite(time) && time >= 0);
    const meanLogTime = times.length ? times.reduce((sum, time) => sum + Math.log(Math.max(time, 1)), 0) / times.length : null;
    return { student, responses, correct, accuracy, ability, items, times, meanLogTime, avgTime: times.length ? times.reduce((sum, time) => sum + time, 0) / times.length : null, medianTime: median(times) };
  });
  const totalResponses = rows.reduce((sum, row) => sum + row.responses.length, 0);
  const totalCorrect = rows.reduce((sum, row) => sum + row.correct, 0);
  const overallAccuracy = totalResponses ? totalCorrect / totalResponses : null;
  const allTimes = rows.flatMap((row) => row.times);
  const globalMeanLogTime = allTimes.length ? allTimes.reduce((sum, time) => sum + Math.log(Math.max(time, 1)), 0) / allTimes.length : null;
  const abilityFor = (row: typeof rows[number]) => {
    const accuracyAbility = row.ability;
    const timeAbility = row.meanLogTime === null || globalMeanLogTime === null ? null : globalMeanLogTime - row.meanLogTime;
    if (mode === "accuracy") return accuracyAbility;
    if (mode === "time") return timeAbility;
    if (accuracyAbility === null || timeAbility === null) return null;
    return (accuracyAbility + timeAbility) / 2;
  };
  const modeCopy = { accuracy: { label: "Accuracy ability", formula: "θᵃ = log(p / (1 − p))", detail: "Uses correct/incorrect responses only.", paper: "Rasch / 1PL measurement foundation", paperUrl: "https://www.rasch.org/memo41.htm" }, time: { label: "Response-time ability", formula: "θᵗ = mean(log time) − log(timeᵢ)", detail: "Higher means faster than the sample mean; not more accurate.", paper: "van der Linden (2006), Lognormal Response-Time Model", paperUrl: "https://openurl.ebsco.com/contentitem/gcd%3A21542156?crl=c&id=ebsco%3Agcd%3A21542156&jrnl=10769986&sid=ebsco%3Aplink%3Acrawler-gcd" }, joint: { label: "Joint speed + accuracy", formula: "θʲ = (θᵃ + θᵗ) / 2", detail: "Transparent pilot composite, not a full hierarchical fit.", paper: "van der Linden (2007), A Hierarchical Framework for Modeling Speed and Accuracy", paperUrl: "https://ris.utwente.nl/ws/files/5129699/Linden05hierarchical.pdf" } }[mode];

  const selected = rows.find((row) => row.student.id === selectedId) ?? null;
  const selectedHistory = useMemo(() => selected ? attempts.filter((attempt) => attempt.studentId === selected.student.id || (!attempt.studentId && attempt.studentName === selected.student.name)).sort((a, b) => b.completedAt.localeCompare(a.completedAt)) : [], [attempts, selected]);
  return <section className="admin-irt-panel">
    <div className="admin-metrics">
      <div><span>Students with responses</span><strong>{rows.filter((row) => row.responses.length > 0).length}</strong></div>
      <div><span>Responses</span><strong>{totalResponses}</strong></div>
      <div><span>Overall accuracy</span><strong>{overallAccuracy === null ? "--" : `${Math.round(overallAccuracy * 100)}%`}</strong></div>
      <div><span>Calibration readiness</span><strong>{totalResponses >= 30 ? "Partial" : "Collecting"}</strong></div>
    </div>
    <div className="admin-irt-note"><strong>How to read this</strong><p>θ is a provisional Rasch-style ability estimate from quiz responses. Official IRT calibration requires stable item identity and at least 30 responses per item. Legacy word-only responses remain visible but are not treated as calibrated item evidence.</p></div>
    <div className="admin-irt-speed-summary"><div><span>Median response time</span><strong>{formatMs(median(allTimes))}</strong></div><div><span>Average response time</span><strong>{formatMs(allTimes.length ? allTimes.reduce((sum, time) => sum + time, 0) / allTimes.length : null)}</strong></div><div><span>Measured timings</span><strong>{allTimes.length}</strong></div></div>
    <div className="admin-irt-modebar"><label>Ability view<select value={mode} onChange={(event) => setMode(event.target.value as AbilityMode)}><option value="joint">Joint accuracy + response time</option><option value="accuracy">Accuracy only</option><option value="time">Response time only</option></select></label><div><strong>{modeCopy.label}</strong><code>{modeCopy.formula}</code><span>{modeCopy.detail}</span><small>Paper: <a href={modeCopy.paperUrl} target="_blank" rel="noreferrer">{modeCopy.paper}</a></small></div></div>
    <section className="account-table admin-irt-table">
      <div className="table-head"><span>Student</span><span>Responses</span><span>Accuracy</span><span>Ability θ</span><span>Median time</span><span>Status</span></div>
      {rows.map((row) => <button className={`account-row ${selectedId === row.student.id ? "selected" : ""}`} key={row.student.id} onClick={() => setSelectedId(row.student.id)}><span><b>{row.student.name}</b></span><span>{row.responses.length}</span><span>{row.accuracy === null ? "--" : `${Math.round(row.accuracy * 100)}%`}</span><span>{abilityFor(row) === null ? "--" : abilityFor(row)!.toFixed(2)}</span><span>{formatMs(row.medianTime)}</span><span><em role="button" tabIndex={0} className={row.responses.length >= 30 ? "active" : "inactive"} onClick={(event) => { event.stopPropagation(); setSelectedId(row.student.id); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); setSelectedId(row.student.id); } }}>{row.responses.length >= 30 ? "Ready to review" : "Collecting data"}</em></span></button>)}
      {rows.length === 0 && <p className="empty">No students are available yet.</p>}
    </section>
    {selected && <aside className="admin-irt-detail"><div><h2>{selected.student.name}</h2><button type="button" onClick={() => setSelectedId(null)}>Close</button></div><div className="admin-irt-detail-grid"><div><span>Ability θ</span><strong>{selected.ability === null ? "--" : selected.ability.toFixed(2)}</strong></div><div><span>Accuracy</span><strong>{selected.accuracy === null ? "--" : `${Math.round(selected.accuracy * 100)}%`}</strong></div><div><span>Responses</span><strong>{selected.responses.length}</strong></div><div><span>Items</span><strong>{selected.items}</strong></div></div><p className="admin-irt-detail-note">Student-level ability is provisional. Use it for progress monitoring, not high-stakes decisions, until item identity and sample size are sufficient.</p><h3>Attempt history</h3>{selectedHistory.length === 0 ? <p className="empty">No quiz attempts yet.</p> : <ul className="admin-irt-history">{selectedHistory.map((attempt) => <li key={attempt.id}><span>{new Date(attempt.completedAt).toLocaleString()}</span><strong>{attempt.correctCount}/{attempt.totalQuestions} correct</strong><span>{attempt.mode ?? "quiz"}</span></li>)}</ul>}</aside>}
  </section>;
}
