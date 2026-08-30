import type { SVGProps } from "react";
import AppIcon, { type AppIconName } from "../../components/AppIcon";

export type UiIconName = AppIconName;

/** Shared alias for management and product chrome. */
export default function Icon({ name, size = 18, strokeWidth = 1.75, ...props }: SVGProps<SVGSVGElement> & { name: UiIconName; size?: number; strokeWidth?: number }) {
  return <AppIcon name={name} size={size} strokeWidth={strokeWidth} {...props} />;
}
