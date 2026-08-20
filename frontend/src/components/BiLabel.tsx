import translations from "../i18n/translations.json";

/**
 * Bilingual label: Traditional Chinese primary, English subtitle.
 * Usage:
 *   <BiLabel k="log_out" />                    (looks up src/translations.json)
 *   <BiLabel zh="登出" en="Log out" />          (inline, for dynamic/interpolated text)
 *   <BiLabel k="submit_story_to_teacher" block />
 *
 * `pinyin` is optional (not every translations.json entry has one yet) — when
 * present it renders as a small romanization line between the Chinese and
 * English text, for learners who can't read the characters yet.
 */
type BiLabelProps =
  | { k: string; zh?: never; en?: never; pinyin?: never; block?: boolean }
  | { k?: never; zh: string; en: string; pinyin?: string; block?: boolean };

function resolve(props: {
  k?: string;
  zh?: string;
  en?: string;
  pinyin?: string;
}): { zh: string; en: string; pinyin?: string } {
  if (props.k) {
    const entry = (translations as Record<string, { zh: string; en: string; pinyin?: string }>)[
      props.k
    ];
    if (!entry) throw new Error(`Missing translation key: ${props.k}`);
    return entry;
  }
  return { zh: props.zh!, en: props.en!, pinyin: props.pinyin };
}

export function BiLabel(props: BiLabelProps) {
  const { zh, en, pinyin } = resolve(props);
  return (
    <span className={`bi-label${props.block ? " bi-label--block" : ""}`}>
      <span className="bi-zh" lang="zh-Hant">{zh}</span>
      {pinyin && <span className="bi-pinyin">{pinyin}</span>}
      <small className="bi-en" lang="en">{en}</small>
    </span>
  );
}

/** Bilingual paragraph: Chinese on top, English below in muted smaller text. */
type BiTextProps =
  | { k: string; zh?: never; en?: never; pinyin?: never }
  | { k?: never; zh: string; en: string; pinyin?: string };

export function BiText(props: BiTextProps) {
  const { zh, en, pinyin } = resolve(props);
  return (
    <span className="bi-text">
      <span className="bi-text-zh" lang="zh-Hant">{zh}</span>
      {pinyin && <span className="bi-text-pinyin">{pinyin}</span>}
      <span className="bi-text-en" lang="en">{en}</span>
    </span>
  );
}
