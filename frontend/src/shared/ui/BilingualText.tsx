import translations from "../../i18n/translations";
import "./BilingualText.css";

export type BilingualTextProps =
  | { k: string; zh?: never; en?: never; pinyin?: never; block?: boolean; align?: "left" | "center" }
  | { k?: never; zh: string; en: string; pinyin?: string; block?: boolean; align?: "left" | "center" };

function resolve(props: { k?: string; zh?: string; en?: string; pinyin?: string }): { zh: string; en: string; pinyin?: string } {
  if (props.k) {
    const entry = (translations as Record<string, { zh: string; en: string; pinyin?: string }>)[props.k];
    if (!entry) throw new Error(`Missing translation key: ${props.k}`);
    return entry;
  }
  return { zh: props.zh!, en: props.en!, pinyin: props.pinyin };
}

/** Canonical bilingual label; keeps Chinese, optional pinyin, and English in one accessible group. */
export default function BilingualText(props: BilingualTextProps) {
  const { zh, en, pinyin } = resolve(props);
  return (
    <span className={`bi-label${props.block ? " bi-label--block" : ""}${props.align ? ` bi-label--${props.align}` : ""}`}>
      <span className="bi-zh" lang="zh-Hant">{zh}</span>
      {pinyin && <span className="bi-pinyin">{pinyin}</span>}
      <small className="bi-en" lang="en">{en}</small>
    </span>
  );
}

export type BiLabelProps = BilingualTextProps;
export const BiLabel = BilingualText;

export type BiTextProps =
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
