import type { ReactNode } from "react";
import { BiLabel, BiText } from "./BiLabel";
import "./StudentPageHeader.css";

/** The unified title block of every non-practice student page (see the
 * student-shell design): eyebrow + zh/pinyin/en h1 + optional one-line lede,
 * always the same size and position so switching pages never "changes
 * worlds". Slot `aside` for a page's small extra chrome (a filter, a badge)
 * without breaking the shared rhythm. */
export default function StudentPageHeader({
  eyebrow,
  title,
  lede,
  aside,
}: {
  eyebrow: { zh: string; pinyin?: string; en: string };
  title: { zh: string; pinyin?: string; en: string };
  lede?: { zh: string; pinyin?: string; en: string };
  aside?: ReactNode;
}) {
  return (
    <header className="student-page-header">
      <div className="student-page-header-copy">
        <p className="eyebrow">
          <BiLabel zh={eyebrow.zh} pinyin={eyebrow.pinyin} en={eyebrow.en} align="left" />
        </p>
        <h1>
          <BiLabel zh={title.zh} pinyin={title.pinyin} en={title.en} align="left" />
        </h1>
        {lede && (
          <p className="student-page-lede">
            <BiText zh={lede.zh} pinyin={lede.pinyin} en={lede.en} />
          </p>
        )}
      </div>
      {aside && <div className="student-page-header-aside">{aside}</div>}
    </header>
  );
}
