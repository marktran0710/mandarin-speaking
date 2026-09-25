import type { VocabQuizEntry, VocabQuizQuestion, VocabQuizQuestionResult } from "@entities/vocabulary";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill from "@shared/ui/student/StudentStatusPill";
import { questionPresentation } from "./questionModel";

interface QuizRailFlow {
  entries: VocabQuizEntry[];
  results: VocabQuizQuestionResult[];
  questionLimit: number | null;
  index: number;
}

interface QuizRailProps {
  flow: QuizRailFlow;
  question: VocabQuizQuestion;
}

function resultAt(results: VocabQuizQuestionResult[], index: number) {
  return results.find((result) => result.questionIndex === index) ?? results[index];
}

function supportCopy(question: VocabQuizQuestion) {
  const surface = questionPresentation(question).surface;
  if (surface === "context") return null;
  if (surface === "pinyin") return {
    title: "Tone guide",
    icon: "graphic_eq",
    copy: "Tone 1 stays level, tone 2 rises, tone 3 dips, and tone 4 falls.",
  };
  return {
    title: "Meaning anchor",
    icon: "lightbulb",
    copy: "Connect the character form, reading, and meaning before you submit.",
  };
}

export default function QuizRail({ flow, question }: QuizRailProps) {
  const total = flow.questionLimit ?? flow.entries.length;
  const correct = flow.results.filter((result) => result.correct).length;
  const accuracy = flow.results.length > 0 ? `${Math.round((correct / flow.results.length) * 100)}%` : "—";
  const support = supportCopy(question);

  return (
    <aside className="sa-quiz__rail sa-quiz__rail--sticky" aria-label="Quiz progress and support">
      <StudentSection variant="panel" className="sa-quiz__rail-card">
        <div className="sa-quiz__rail-heading"><span>Assessment</span><StudentStatusPill tone="success">In progress</StudentStatusPill></div>
        <div className="sa-quiz__stats">
          <div><span>Accuracy</span><strong>{accuracy}</strong></div>
          <div><span>Done</span><strong>{flow.results.length}<small> / {total}</small></strong></div>
          <div><span>Left</span><strong>{Math.max(0, total - flow.results.length)}</strong></div>
        </div>
      </StudentSection>

      {support && (
        <StudentSection variant="tinted" className="sa-quiz__rail-card sa-quiz__taxonomy-card">
          <div className="sa-quiz__rail-heading">
            <span><StudentIcon name={support.icon} size={17} role="decorative" /> {support.title}</span>
            <span className="sa-quiz__taxonomy-dot" aria-hidden="true" />
          </div>
          <p>{support.copy}</p>
        </StudentSection>
      )}

      <StudentSection variant="panel" className="sa-quiz__rail-card sa-quiz__question-map">
        <div className="sa-quiz__rail-heading"><span>Question map</span><span className="sa-quiz__map-legend"><i className="is-done" /> Done <i className="is-current" /> Current</span></div>
        <ol>
          {Array.from({ length: total }, (_, index) => {
            const result = resultAt(flow.results, index);
            const current = index === flow.index;
            return (
              <li key={index} className={`${current ? "is-current" : ""} ${result ? (result.correct ? "is-correct" : "is-incorrect") : "is-pending"}`}>
                {result ? <StudentIcon name={result.correct ? "check" : "close"} size={16} role="decorative" /> : index + 1}
              </li>
            );
          })}
        </ol>
      </StudentSection>
    </aside>
  );
}
