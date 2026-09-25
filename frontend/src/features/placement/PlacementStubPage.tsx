import { useEffect, useMemo, useState } from "react";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill, { type StudentStatusTone } from "@shared/ui/student/StudentStatusPill";
import "@shared/ui/student/layout.css";
import {
  unavailablePlacementSession,
  usePlacementSession,
  type PlacementSessionAdapter,
  type PlacementSessionStatus,
} from "./placementSession";
import "./PlacementStubPage.css";
import {
  completePlacementAttempt,
  getPlacementBlueprint,
  startPlacementAttempt,
  type PlacementAnswer,
  type PlacementBlueprint,
  type PlacementQuestion,
  type PlacementResult,
} from "@shared/api/placement-test";

export interface PlacementStubPageProps {
  adapter?: PlacementSessionAdapter;
}

interface PlacementStatusPresentation {
  label: string;
  tone: StudentStatusTone;
  heading: string;
  body: string;
}

const STATUS_PRESENTATION: Record<PlacementSessionStatus, PlacementStatusPresentation> = {
  unavailable: {
    label: "Not available",
    tone: "neutral",
    heading: "Placement test not available",
    body: "The placement assessment is not available in this learning workspace yet.",
  },
  loading: {
    label: "Loading",
    tone: "info",
    heading: "Placement test is loading",
    body: "The placement assessment is being prepared. No assessment data is shown until the session is ready.",
  },
  ready: {
    label: "Ready",
    tone: "info",
    heading: "Placement test is ready",
    body: "The placement assessment can be connected here when its learner-facing session contract is available.",
  },
  complete: {
    label: "Complete",
    tone: "success",
    heading: "Placement test complete",
    body: "Placement results will appear here when the assessment result contract is available.",
  },
  error: {
    label: "Unavailable",
    tone: "danger",
    heading: "Placement test unavailable",
    body: "The placement assessment could not be loaded. No assessment data is shown.",
  },
};

function UnavailablePlacementPage({ adapter = unavailablePlacementSession }: PlacementStubPageProps) {
  const session = usePlacementSession(adapter);
  const presentation = STATUS_PRESENTATION[session.status];

  return (
    <div className="sa-page-container sa-placement">
      <StudentPageHeader
        eyebrowEn="Placement"
        eyebrowZh="入門測驗"
        titleZh="入門測驗"
        titleEn="Placement Test"
        aside={<StudentStatusPill tone={presentation.tone}>{presentation.label}</StudentStatusPill>}
      />

      <StudentSection
        variant="panel"
        className="sa-placement__card"
        aria-labelledby="placement-test-heading"
      >
        <div className="sa-placement__accent" aria-hidden="true" />
        <div className="sa-placement__body">
          <div className="sa-placement__intro">
            <div className="sa-placement__icon" aria-hidden="true">
              <StudentIcon name="flag" size={20} role="decorative" />
            </div>
            <div className="sa-placement__intro-copy">
              <p className="sa-placement__kicker">Assessment availability</p>
              <h2 id="placement-test-heading">{presentation.heading}</h2>
              <p className="sa-placement__description">{presentation.body}</p>
            </div>
          </div>

          <div className="sa-placement__notice" role="status" aria-live="polite">
            <StudentIcon name="info" size={18} role="decorative" />
            <p>
              <span lang="zh-Hant">入門測驗目前未開放。</span>
              <span>Placement testing will appear here when it is enabled for learners.</span>
            </p>
          </div>
        </div>
      </StudentSection>
    </div>
  );
}

function labelFor(question: PlacementQuestion): string {
  if (question.questionType === "basic_meaning_mcq") return "Meaning check";
  if (question.questionType === "character_to_pinyin_typing") return "Reading recall";
  return "Context clue";
}

function shuffleQuestions(questions: PlacementQuestion[]): PlacementQuestion[] {
  return [...questions].sort((left, right) => {
    const leftKey = `${left.questionId}:placement`;
    const rightKey = `${right.questionId}:placement`;
    return leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0;
  });
}

function PlacementAssessmentPage() {
  const [blueprint, setBlueprint] = useState<PlacementBlueprint | null>(null);
  const [attemptId, setAttemptId] = useState("");
  const [questions, setQuestions] = useState<PlacementQuestion[]>([]);
  const [randomize, setRandomize] = useState(false);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [times, setTimes] = useState<Record<string, number>>({});
  const [questionStartedAt, setQuestionStartedAt] = useState(() => Date.now());
  const [result, setResult] = useState<PlacementResult | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "starting" | "answering" | "submitting" | "result" | "error">("loading");
  const [error, setError] = useState("");
  const [pinyinDraft, setPinyinDraft] = useState("");
  const question = questions[index];
  const displayedQuestions = useMemo(() => randomize ? shuffleQuestions(questions) : questions, [questions, randomize]);

  useEffect(() => {
    let active = true;
    void getPlacementBlueprint().then((data) => {
      if (!active) return;
      setBlueprint(data);
      setQuestions(data.questions);
      setStatus("ready");
    }).catch((reason) => {
      if (!active) return;
      setError(reason instanceof Error ? reason.message : "Could not load the placement test.");
      setStatus("error");
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (status !== "answering" || !question) return;
    setQuestionStartedAt(Date.now());
    setPinyinDraft(answers[question.questionId] ?? "");
  }, [index, status]);

  const start = async () => {
    setStatus("starting");
    setError("");
    try {
      const attempt = await startPlacementAttempt();
      setAttemptId(attempt.attemptId);
      setQuestions(attempt.questions);
      setAnswers({});
      setTimes({});
      setIndex(0);
      setResult(null);
      setStatus("answering");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start the placement test.");
      setStatus("error");
    }
  };

  const saveCurrentAnswer = (value: string) => {
    if (!question) return;
    setAnswers((current) => ({ ...current, [question.questionId]: value }));
    setTimes((current) => ({ ...current, [question.questionId]: Math.max(current[question.questionId] ?? 0, Date.now() - questionStartedAt) }));
  };

  const next = () => {
    if (!question || !(answers[question.questionId] ?? pinyinDraft).trim()) return;
    saveCurrentAnswer(question.questionType === "character_to_pinyin_typing" ? pinyinDraft.trim() : answers[question.questionId]);
    if (index + 1 < displayedQuestions.length) {
      const nextQuestion = displayedQuestions[index + 1];
      setAnswers((current) => ({ ...current, [question.questionId]: question.questionType === "character_to_pinyin_typing" ? pinyinDraft.trim() : current[question.questionId] }));
      setIndex(index + 1);
      setQuestionStartedAt(Date.now());
      setPinyinDraft(answers[nextQuestion.questionId] ?? "");
    }
  };

  const finish = async () => {
    if (!question || !attemptId) return;
    const finalAnswer = question.questionType === "character_to_pinyin_typing" ? pinyinDraft.trim() : answers[question.questionId];
    if (!finalAnswer?.trim()) return;
    saveCurrentAnswer(finalAnswer.trim());
    const now = Date.now();
    const responseAnswers: PlacementAnswer[] = displayedQuestions.map((item) => ({
      questionId: item.questionId,
      selectedAnswer: item.questionId === question.questionId ? finalAnswer.trim() : answers[item.questionId],
      timeMs: (times[item.questionId] ?? 0) + (item.questionId === question.questionId ? Math.max(0, now - questionStartedAt) : 0),
      answeredAt: new Date().toISOString(),
    }));
    setStatus("submitting");
    setError("");
    try {
      const completed = await completePlacementAttempt(attemptId, responseAnswers);
      setResult(completed);
      setStatus("result");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not submit the placement test.");
      setStatus("answering");
    }
  };

  if (status === "loading") return <PlacementLiveShell status="Loading" heading="Placement test is loading" body="Preparing your placement assessment." />;
  if (status === "error") return <PlacementLiveShell status="Unavailable" heading="Placement test unavailable" body={error} />;
  if (!blueprint?.configured || blueprint.questionCount === 0) return <PlacementLiveShell status="Not available" heading="Placement test not available" body="Your teacher has not configured a placement assessment yet." />;
  if (status === "result" && result) {
    const congratulations = result.messageKey === "CONGRATULATIONS";
    return <div className="sa-page-container sa-placement"><StudentPageHeader eyebrowEn="Placement" eyebrowZh="Placement" titleZh="入門測驗" titleEn="Placement Test" aside={<StudentStatusPill tone="success">Complete</StudentStatusPill>} /><StudentSection variant="panel" className="sa-placement__result"><StudentIcon name={congratulations ? "celebration" : "self_improvement"} size={34} role="decorative" /><p className="sa-placement__result-kicker">Placement complete</p><h2>你答對 {result.correctCount} / {result.totalQuestions} 題。</h2><p className="sa-placement__result-score">{result.percentage}%</p><p>{congratulations ? "Great work — you are ready to keep learning." : "Keep practising — every question helps build your learning path."}</p></StudentSection></div>;
  }

  const activeQuestion = displayedQuestions[index];
  const selected = activeQuestion?.questionType === "character_to_pinyin_typing" ? pinyinDraft : answers[activeQuestion?.questionId ?? ""] ?? "";
  const progress = displayedQuestions.length ? ((index + 1) / displayedQuestions.length) * 100 : 0;
  return <div className="sa-page-container sa-placement">
    <StudentPageHeader eyebrowEn="Placement" eyebrowZh="Placement" titleZh="入門測驗" titleEn="Placement Test" aside={<StudentStatusPill tone="info">Question {index + 1} / {displayedQuestions.length}</StudentStatusPill>} />
    {status === "ready" && <StudentSection variant="panel" className="sa-placement__start"><div><p className="sa-placement__kicker">A short diagnostic</p><h2>Show what you already know.</h2><p>This placement test uses {blueprint.questionCount} vocabulary questions from your published course material. It updates your learning record after you submit.</p></div><label className="sa-placement__randomize"><input type="checkbox" checked={randomize} onChange={(event) => setRandomize(event.target.checked)} /> Randomize display order</label><StudentButton variant="primary" iconTrailing="arrow_forward" onClick={() => void start()}>Start placement test</StudentButton></StudentSection>}
    {(status === "starting" || status === "submitting") && <StudentSection variant="panel" className="sa-placement__start"><p role="status">{status === "starting" ? "Starting your assessment…" : "Saving your answers…"}</p></StudentSection>}
    {status === "answering" && activeQuestion && <>
      <div className="sa-placement__progress" role="progressbar" aria-label="Placement progress" aria-valuemin={0} aria-valuemax={displayedQuestions.length} aria-valuenow={index + 1}><span style={{ width: `${progress}%` }} /></div>
      <StudentSection variant="panel" className="sa-placement__question"><div className="sa-placement__question-meta"><span>{labelFor(activeQuestion)}</span><small>{activeQuestion.sourceStoryTitle}</small></div><p className="sa-placement__question-prompt">{activeQuestion.prompt || (activeQuestion.questionType === "character_to_pinyin_typing" ? `Type the pinyin for ${activeQuestion.targetWord}.` : "Choose the best answer.")}</p><h2 lang="zh-Hant">{activeQuestion.targetWord}</h2>{activeQuestion.questionType === "character_to_pinyin_typing" ? <label className="sa-placement__input">Pinyin with tones<input autoFocus value={pinyinDraft} onChange={(event) => setPinyinDraft(event.target.value)} placeholder="e.g. nǐ hǎo or ni3 hao3" onKeyDown={(event) => { if (event.key === "Enter" && pinyinDraft.trim()) { if (index + 1 === displayedQuestions.length) void finish(); else next(); } }} /></label> : <div className="sa-placement__options" role="group" aria-label="Answer options">{activeQuestion.options.map((option, optionIndex) => <button key={option} type="button" className={`sa-placement__option${selected === option ? " is-selected" : ""}`} onClick={() => saveCurrentAnswer(option)}><span>{optionIndex + 1}</span>{option}</button>)}</div>}<div className="sa-placement__question-actions"><span>{error && <span role="alert">{error}</span>}</span>{index + 1 === displayedQuestions.length ? <StudentButton variant="primary" disabled={!selected.trim()} onClick={() => void finish()}>Finish test</StudentButton> : <StudentButton variant="primary" iconTrailing="arrow_forward" disabled={!selected.trim()} onClick={next}>Next question</StudentButton>}</div></StudentSection>
    </>}
  </div>;
}

function PlacementLiveShell({ status, heading, body }: { status: string; heading: string; body: string }) {
  return <div className="sa-page-container sa-placement"><StudentPageHeader eyebrowEn="Placement" eyebrowZh="Placement" titleZh="入門測驗" titleEn="Placement Test" aside={<StudentStatusPill tone={status === "Unavailable" || status === "Not available" ? "neutral" : "info"}>{status}</StudentStatusPill>} /><StudentSection variant="panel" className="sa-placement__card"><div className="sa-placement__accent" aria-hidden="true" /><div className="sa-placement__body"><div className="sa-placement__intro"><div className="sa-placement__icon" aria-hidden="true"><StudentIcon name="flag" size={20} role="decorative" /></div><div className="sa-placement__intro-copy"><p className="sa-placement__kicker">Assessment availability</p><h2>{heading}</h2><p className="sa-placement__description">{body}</p></div></div></div></StudentSection></div>;
}

export default function PlacementStubPage({ adapter, live = true }: PlacementStubPageProps & { live?: boolean }) {
  return live ? <PlacementAssessmentPage /> : <UnavailablePlacementPage adapter={adapter ?? unavailablePlacementSession} />;
}
