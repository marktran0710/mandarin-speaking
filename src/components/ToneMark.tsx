interface ToneMarkProps {
  className?: string;
  size?: number;
  /** When false, all four strokes use currentColor instead of the tone
   * palette — for placing the mark on top of a solid accent color. */
  colorful?: boolean;
}

/**
 * The four Mandarin tone contours (ā á ǎ à) rendered as a single line mark —
 * the app's signature: flat / rising / dip / falling, in that reading order.
 * Each stroke uses its tone's color (the app's real tone-color convention),
 * making the mark itself a small burst of the "tone colors" palette.
 * Purely decorative, so it's hidden from assistive tech.
 */
export default function ToneMark({ className, size = 28, colorful = true }: ToneMarkProps) {
  const c = (tone: string) => (colorful ? `var(${tone})` : "currentColor");
  return (
    <svg
      className={className}
      width={size}
      height={(size * 32) / 108}
      viewBox="0 0 108 32"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M2 10 H20" stroke={c("--tone1")} strokeWidth="4" strokeLinecap="round" />
      <path d="M28 22 L46 6" stroke={c("--jade")} strokeWidth="4" strokeLinecap="round" />
      <path
        d="M54 13 C58 27 68 27 72 6"
        stroke={c("--gold")}
        strokeWidth="4"
        strokeLinecap="round"
        fill="none"
      />
      <path d="M80 6 L98 26" stroke={c("--seal")} strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}
