/**
 * Material Symbols wrapper. Icons are either decorative (paired with visible
 * text — aria-hidden) or meaningful (no visible text alternative — needs a
 * label). Never render a bare icon inside an interactive control without one
 * or the other; that is the #1 accessibility anti-pattern for icon buttons.
 */
export type StudentIconRole = "decorative" | "meaningful";

interface StudentIconProps {
  name: string;
  size?: number;
  role?: StudentIconRole;
  label?: string;
  filled?: boolean;
  className?: string;
}

export default function StudentIcon({
  name,
  size = 18,
  role = "decorative",
  label,
  filled = false,
  className = "",
}: StudentIconProps) {
  if (role === "meaningful" && !label) {
    throw new Error(`StudentIcon "${name}": role="meaningful" requires a label`);
  }
  return (
    <span
      className={`sa-icon ${className}`.trim()}
      style={{
        fontSize: size,
        fontVariationSettings: filled ? "'FILL' 1" : undefined,
      }}
      aria-hidden={role === "decorative" ? true : undefined}
      role={role === "meaningful" ? "img" : undefined}
      aria-label={role === "meaningful" ? label : undefined}
    >
      {name}
    </span>
  );
}
