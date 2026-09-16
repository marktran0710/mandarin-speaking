import type { SVGProps } from "react";
import AppIcon, { type AppIconName } from "./AppIcon";

export type StudentIconName = AppIconName;

/** Canonical size scale for every `<StudentIcon>` in student mode. No such
 * scale existed before — every call site picked whatever number "looked
 * right", which had drifted to 15 distinct sizes (12-30px, plus a couple of
 * 56px hero icons) across the app with no visual rhythm to it. New code
 * should pick from this set rather than a bespoke literal; snap an existing
 * literal to the nearest tier when you touch that call site anyway. */
export const ICON_SIZE = {
  /** Inline with dense small text — status dots, compact chip icons. */
  xs: 14,
  /** The most common size: inline with body text, list rows, small buttons. */
  sm: 16,
  /** Default — nav items, standard buttons. Matches StudentIcon's own default. */
  md: 18,
  /** Section headers, card icons, emphasis. */
  lg: 20,
  /** Prominent standalone icons — empty states, feature callouts. */
  xl: 24,
} as const;

interface StudentIconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: StudentIconName;
  size?: number;
  strokeWidth?: number;
}

/** Student-facing alias for the site's canonical icon family. */
export default function StudentIcon({ name, size = ICON_SIZE.md, strokeWidth = 1.75, ...props }: StudentIconProps) {
  return <AppIcon name={name} size={size} strokeWidth={strokeWidth} {...props} />;
}
