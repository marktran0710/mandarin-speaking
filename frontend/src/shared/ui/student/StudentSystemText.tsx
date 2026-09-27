import { useState, type PointerEvent, type ReactNode } from "react";
import { studentUiCopy, type StudentUiCopy, type StudentUiCopyKey } from "../../../i18n/student-ui-copy";
import "./StudentSystemText.css";

export interface StudentSystemTextProps {
  k: StudentUiCopyKey;
  english?: "supporting";
  withinControl?: boolean;
  className?: string;
  children?: ReactNode;
}

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
  const [touchOpen, setTouchOpen] = useState(false);

  const handlePointerDown = (event: PointerEvent<HTMLSpanElement>) => {
    if (event.pointerType !== "mouse") setTouchOpen((open) => !open);
  };

  return (
    <span
      className={`sa-system-text${withinControl ? " is-within-control" : ""}${className ? ` ${className}` : ""}`}
      tabIndex={withinControl ? undefined : 0}
      title={copy.pinyin}
      aria-label={copy.zh}
      data-touch-open={touchOpen || undefined}
      onPointerDown={handlePointerDown}
    >
      <span className="sa-system-text__zh" lang="zh-Hant">{label}</span>
      {english === "supporting" && copy.en && <small className="sa-system-text__en" lang="en">{copy.en}</small>}
      <span
        className="sa-system-text__tooltip"
        role="tooltip"
        aria-label={copy.en ? `${copy.pinyin} · ${copy.en}` : copy.pinyin}
      >
        <span className="sa-system-text__tooltip-pinyin">{copy.pinyin}</span>
        {copy.en && <small className="sa-system-text__tooltip-en" lang="en">{copy.en}</small>}
      </span>
    </span>
  );
}
