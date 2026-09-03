import type { CSSProperties } from "react";
/* Borrows .tonemark-stroke-animated + the tonemark-draw keyframes, which
   already normalise stroke-dasharray across straight/diagonal/curved paths
   via pathLength="1" and fail safe to fully-drawn. */
import "./ToneMark.css";

interface ToneStrokeProps {
  tone: 1 | 2 | 3 | 4;
  className?: string;
  /** Width in px; height follows the 22:16 viewBox ratio. */
  width?: number;
  /** Draw the stroke in instead of rendering it complete. Respects
   * prefers-reduced-motion (handled in ToneMark.css). */
  animated?: boolean;
  /** Seconds to wait before drawing, so a row of strokes can trace
   * left-to-right in reading order. */
  delay?: number;
}

/* One tone contour, in the same stroke language as ToneMark (4px round caps,
   the tone's own color) but cropped to a single character's width so it can
   sit directly above the Han character it belongs to. Path geometry is
   ToneMark's, shifted to a shared 22-wide origin. */
const TONE_PATHS: Record<1 | 2 | 3 | 4, { d: string; color: string }> = {
  1: { d: "M2 8 H20", color: "var(--tone1)" }, // ā — level
  2: { d: "M2 14 L20 2", color: "var(--jade)" }, // á — rising
  3: { d: "M2 5 C5 16 17 16 20 2", color: "var(--gold)" }, // ǎ — dipping
  4: { d: "M2 2 L20 14", color: "var(--seal)" }, // à — falling
};

/**
 * A single Mandarin tone contour, drawn above the character that carries it.
 * Decorative — the tone is already conveyed by the pinyin text nearby, so this
 * is hidden from assistive tech.
 */
export default function ToneStroke({
  tone,
  className,
  width = 22,
  animated = false,
  delay = 0,
}: ToneStrokeProps) {
  const { d, color } = TONE_PATHS[tone];
  return (
    <svg
      className={className}
      width={width}
      height={(width * 16) / 22}
      viewBox="0 0 22 16"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d={d}
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
        fill="none"
        {...(animated
          ? {
              pathLength: 1,
              className: "tonemark-stroke-animated",
              style: { "--tonemark-delay": `${delay}s` } as CSSProperties,
            }
          : {})}
      />
    </svg>
  );
}
