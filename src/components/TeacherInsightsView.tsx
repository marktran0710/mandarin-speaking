import { useEffect, useState } from "react";
import {
  getVocabQuizFrex,
  getVocabQuizIrt,
  getVocabQuizJointModel,
  type VocabQuizFrexStudent,
  type VocabQuizIrt,
  type VocabQuizJointModel,
  type VocabQuizMode,
} from "../services/database";

const MODES: VocabQuizMode[] = ["speed", "strikes", "free", "review"];
const MODE_LABEL: Record<VocabQuizMode, string> = {
  speed: "Speed",
  strikes: "Strikes",
  free: "Free",
  review: "Review",
};
const REFRESH_INTERVAL_MS = 20_000;

/** Model-based reading of the vocab quiz — item response theory (ability
 * accounting for *which* words a student got, not just how many), a joint
 * speed/accuracy model per quiz mode (time pressure differs too much
 * between modes to pool), and FREX-ranked personal weak spots. Polls on an
 * interval rather than a real push, which is real-time-enough for a
 * classroom-glance dashboard without the complexity of a websocket. */
export default function TeacherInsightsView() {
  const [irt, setIrt] = useState<VocabQuizIrt | null>(null);
  const [joint, setJoint] = useState<VocabQuizJointModel | null>(null);
  const [frex, setFrex] = useState<VocabQuizFrexStudent[]>([]);
  const [mode, setMode] = useState<VocabQuizMode>("speed");
  const [expandedStudent, setExpandedStudent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = async (nextMode: VocabQuizMode) => {
    setLoading(true);
    try {
      const [irtResult, jointResult, frexResult] = await Promise.all([
        getVocabQuizIrt(),
        getVocabQuizJointModel(nextMode),
        getVocabQuizFrex(),
      ]);
      setIrt(irtResult);
      setJoint(jointResult);
      setFrex(frexResult);
      setError(null);
      setLastUpdated(new Date());
    } catch {
      setError("Could not load quiz insights.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh(mode);
    const timer = setInterval(() => refresh(mode), REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  if (error) {
    return (
      <div className="insights-view">
        <section className="teacher-panel">
          <div className="teacher-panel-header">
            <div>
              <p className="stories-kicker">Vocab quiz insights</p>
              <h2>Insights</h2>
            </div>
          </div>
          <p className="teacher-form-error">{error}</p>
        </section>
      </div>
    );
  }

  if (!loading && irt && irt.nResponses === 0) {
    return (
      <div className="insights-view">
        <section className="teacher-panel">
          <div className="teacher-panel-header">
            <div>
              <p className="stories-kicker">Vocab quiz insights</p>
              <h2>Insights</h2>
            </div>
          </div>
          <div className="teacher-empty-panel">
            <strong>No roster-linked quiz attempts yet</strong>
            <p>
              Ability estimates, item difficulty, and weak-spot detection need
              students signed in via the roster (see the Roster tab) — quiz
              attempts saved before that won't appear here.
            </p>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="insights-view">
      <section className="teacher-panel insights-header-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Vocab quiz insights</p>
            <h2>Ability, Difficulty &amp; Weak Spots</h2>
          </div>
          <div className="insights-refresh">
            <span className="insights-updated">
              {lastUpdated
                ? `Updated ${lastUpdated.toLocaleTimeString()}`
                : "Loading…"}
            </span>
            <button
              type="button"
              className="teacher-refresh-btn"
              disabled={loading}
              onClick={() => refresh(mode)}
            >
              {loading ? "Refreshing…" : "↺ Refresh"}
            </button>
          </div>
        </div>
        <p className="insights-note">
          Refreshes automatically every {REFRESH_INTERVAL_MS / 1000}s.
        </p>
      </section>

      <section className="teacher-dashboard-grid">
        <div className="teacher-panel">
          <div className="teacher-panel-header">
            <div>
              <p className="stories-kicker">Item response theory</p>
              <h2>Student Ability</h2>
            </div>
            <span className="queue-count">{irt?.students.length ?? 0}</span>
          </div>
          {!irt || irt.students.length === 0 ? (
            <p className="roster-status">No data yet.</p>
          ) : (
            <div className="insights-list">
              <div className="insights-row insights-row-head">
                <span>Student</span>
                <span>Ability</span>
                <span>Responses</span>
              </div>
              {irt.students.map((s) => (
                <div className="insights-row" key={s.studentId}>
                  <span>{s.name}</span>
                  <span>{s.ability.toFixed(2)}</span>
                  <span>{s.nResponses}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="teacher-panel">
          <div className="teacher-panel-header">
            <div>
              <p className="stories-kicker">Item response theory</p>
              <h2>Hardest Words</h2>
            </div>
            <span className="queue-count">{irt?.items.length ?? 0}</span>
          </div>
          {!irt || irt.items.length === 0 ? (
            <p className="roster-status">No data yet.</p>
          ) : (
            <div className="insights-list">
              <div className="insights-row insights-row-head">
                <span>Word</span>
                <span>Difficulty</span>
                <span>Responses</span>
              </div>
              {irt.items.map((item) => (
                <div className="insights-row" key={item.word}>
                  <span lang="zh-Hant">{item.word}</span>
                  <span>{item.difficulty.toFixed(2)}</span>
                  <span>{item.nResponses}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="teacher-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">Joint speed/accuracy model</p>
            <h2>Pace vs. Accuracy by Quiz Mode</h2>
          </div>
          <div className="insights-mode-picker">
            {MODES.map((m) => (
              <button
                key={m}
                type="button"
                className={`insights-mode-btn${m === mode ? " active" : ""}`}
                onClick={() => setMode(m)}
              >
                {MODE_LABEL[m]}
              </button>
            ))}
          </div>
        </div>

        {!joint || joint.nResponses === 0 ? (
          <div className="teacher-empty-panel">
            <strong>No {MODE_LABEL[mode].toLowerCase()}-mode attempts yet</strong>
            <p>This model is fit separately per mode since time pressure differs too much between them to pool.</p>
          </div>
        ) : (
          <>
            <p className="insights-correlation-note">
              {joint.abilitySpeedCorrelation === null ? (
                "Not enough students with both a speed and an ability estimate yet to say whether pace and accuracy move together in this mode."
              ) : joint.abilitySpeedCorrelation > 0.2 ? (
                `In ${MODE_LABEL[mode]} mode, faster students also tend to be more accurate (r = ${joint.abilitySpeedCorrelation.toFixed(2)}) — likely mastery, not guessing.`
              ) : joint.abilitySpeedCorrelation < -0.2 ? (
                `In ${MODE_LABEL[mode]} mode, faster students tend to be less accurate (r = ${joint.abilitySpeedCorrelation.toFixed(2)}) — watch for rushing under time pressure.`
              ) : (
                `In ${MODE_LABEL[mode]} mode, pace and accuracy aren't clearly linked (r = ${joint.abilitySpeedCorrelation.toFixed(2)}).`
              )}
            </p>
            <div className="insights-list">
              <div className="insights-row insights-row-head">
                <span>Student</span>
                <span>Ability</span>
                <span>Speed</span>
              </div>
              {joint.students.map((s) => (
                <div className="insights-row" key={s.studentId}>
                  <span>{s.name}</span>
                  <span>{s.ability === null ? "—" : s.ability.toFixed(2)}</span>
                  <span>{s.speed.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="teacher-panel">
        <div className="teacher-panel-header">
          <div>
            <p className="stories-kicker">FREX-ranked</p>
            <h2>Personal Weak Spots</h2>
          </div>
          <span className="queue-count">{frex.length}</span>
        </div>

        {frex.length === 0 ? (
          <div className="teacher-empty-panel">
            <strong>No characteristic weak words yet</strong>
            <p>Shows up once a student has missed at least one word.</p>
          </div>
        ) : (
          <div className="insights-frex-list">
            {frex.map((student) => (
              <div className="insights-frex-student" key={student.studentId}>
                <button
                  type="button"
                  className="insights-frex-toggle"
                  aria-expanded={expandedStudent === student.studentId}
                  aria-controls={`insights-frex-words-${student.studentId}`}
                  onClick={() =>
                    setExpandedStudent((current) =>
                      current === student.studentId ? null : student.studentId,
                    )
                  }
                >
                  <span>{student.name}</span>
                  <span className="insights-frex-count">{student.words.length} word{student.words.length === 1 ? "" : "s"}</span>
                </button>
                {expandedStudent === student.studentId && (
                  <div className="insights-frex-words" id={`insights-frex-words-${student.studentId}`}>
                    {student.words.map((w) => (
                      <div className="insights-frex-word" key={w.word}>
                        <strong lang="zh-Hant">{w.word}</strong>
                        <span>
                          missed {w.missCount}× · {Math.round(w.exclusivity * 100)}% of the class's misses on this word are theirs
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
