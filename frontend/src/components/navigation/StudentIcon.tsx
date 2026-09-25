import Icon, { type UiIconName } from "@shared/ui/Icon";

export type StudentIconName = UiIconName;

export const ICON_SIZE = {
  xs: 14,
  sm: 16,
  md: 18,
  lg: 20,
  xl: 24,
} as const;

/** Compatibility adapter for legacy chrome callers; shared/ui/Icon owns rendering. */
export default function StudentIcon({ name, size = ICON_SIZE.md, strokeWidth = 1.75, ...props }: Parameters<typeof Icon>[0]) {
  return <Icon name={name} size={size} strokeWidth={strokeWidth} {...props} />;
}
