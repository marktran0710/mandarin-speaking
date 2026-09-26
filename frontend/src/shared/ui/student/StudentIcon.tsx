/**
 * Local icon adapter. Icons are either decorative (paired with visible
 * text ??aria-hidden) or meaningful (no visible text alternative ??needs a
 * label). Never render a bare icon inside an interactive control without one
 * or the other; that is the #1 accessibility anti-pattern for icon buttons.
 */
import Icon, { type AppIconName } from "../Icon";

export type StudentIconRole = "decorative" | "meaningful";

interface StudentIconProps {
  name: string;
  size?: number;
  role?: StudentIconRole;
  label?: string;
  filled?: boolean;
  className?: string;
}

const ICON_ALIASES: Record<string, AppIconName> = {
  arrow_forward: "arrow-right", arrow_back: "arrow-left", arrow_upward: "arrow-up", arrow_downward: "arrow-down",
  menu_book: "book", trending_up: "chart", flag: "target", person: "user", person_outline: "user",
  check_circle: "check-circle", radio_button_unchecked: "clock", lock_open: "lock", play_arrow: "play",
  graphic_eq: "volume", replay: "retry", celebration: "celebrate", self_improvement: "idea", route: "target",
  hotel_class: "star", psychology: "idea", event_repeat: "refresh", schedule: "clock", stairs: "chart",
  fitness_center: "target", edit_note: "edit", expand_less: "chevron-up", expand_more: "chevron-down",
  change_history: "warning", school: "book", info: "info", error: "warning", warning: "warning",
  image: "image", mic: "microphone", send: "send", stop: "stop", lock: "lock", logout: "logout",
  star: "star", menu: "menu", close: "close",
};

function resolveIconName(name: string): AppIconName {
  return ICON_ALIASES[name] ?? (name as AppIconName);
}

export default function StudentIcon({
  name,
  size = 18,
  role = "decorative",
  label,
  filled: _filled = false,
  className = "",
}: StudentIconProps) {
  if (role === "meaningful" && !label) {
    throw new Error(`StudentIcon "${name}": role="meaningful" requires a label`);
  }
  return (
    <Icon
      name={resolveIconName(name)}
      size={size}
      className={`sa-icon ${className}`.trim()}
      aria-hidden={role === "decorative" ? true : undefined}
      role={role === "meaningful" ? "img" : undefined}
      aria-label={role === "meaningful" ? label : undefined}
    />
  );
}
