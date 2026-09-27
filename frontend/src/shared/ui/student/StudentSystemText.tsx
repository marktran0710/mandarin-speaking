import { Children, createContext, Fragment, isValidElement, useContext, useState, type PointerEvent, type ReactNode } from "react";
import { studentUiCopy, type StudentUiCopy, type StudentUiCopyKey } from "../../../i18n/student-ui-copy";
import "./StudentSystemText.css";

export interface StudentSystemTextProps {
  k: StudentUiCopyKey;
  english?: "supporting";
  withinControl?: boolean;
  className?: string;
  children?: ReactNode;
}

export interface StudentSystemTextHint {
  pinyin: string;
  english?: string;
}

/** Suppresses per-word popups while StudentButton renders one combined hint. */
export const StudentControlTooltipContext = createContext(false);

/** Static learner UI copy with pinyin and an English gloss; never use this for lesson data. */
export default function StudentSystemText({
  k,
  english,
  withinControl = false,
  className = "",
  children,
}: StudentSystemTextProps) {
  const copy: StudentUiCopy = studentUiCopy[k];
  const label = children ?? copy.zh;
  const suppressTooltip = useContext(StudentControlTooltipContext);
  const [touchOpen, setTouchOpen] = useState(false);

  const handlePointerDown = (event: PointerEvent<HTMLSpanElement>) => {
    if (event.pointerType !== "mouse") setTouchOpen((open) => !open);
  };

  return (
    <span
      className={`sa-system-text${withinControl ? " is-within-control" : ""}${className ? ` ${className}` : ""}`}
      tabIndex={withinControl ? undefined : 0}
      aria-label={copy.zh}
      data-touch-open={touchOpen || undefined}
      onPointerDown={handlePointerDown}
    >
      <span className="sa-system-text__zh" lang="zh-Hant">{label}</span>
      {english === "supporting" && copy.en && <small className="sa-system-text__en" lang="en">{copy.en}</small>}
      {!suppressTooltip && (
        <span
          className="sa-system-text__tooltip"
          role="tooltip"
          aria-label={copy.en ? `${copy.pinyin} · ${copy.en}` : copy.pinyin}
        >
          <span className="sa-system-text__tooltip-pinyin">{copy.pinyin}</span>
          {copy.en && <small className="sa-system-text__tooltip-en" lang="en">{copy.en}</small>}
        </span>
      )}
    </span>
  );
}

export function collectStudentSystemTextHints(children: ReactNode): StudentSystemTextHint[] {
  const hints: StudentSystemTextHint[] = [];
  const visit = (nodes: ReactNode) => {
    Children.forEach(nodes, (node) => {
      if (!isValidElement(node)) return;
      if (node.type === StudentSystemText) {
        const props = node.props as StudentSystemTextProps;
        const copy = studentUiCopy[props.k];
        hints.push({ pinyin: copy.pinyin, english: copy.en });
        return;
      }
      if (node.type === Fragment || node.props.children) visit(node.props.children);
    });
  };
  visit(children);
  return hints;
}
