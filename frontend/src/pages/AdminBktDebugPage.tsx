import { useEffect, useMemo, useState } from "react";
import type { Student } from "../services/api/roster-help";
import { listCustomStories, type StoredCustomStory } from "../services/api/stories-submissions";
import { injectBktDebugResponses, type BktDebugResult } from "../services/api/bkt-debug";
import "./AdminBktDebugPage.css";

const PATTERN_RE = /^[01]{1,50}$/;

/** Admin-only tool: pick a student + published word, paste a 0/1 pattern
 * (1 = correct, 0 = incorrect), and see the BKT mastery estimate after each
 * answer - without needing a real student to click through a real quiz for
 * every scenario worth checking. Injected responses are tagged synthetic
 * server-side (see routers/bkt_debug.py) so they never count as real
 * calibration evidence. */
export default function AdminBktDebugPage({ students }: { students: Student[] }) {
  const [stories, setStories] = useState<StoredCustomStory[]>([]);
  const [studentId, setStudentId] = useState("");
  const [storyId, setStoryId] = useState("");
  const [wordId, setWordId] = useState("");
  const [pattern, setPattern] = useState("1011010");
  const [result, setResult] = useState<BktDebugResult | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void listCustomStories().then((rows) => {
      setStories(rows.filter((story) => story.published && (story.vocabAssessment?.length ?? 0) > 0));
    });
  }, []);

  useEffect(() => {
    if (!studentId && students[0]) setStudentId(students[0].id);
  }, [students, studentId]);

  useEffect(() => {
    if (!storyId && stories[0]) setStoryId(stories[0].id);
  }, [stories, storyId]);

  const selectedStory = stories.find((story) => story.id === storyId);
  const words = useMemo(() => {
    const seen = new Map<string, string>();
    for (const item of selectedStory?.vocabAssessment ?? []) {
      if (item.level === "easy" && !seen.has(item.wordId)) seen.set(item.wordId, item.targetWord);
    }
    return [...seen.entries()];
  }, [selectedStory]);

  useEffect(() => {
    if (words.length > 0 && !words.some(([id]) => id === wordId)) setWordId(words[0][0]);
  }, [words, wordId]);

  const patternValid = PATTERN_RE.test(pattern);

  const submit = async () => {
    if (!studentId || !storyId || !wordId || !patternValid) return;
    setSubmitting(true);
    setError("");
    try {
      setResult(await injectBktDebugResponses(studentId, storyId, wordId, pattern));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not inject the debug responses.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="admin-bkt-debug" aria-label="BKT debug">
      <p className="admin-bkt-debug-note">
        Injects fake responses straight into the real ledger (tagged <code>evidence_origin = synthetic</code>,
        never counted as real calibration evidence) and replays BKT mastery after each one. For debugging the
        pipeline, not for grading anyone.
      </p>
      <div className="admin-bkt-debug-form">
        <label>
          Student
          <select value={studentId} onChange={(event) => setStudentId(event.target.value)}>
            {students.map((student) => (
              <option key={student.id} value={student.id}>{student.name}</option>
            ))}
          </select>
        </label>
        <label>
          Published story
          <select value={storyId} onChange={(event) => { setStoryId(event.target.value); setWordId(""); }}>
            {stories.length === 0 && <option value="">No published story with quiz material</option>}
            {stories.map((story) => (
              <option key={story.id} value={story.id}>{story.title}</option>
            ))}
          </select>
        </label>
        <label>
          Word
          <select value={wordId} onChange={(event) => setWordId(event.target.value)} disabled={words.length === 0}>
            {words.length === 0 && <option value="">No tier1 (easy) word in this story</option>}
            {words.map(([id, targetWord]) => (
              <option key={id} value={id}>{targetWord}</option>
            ))}
          </select>
        </label>
        <label>
          Pattern (1 = correct, 0 = incorrect, in order)
          <input
            value={pattern}
            onChange={(event) => setPattern(event.target.value.trim())}
            placeholder="e.g. 1011010"
            aria-invalid={!patternValid}
          />
        </label>
        <button type="button" onClick={() => void submit()} disabled={submitting || !studentId || !storyId || !wordId || !patternValid}>
          {submitting ? "Injecting…" : "Inject and replay"}
        </button>
        {!patternValid && pattern.length > 0 && <small className="admin-bkt-debug-error">Only 0 and 1, 1-50 characters.</small>}
        {error && <small className="admin-bkt-debug-error">{error}</small>}
      </div>

      {result && (
        <div className="admin-bkt-debug-result">
          <h3>{result.targetWord}</h3>
          <p>
            {result.correctCount} / {result.totalCount} correct across this word's whole history
            (just injected {result.injectedCount}) — final mastery <strong>{Math.round(result.finalMastery * 100)}%</strong>
          </p>
          <ol className="admin-bkt-debug-trace">
            {result.steps.map((step) => (
              <li key={step.index} className={step.correct ? "is-correct" : "is-incorrect"}>
                <span className="admin-bkt-debug-trace-mark">{step.correct ? "✓" : "✗"}</span>
                <span className="admin-bkt-debug-trace-bar" style={{ width: `${Math.round(step.pLearned * 100)}%` }} />
                <span className="admin-bkt-debug-trace-pct">{Math.round(step.pLearned * 100)}%</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
