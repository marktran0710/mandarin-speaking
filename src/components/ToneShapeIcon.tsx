export type ToneGroup = 1 | 2 | 3 | 4 | "mixed";

const TONE_SHAPE_PATHS: Record<ToneGroup, string> = {
  1: "M4 14 H28",
  2: "M4 22 L28 6",
  3: "M4 10 C10 24 22 24 28 6",
  4: "M4 6 L28 22",
  mixed: "M4 14 H10 M14 22 L20 6 M24 10 C26 17 30 17 32 8",
};

/**
 * A single Mandarin tone contour (flat / rising / dip / falling / mixed) as a
 * small line-stroke icon — the same visual language as the app's ToneMark
 * brand mark, reused wherever a single tone shape needs to stand alone (tone
 * practice word picker, journey-path stops, etc.) instead of the full 4-tone
 * mark. Purely decorative, so it's hidden from assistive tech.
 */
export default function ToneShapeIcon({
  tone,
  size = 22,
  color,
}: {
  tone: ToneGroup;
  size?: number;
  /** Defaults to currentColor so callers can tint via CSS `color`. */
  color?: string;
}) {
  return (
    <svg
      className="tone-shape-icon"
      width={size}
      height={size}
      viewBox="0 0 32 28"
      fill="none"
      aria-hidden="true"
    >
      <path
        d={TONE_SHAPE_PATHS[tone]}
        stroke={color ?? "currentColor"}
        strokeWidth="3"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}
