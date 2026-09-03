import type { SVGProps } from "react";
import AppIcon, { type AppIconName } from "./AppIcon";

export type StudentIconName = AppIconName;

interface StudentIconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: StudentIconName;
  size?: number;
  strokeWidth?: number;
}

/** Student-facing alias for the site's canonical icon family. */
export default function StudentIcon({ name, size = 18, strokeWidth = 1.75, ...props }: StudentIconProps) {
  return <AppIcon name={name} size={size} strokeWidth={strokeWidth} {...props} />;
}
