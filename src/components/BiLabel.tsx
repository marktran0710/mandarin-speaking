/**
 * Bilingual label: Traditional Chinese primary, English subtitle.
 * Usage:
 *   <BiLabel zh="登出" en="Log out" />
 *   <BiLabel zh="提交故事給老師" en="Submit Story to Teacher" block />
 */
export function BiLabel({
  zh,
  en,
  block = false,
}: {
  zh: string;
  en: string;
  block?: boolean;
}) {
  return (
    <span className={`bi-label${block ? " bi-label--block" : ""}`}>
      <span className="bi-zh">{zh}</span>
      <small className="bi-en">{en}</small>
    </span>
  );
}

/** Bilingual paragraph: Chinese on top, English below in muted smaller text. */
export function BiText({ zh, en }: { zh: string; en: string }) {
  return (
    <span className="bi-text">
      <span className="bi-text-zh">{zh}</span>
      <span className="bi-text-en">{en}</span>
    </span>
  );
}
