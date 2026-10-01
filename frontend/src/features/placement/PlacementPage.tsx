import { useEffect, useMemo, useState } from "react";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentPage from "@shared/ui/student/StudentPage";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill, { type StudentStatusTone } from "@shared/ui/student/StudentStatusPill";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import type { StudentUiCopyKey } from "../../i18n/student-ui-copy";
import {
  unavailablePlacementSession,
  usePlacementSession,
  type PlacementSessionAdapter,
  type PlacementSessionStatus,
} from "./placementSession";
import "./PlacementPage.css";
import {
  completePlacementAttempt,
  getPlacementBlueprint,
  startPlacementAttempt,
  type PlacementAnswer,
  type PlacementBlueprint,
  type PlacementQuestion,
  type PlacementResult,
} from "@shared/api/placement-test";

export interface PlacementPageProps {
  adapter?: PlacementSessionAdapter;
}

/** Wiring for a placement test that gates a new account (see usePlacementGate). */
interface PlacementGateProps {
  /** The account must finish this test before the rest of Student Mode opens. */
  gated?: boolean;
  /** Called once the attempt is saved, so the gate can re-check and unlock. */
  onCompleted?: () => void;
  /** Shown on the result screen as the way on into the lessons. */
  onStartLearning?: () => void;
}

interface PlacementStatusPresentation {
  labelKey: StudentUiCopyKey;
  tone: StudentStatusTone;
  headingKey: StudentUiCopyKey;
  bodyKey: StudentUiCopyKey;
}

const STATUS_PRESENTATION: Record<PlacementSessionStatus, PlacementStatusPresentation> = {
  unavailable: {
    labelKey: "notAvailable",
    tone: "neutral",
    headingKey: "placementUnavailable",
    bodyKey: "placementNotConfigured",
  },
  loading: {
    labelKey: "loading",
    tone: "info",
    headingKey: "assessmentLoading",
    bodyKey: "assessmentPreparing",
  },
  ready: {
    labelKey: "ready",
    tone: "info",
    headingKey: "assessmentReady",
    bodyKey: "assessmentStartHint",
  },
  complete: {
    labelKey: "complete",
    tone: "success",
    headingKey: "placementComplete",
    bodyKey: "placementResultShown",
  },
  error: {
    labelKey: "unavailable",
    tone: "danger",
    headingKey: "placementUnavailable",
    bodyKey: "placementLoadError",
  },
};

function UnavailablePlacementPage({ adapter = unavailablePlacementSession }: PlacementPageProps) {
  const session = usePlacementSession(adapter);
  const presentation = STATUS_PRESENTATION[session.status];

  return (
    <StudentPage
      layout="task"
      header={
        <StudentPageHeader
          eyebrowKey="placement"
          titleKey="placementTest"
          aside={<StudentStatusPill tone={presentation.tone}><StudentSystemText k={presentation.labelKey} withinControl /></StudentStatusPill>}
        />
      }
    >
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
              <p className="sa-placement__kicker"><StudentSystemText k="assessmentAvailability" /></p>
              <h2 id="placement-test-heading"><StudentSystemText k={presentation.headingKey} /></h2>
              <p className="sa-placement__description"><StudentSystemText k={presentation.bodyKey} /></p>
            </div>
          </div>

          <div className="sa-placement__notice" role="status" aria-live="polite">
            <StudentIcon name="info" size={18} role="decorative" />
            <p>
              <StudentSystemText k="placementClosedNotice" />
              <StudentSystemText k="placementEnabledNotice" />
            </p>
          </div>
        </div>
      </StudentSection>
    </StudentPage>
  );
}

function labelFor(question: PlacementQuestion): StudentUiCopyKey {
  if (question.questionType === "basic_meaning_mcq") return "meaningCheck";
  if (question.questionType === "character_to_pinyin_typing") return "readingRecall";
  return "contextClue";
}

function shuffleQuestions(questions: PlacementQuestion[]): PlacementQuestion[] {
  const shuffled = [...questions];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
  }
  return shuffled;
}

function PlacementAssessmentPage({ gated, onCompleted, onStartLearning }: PlacementGateProps) {
  const [blueprint, setBlueprint] = useState<PlacementBlueprint | null>(null);
  const [attemptId, setAttemptId] = useState("");
  const [questions, setQuestions] = useState<PlacementQuestion[]>([]);
  const [randomize, setRandomize] = useState(false);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [times, setTimes] = useState<Record<string, number>>({});
  const [answeredAt, setAnsweredAt] = useState<Record<string, string>>({});
  const [questionStartedAt, setQuestionStartedAt] = useState(() => Date.now());
  const [result, setResult] = useState<PlacementResult | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "starting" | "answering" | "submitting" | "result" | "error">("loading");
  const [error, setError] = useState("");
  const [pinyinDraft, setPinyinDraft] = useState("");
  const displayedQuestions = useMemo(() => randomize ? shuffleQuestions(questions) : questions, [questions, randomize]);
  const question = displayedQuestions[index];

  const loadBlueprint = () => {
    setStatus("loading");
    setError("");
    void getPlacementBlueprint().then((data) => { setBlueprint(data); setQuestions(data.questions); setStatus("ready"); }).catch((reason) => { setError(reason instanceof Error ? reason.message : "入門測驗載入失敗。請再試一次。"); setStatus("error"); });
  };

  useEffect(() => {
    let active = true;
    void getPlacementBlueprint().then((data) => {
      if (!active) return;
      setBlueprint(data);
      setQuestions(data.questions);
      setStatus("ready");
    }).catch((reason) => {
      if (!active) return;
      setError(reason instanceof Error ? reason.message : "入門測驗載入失敗。請再試一次。");
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
      setAnsweredAt({});
      setIndex(0);
      setResult(null);
      setStatus("answering");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "入門測驗無法開始。請再試一次。");
      setStatus("error");
    }
  };

  const saveCurrentAnswer = (value: string) => {
    if (!question) return;
    setAnswers((current) => ({ ...current, [question.questionId]: value }));
    setTimes((current) => ({ ...current, [question.questionId]: Math.max(current[question.questionId] ?? 0, Date.now() - questionStartedAt) }));
    setAnsweredAt((current) => ({ ...current, [question.questionId]: new Date().toISOString() }));
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
    const finalAnsweredAt = new Date().toISOString();
    const responseAnswers: PlacementAnswer[] = displayedQuestions.map((item) => ({
      questionId: item.questionId,
      selectedAnswer: item.questionId === question.questionId ? finalAnswer.trim() : answers[item.questionId],
      timeMs: (times[item.questionId] ?? 0) + (item.questionId === question.questionId ? Math.max(0, now - questionStartedAt) : 0),
      answeredAt: item.questionId === question.questionId ? finalAnsweredAt : (answeredAt[item.questionId] ?? finalAnsweredAt),
    }));
    setStatus("submitting");
    setError("");
    try {
      const completed = await completePlacementAttempt(attemptId, responseAnswers);
      setResult(completed);
      setStatus("result");
      onCompleted?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "入門測驗無法提交。請再試一次。");
      setStatus("answering");
    }
  };

  const placementHeader = (aside?: React.ReactNode) => (
    <StudentPageHeader eyebrowKey="placement" titleKey="placementTest" aside={aside} />
  );

  if (status === "loading") {
    return <StudentPage layout="task" header={placementHeader(<StudentStatusPill tone="info"><StudentSystemText k="loading" withinControl /></StudentStatusPill>)} state="loading" />;
  }
  if (status === "error") {
    return (
      <StudentPage
        layout="task"
        header={placementHeader(<StudentStatusPill tone="danger"><StudentSystemText k="unavailable" withinControl /></StudentStatusPill>)}
      ><StudentSection variant="panel" className="sa-placement__result"><StudentIcon name="error" size={30} role="decorative" /><p className="sa-placement__result-kicker"><StudentSystemText k="placementTest" /></p><h2><StudentSystemText k="placementUnavailableTitle" /></h2><p><StudentSystemText k="retryNetwork" /></p><p className="sa-placement__error" role="alert">{error}</p><StudentButton variant="primary" onClick={loadBlueprint}><StudentSystemText k="retry" withinControl /></StudentButton></StudentSection></StudentPage>
    );
  }
  if (!blueprint?.configured || blueprint.questionCount === 0) {
    return (
      <StudentPage
        layout="task"
        header={placementHeader(<StudentStatusPill tone="neutral"><StudentSystemText k="notAvailable" withinControl /></StudentStatusPill>)}
        state="empty"
        emptyTitle={<StudentSystemText k="placementNotSet" />}
        emptyText={<StudentSystemText k="noPlacementQuestions" />}
      />
    );
  }
  if (status === "result" && result) {
    const congratulations = result.messageKey === "CONGRATULATIONS";
    return (
      <StudentPage layout="task" header={placementHeader(<StudentStatusPill tone="success"><StudentSystemText k="complete" withinControl /></StudentStatusPill>)}>
        <StudentSection variant="panel" className="sa-placement__result">
          <StudentIcon name={congratulations ? "celebration" : "self_improvement"} size={34} role="decorative" />
          <p className="sa-placement__result-kicker"><StudentSystemText k="placementComplete" /></p>
          <h2>你答對 {result.correctCount} / {result.totalQuestions} 題。</h2>
          <p className="sa-placement__result-score">{result.percentage}%</p>
          <p><StudentSystemText k={congratulations ? "greatWork" : "keepPractising"} /></p>
          {onStartLearning && (
            <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={onStartLearning}>
              <StudentSystemText k="startLearning" withinControl />
            </StudentButton>
          )}
        </StudentSection>
      </StudentPage>
    );
  }

  const activeQuestion = displayedQuestions[index];
  const selected = activeQuestion?.questionType === "character_to_pinyin_typing" ? pinyinDraft : answers[activeQuestion?.questionId ?? ""] ?? "";
  const progress = displayedQuestions.length ? ((index + 1) / displayedQuestions.length) * 100 : 0;
  const isLastQuestion = index + 1 === displayedQuestions.length;

  const questionAction = isLastQuestion
    ? <StudentButton variant="primary" disabled={!selected.trim()} onClick={() => void finish()}><StudentSystemText k="finishQuiz" withinControl /></StudentButton>
    : <StudentButton variant="primary" iconTrailing="arrow_forward" disabled={!selected.trim()} onClick={next}><StudentSystemText k="nextQuestion" withinControl /></StudentButton>;

  return (
    <StudentPage
      layout="task"
      header={placementHeader(status === "answering" ? <StudentStatusPill tone="info">第 {index + 1} / {displayedQuestions.length} 題</StudentStatusPill> : undefined)}
    >
      {status === "ready" && <StudentSection variant="panel" className="sa-placement__start"><div>{gated && <p className="sa-placement__required" role="note"><StudentSystemText k="placementRequiredNotice" /></p>}<p className="sa-placement__kicker"><StudentSystemText k="placementTest" /> · <StudentSystemText k="shortDiagnostic" /></p><h2><StudentSystemText k="placementIntro" /></h2><p><StudentSystemText k="placementDataNote" />（{blueprint.questionCount} 題）</p></div><div className="sa-placement__start-controls"><label className="sa-placement__randomize"><input type="checkbox" checked={randomize} onChange={(event) => setRandomize(event.target.checked)} /> <StudentSystemText k="randomizeQuestions" /></label><StudentButton variant="primary" iconTrailing="arrow_forward" onClick={() => void start()}><StudentSystemText k="startTest" withinControl /></StudentButton></div></StudentSection>}
      {(status === "starting" || status === "submitting") && <StudentSection variant="panel" className="sa-placement__start"><p role="status">{status === "starting" ? <StudentSystemText k="startingAssessment" /> : <StudentSystemText k="saveAnswers" />}</p></StudentSection>}
      {status === "answering" && activeQuestion && <div className="sa-placement">
        <div className="sa-placement__progress" role="progressbar" aria-label="入門測驗進度" aria-valuemin={0} aria-valuemax={displayedQuestions.length} aria-valuenow={index + 1}><span style={{ width: `${progress}%` }} /></div>
        <StudentSection variant="panel" className="sa-placement__question"><div className="sa-placement__question-meta"><span><StudentSystemText k={labelFor(activeQuestion)} /></span><small>{activeQuestion.sourceStoryTitle}</small></div><p className="sa-placement__question-prompt">{activeQuestion.prompt || (activeQuestion.questionType === "character_to_pinyin_typing" ? <><StudentSystemText k="typePinyinReading" />：{activeQuestion.targetWord}</> : <StudentSystemText k="chooseOption" />)}</p><h2 lang="zh-Hant">{activeQuestion.targetWord}</h2>{activeQuestion.questionType === "character_to_pinyin_typing" ? <label className="sa-placement__input"><StudentSystemText k="pinyinWithTones" /><input autoFocus value={pinyinDraft} onChange={(event) => setPinyinDraft(event.target.value)} placeholder="例如：nǐ hǎo 或 ni3 hao3" onKeyDown={(event) => { if (event.key === "Enter" && pinyinDraft.trim()) { if (isLastQuestion) void finish(); else next(); } }} /></label> : <div className="sa-placement__options" role="group" aria-label="答案選項">{activeQuestion.options.map((option, optionIndex) => <button key={option} type="button" className={`sa-placement__option${selected === option ? " is-selected" : ""}`} onClick={() => saveCurrentAnswer(option)}><span>{optionIndex + 1}</span>{option}</button>)}</div>}<div className="sa-placement__question-footer">{error && <p role="alert" className="sa-placement__error">{error}</p>}{questionAction}</div></StudentSection>
      </div>}
    </StudentPage>
  );
}

export default function PlacementPage({
  adapter,
  live = true,
  ...gate
}: PlacementPageProps & PlacementGateProps & { live?: boolean }) {
  return live ? <PlacementAssessmentPage {...gate} /> : <UnavailablePlacementPage adapter={adapter ?? unavailablePlacementSession} />;
}
