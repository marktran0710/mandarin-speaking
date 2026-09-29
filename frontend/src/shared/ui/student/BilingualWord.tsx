import type { CSSProperties } from "react";

/**
 * The one bilingual-text primitive every screen uses. Hierarchy per
 * DESIGN.md: Hanzi strongest, pinyin secondary (ruby, 55-60% of Hanzi size),
 * English/gloss secondary. Never a 3rd visible tier stacked below both ??
 * pinyin lives in the ruby <rt>, gloss is a separate sibling line.
 */
export type BilingualWordSize = "hero" | "display" | "inline";

interface BilingualWordProps {
  hanzi: string;
  pinyin?: string;
  gloss?: string;
  size?: BilingualWordSize;
  toneHighlight?: boolean;
  className?: string;
  style?: CSSProperties;
}

const SIZE_VAR: Record<BilingualWordSize, string> = {
  hero: "var(--font-size-character-hero)",
  display: "var(--font-size-character-display)",
  inline: "var(--font-size-character-inline)",
};
const LEADING_VAR: Record<BilingualWordSize, string> = {
  hero: "var(--leading-character-hero)",
  display: "var(--leading-character-display)",
  inline: "var(--leading-character-inline)",
};

export default function BilingualWord({
  hanzi,
  pinyin,
  gloss,
  size = "display",
  toneHighlight = false,
  className = "",
  style,
}: BilingualWordProps) {
  return (
    <span
      className={`sa-bilingual-word ${className}`.trim()}
      style={{
        display: "inline-flex",
        flexDirection: "column",
        gap: 2,
        ...style,
      }}
    >
      {pinyin ? (
        <ruby
          className="sa-ruby"
          lang="zh-Hant"
          style={{
            fontFamily: "var(--font-hanzi)",
            fontSize: SIZE_VAR[size],
            lineHeight: LEADING_VAR[size],
            color: toneHighlight ? "var(--color-primary)" : "var(--color-ink)",
            fontWeight: toneHighlight ? 500 : 400,
          }}
        >
          {hanzi}
          <rp>(</rp>
          <rt>{pinyin}</rt>
          <rp>)</rp>
        </ruby>
      ) : (
        <span
          lang="zh-Hant"
          style={{
            fontFamily: "var(--font-hanzi)",
            fontSize: SIZE_VAR[size],
            lineHeight: LEADING_VAR[size],
            color: toneHighlight ? "var(--color-primary)" : "var(--color-ink)",
            fontWeight: toneHighlight ? 500 : 400,
            // Parent bubbles set overflow-wrap:anywhere, which lets a closing
            // 。？ wrap onto a line by itself; keep normal CJK line-breaking.
            overflowWrap: "normal",
            lineBreak: "strict",
          }}
        >
          {hanzi}
        </span>
      )}
      {gloss && (
        <span
          style={{
            fontFamily: "var(--font-ui)",
            fontSize: "var(--font-size-small)",
            lineHeight: "var(--leading-small)",
            color: "var(--color-muted)",
            fontStyle: "italic",
          }}
        >
          {gloss}
        </span>
      )}
    </span>
  );
}
