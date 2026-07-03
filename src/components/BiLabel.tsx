import translations from "../i18n/translations.json";

/**
 * Bilingual label: Traditional Chinese primary, English subtitle.
 * Usage:
 *   <BiLabel k="log_out" />                    (looks up src/translations.json)
 *   <BiLabel zh="登出" en="Log out" />          (inline, for dynamic/interpolated text)
 *   <BiLabel k="submit_story_to_teacher" block />
 */
type BiLabelProps =
  | { k: string; zh?: never; en?: never; block?: boolean }
  | { k?: never; zh: string; en: string; block?: boolean };

function resolve(props: { k?: string; zh?: string; en?: string }): { zh: string; en: string } {
  if (props.k) {
    const entry = (translations as Record<string, { zh: string; en: string }>)[props.k];
    if (!entry) throw new Error(`Missing translation key: ${props.k}`);
    return entry;
  }
  return { zh: props.zh!, en: props.en! };
}

export function BiLabel(props: BiLabelProps) {
  const { zh, en } = resolve(props);
  return (
    <span className={`bi-label${props.block ? " bi-label--block" : ""}`}>
      <span className="bi-zh" lang="zh-Hant">{zh}</span>
      <small className="bi-en" lang="en">{en}</small>
    </span>
  );
}

/** Bilingual paragraph: Chinese on top, English below in muted smaller text. */
type BiTextProps = { k: string; zh?: never; en?: never } | { k?: never; zh: string; en: string };

export function BiText(props: BiTextProps) {
  const { zh, en } = resolve(props);
  return (
    <span className="bi-text">
      <span className="bi-text-zh" lang="zh-Hant">{zh}</span>
      <span className="bi-text-en" lang="en">{en}</span>
    </span>
  );
}
