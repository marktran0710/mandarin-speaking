import type { VocabQuizEntry, VocabQuizQuestion, VocabQuizQuestionResult } from "@entities/vocabulary";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill from "@shared/ui/student/StudentStatusPill";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
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
    title: "聲調提示",
    icon: "graphic_eq",
    copy: "第一聲平，第二聲上升，第三聲先降後升，第四聲下降。",
  };
  return {
    title: "意思提示",
    icon: "lightbulb",
    copy: "提交前，把字形、讀音和意思連在一起。",
  };
}

export default function QuizRail({ flow, question }: QuizRailProps) {
  const total = flow.questionLimit ?? flow.entries.length;
  const support = supportCopy(question);

  return (
    <aside className="sa-quiz__rail sa-quiz__rail--sticky" aria-label="測驗進度與提示">
      <StudentSection variant="panel" className="sa-quiz__rail-card">
        <div className="sa-quiz__rail-heading"><StudentSystemText k="assessment" /><StudentStatusPill tone="success"><StudentSystemText k="inProgress" withinControl /></StudentStatusPill></div>
        <div className="sa-quiz__stats">
          <div><span><StudentSystemText k="done" /></span><strong>{flow.results.length}<small> / {total}</small></strong></div>
          <div><span><StudentSystemText k="left" /></span><strong>{Math.max(0, total - flow.results.length)}</strong></div>
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
        <div className="sa-quiz__rail-heading"><StudentSystemText k="questionMap" /><span className="sa-quiz__map-legend"><i className="is-done" /> 完成 <i className="is-current" /> <StudentSystemText k="current" /></span></div>
        <ol>
          {Array.from({ length: total }, (_, index) => {
            const result = resultAt(flow.results, index);
            const current = index === flow.index && !result;
            return (
              <li
                key={index}
                className={`${current ? "is-current" : ""} ${result ? "is-done" : "is-pending"}`}
                aria-current={current ? "step" : undefined}
                aria-label={`第 ${index + 1} 題${result ? "，已完成" : current ? "，目前題目" : ""}`}
              >
                {index + 1}
              </li>
            );
          })}
        </ol>
      </StudentSection>
    </aside>
  );
}
