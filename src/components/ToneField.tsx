import "./ToneField.css";

/**
 * Oversized ambient brush-stroke, built from the same dip-tone contour as
 * ToneShapeIcon/ToneMark (`M4 10 C10 24 22 24 28 6`) blown up to fill the
 * page — the login screen's signature is the app's own tone-mark geometry
 * at monumental scale, not a generic gradient blob. Purely decorative.
 */
export default function ToneField({ variant }: { variant: "student" | "teacher" }) {
  return (
    <svg
      className={`tone-field tone-field--${variant}`}
      viewBox="0 0 1000 500"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      <path className="tone-field-stroke tone-field-stroke--thick" d="M60 180 C280 480 680 480 940 80" />
      <path className="tone-field-stroke tone-field-stroke--thin" d="M60 230 C280 530 680 530 940 130" />
    </svg>
  );
}
