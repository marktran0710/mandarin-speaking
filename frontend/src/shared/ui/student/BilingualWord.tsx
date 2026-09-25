import type { CSSProperties } from "react";

/**
 * The one bilingual-text primitive every screen uses. Hierarchy per
 * DESIGN.md: Hanzi strongest, pinyin secondary (ruby, 55-60% of Hanzi size),
 * English/gloss secondary. Never a 3rd visible tier stacked below both —
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
  hero: "var(--sa-text-character-hero)",
  display: "var(--sa-text-character-display)",
  inline: "var(--sa-text-character-inline)",
};
const LEADING_VAR: Record<BilingualWordSize, string> = {
  hero: "var(--sa-leading-character-hero)",
  display: "var(--sa-leading-character-display)",
  inline: "var(--sa-leading-character-inline)",
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
            fontFamily: "var(--sa-font-body)",
            fontSize: SIZE_VAR[size],
            lineHeight: LEADING_VAR[size],
            color: toneHighlight ? "var(--sa-primary)" : "var(--sa-on-surface)",
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
            fontFamily: "var(--sa-font-body)",
            fontSize: SIZE_VAR[size],
            lineHeight: LEADING_VAR[size],
            color: toneHighlight ? "var(--sa-primary)" : "var(--sa-on-surface)",
            fontWeight: toneHighlight ? 500 : 400,
          }}
        >
          {hanzi}
        </span>
      )}
      {gloss && (
        <span
          style={{
            fontFamily: "var(--sa-font-label)",
            fontSize: "var(--sa-text-body-sm)",
            lineHeight: "var(--sa-leading-body-sm)",
            color: "var(--sa-on-surface-variant)",
            fontStyle: "italic",
          }}
        >
          {gloss}
        </span>
      )}
    </span>
  );
}
