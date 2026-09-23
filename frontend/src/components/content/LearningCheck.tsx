import { useEffect, useState } from "react";
import {
  getResearchProbesDue,
  postResearchProbeResponse,
  type ResearchProbeQuestion,
} from "../../services/api/vocabulary-research";
import { BiLabel, BiText } from "../ui/BiLabel";
import StudentIcon from "../navigation/StudentIcon";
import {
  StudentSection,
  StudentSectionBody,
  StudentSectionHeader,
  StudentStack,
} from "../student-workspace/student-layout";
import "./TopicSelector.css";

interface LearningCheckProps {
  onDone: () => void;
}

/** Epic 7, Task 7.8: the student-facing "Learning Check" - deliberately
 * never called a research probe in any visible copy. Task 7.6: no question
 * ever shows whether the previous answer was correct, the correct answer,
 * or a running score - only "answered" progress through the list, since
 * feedback here would itself be an intervention on the outcome measure. */
export default function LearningCheck({ onDone }: LearningCheckProps) {
  const [questions, setQuestions] = useState<ResearchProbeQuestion[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getResearchProbesDue()
      .then((session) => { if (!cancelled) setQuestions(session.questions); })
      .catch(() => { if (!cancelled) setLoadError(true); });
    return () => { cancelled = true; };
  }, []);

  const submitAnswer = async () => {
    if (!questions || selected === null) return;
    const question = questions[index];
    setSubmitting(true);
    try {
      await postResearchProbeResponse(
        question.assignmentId,
        selected,
        `learning-check:${question.assignmentId}:${Date.now()}`,
      );
    } catch {
      // Best-effort: a failed submit still advances the student past this
      // question rather than blocking the flow - there is no retry UI for
      // a read-only measurement.
    }
    setSubmitting(false);
    setSelected(null);
    if (index + 1 < questions.length) {
      setIndex(index + 1);
    } else {
      setFinished(true);
    }
  };

  if (loadError || (questions && questions.length === 0)) {
    onDone();
    return null;
  }

  if (finished) {
    return (
      <StudentStack className="topic-selector">
        <StudentSection className="empty-state" variant="soft" aria-labelledby="lc-done-title">
          <div className="empty-icon"><StudentIcon name="spark" size={28} /></div>
          <StudentSectionHeader
            headingId="lc-done-title"
            title={<BiLabel zh="小測驗完成" pinyin="Xiǎo cèyàn wánchéng" en="Check complete" align="center" />}
          />
          <p><BiText zh="謝謝。" en="Thank you." /></p>
          <button type="button" className="ts-dash-continue-action" onClick={onDone}>
            <BiLabel zh="繼續" en="Continue" />
            <StudentIcon name="arrow-right" size={17} aria-hidden="true" />
          </button>
        </StudentSection>
      </StudentStack>
    );
  }

  if (!questions) {
    return (
      <StudentStack className="topic-selector">
        <StudentSection className="empty-state" variant="soft" aria-labelledby="lc-loading-title">
          <div className="empty-icon"><StudentIcon name="spark" size={28} /></div>
          <StudentSectionHeader headingId="lc-loading-title" title={<BiLabel k="loading_activities" />} />
        </StudentSection>
      </StudentStack>
    );
  }

  const question = questions[index];

  return (
    <StudentStack className="topic-selector">
      <StudentSection className="ts-dashboard" variant="soft" aria-labelledby="lc-question-title">
        <StudentSectionHeader
          headingId="lc-question-title"
          title={<BiLabel zh="小測驗" pinyin="Xiǎo cèyàn" en="Learning Check" align="left" />}
        />
        <StudentSectionBody>
          <p className="ts-dash-kicker">
            <BiLabel en={`Question ${index + 1} of ${questions.length}`} zh={`第 ${index + 1} / ${questions.length} 題`} />
          </p>
          <p>{question.prompt}</p>
          <div className="lc-choice-list">
            {(question.choices ?? []).map((choice) => (
              <button
                key={choice}
                type="button"
                className={`lc-choice${selected === choice ? " lc-choice--selected" : ""}`}
                aria-pressed={selected === choice}
                onClick={() => setSelected(choice)}
              >
                {choice}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="ts-dash-continue-action"
            disabled={selected === null || submitting}
            onClick={() => void submitAnswer()}
          >
            <BiLabel zh="下一題" en={index + 1 < questions.length ? "Next" : "Finish"} />
            <StudentIcon name="arrow-right" size={17} aria-hidden="true" />
          </button>
        </StudentSectionBody>
      </StudentSection>
    </StudentStack>
  );
}
