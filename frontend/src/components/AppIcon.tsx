import type { SVGProps } from "react";

/**
 * The single icon family used by every product surface.
 *
 * Icons are drawn on the same 24px grid with a quiet editorial line: one
 * stroke weight, rounded joins, and enough negative space to stay legible at
 * 16–32px. The component is intentionally code-native so color, state, and
 * accessibility remain controlled by the consuming UI instead of a raster or
 * hand-authored SVG file.
 */
export type AppIconName =
  | "home" | "book" | "stories" | "image" | "listen" | "headset" | "voice" | "microphone"
  | "sun" | "moon" | "logout" | "user" | "users" | "lock" | "star" | "chart" | "analytics" | "eye" | "eye-off"
  | "record" | "stop" | "upload" | "download" | "analyze" | "play" | "pause" | "volume"
  | "feedback" | "message" | "retry" | "refresh" | "check" | "check-circle" | "x-circle"
  | "warning" | "info" | "spark" | "idea" | "celebrate" | "seedling" | "sprout" | "tree"
  | "menu" | "close" | "plus" | "minus" | "arrow-left" | "arrow-right" | "chevron-left" | "chevron-right" | "chevron-down"
  | "chevron-up" | "arrow-up" | "arrow-down" | "external" | "edit" | "trash" | "filter" | "search" | "file" | "library"
  | "inbox" | "dashboard" | "debug" | "help" | "settings" | "target" | "shield" | "clock"
  | "send" | "dots" | "quiz" | "monitor" | "face-neutral" | "face-good" | "face-hard";

export interface AppIconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: AppIconName;
  size?: number;
  strokeWidth?: number;
}

type IconAccent = { path: number; fill: string };

const paths: Record<AppIconName, string[]> = {
  home: ["M3.5 10.5 12 3.8l8.5 6.7", "M5.5 9.5V20h13V9.5", "M9.5 20v-5.5h5V20"],
  book: ["M4.5 5.5A2.5 2.5 0 0 1 7 3h13v16H7a2.5 2.5 0 0 0-2.5 2.5z", "M4.5 5.5v16", "M8.5 7h7"],
  stories: ["M5 4.5h14v16H7.5A2.5 2.5 0 0 1 5 18z", "M5 4.5v13.5", "M8.5 8h7M8.5 11.5h5.5"],
  image: ["M4 4.5h16v15H4z", "M8.5 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z", "m4 16 4.5-4 3 2.5 2.5-2 6 4.5"],
  listen: ["M4 13v-2a8 8 0 0 1 16 0v2", "M4 13v3a2 2 0 0 0 2 2h1v-7H6a2 2 0 0 0-2 2ZM20 13v3a2 2 0 0 1-2 2h-1v-7h1a2 2 0 0 1 2 2Z", "M15 19c-.8 1.3-2 2-3.7 2H10"],
  headset: ["M4 13v-2a8 8 0 0 1 16 0v2", "M4 13v3a2 2 0 0 0 2 2h1v-7H6a2 2 0 0 0-2 2ZM20 13v3a2 2 0 0 1-2 2h-1v-7h1a2 2 0 0 1 2 2Z", "M12 21h2"],
  voice: ["M12 3a3.5 3.5 0 0 0-3.5 3.5v5a3.5 3.5 0 0 0 7 0v-5A3.5 3.5 0 0 0 12 3Z", "M5 11.5a7 7 0 0 0 14 0", "M12 18.5V21M8.5 21h7"],
  microphone: ["M12 3a3.5 3.5 0 0 0-3.5 3.5v5a3.5 3.5 0 0 0 7 0v-5A3.5 3.5 0 0 0 12 3Z", "M5 11.5a7 7 0 0 0 14 0", "M12 18.5V21M8.5 21h7"],
  sun: ["M12 2.5v2M12 19.5v2M4.7 4.7l1.4 1.4M17.9 17.9l1.4 1.4M2.5 12h2M19.5 12h2M4.7 19.3l1.4-1.4M17.9 6.1l1.4-1.4", "M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z"],
  moon: ["M20 15.2A8.4 8.4 0 0 1 8.8 4a8.8 8.8 0 1 0 11.2 11.2Z"],
  logout: ["M10 4H5v16h5", "M14 8l4 4-4 4", "M8 12h10"],
  user: ["M12 11.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z", "M5 20a7 7 0 0 1 14 0"],
  users: ["M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1", "M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z", "M17 3.5a4 4 0 0 1 0 7.5M21 20v-1a4 4 0 0 0-3-3.8"],
  eye: ["M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12Z", "M15.5 12a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0Z"],
  "eye-off": ["M3 3l18 18", "M10.6 5.7A9.3 9.3 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17.8 17.8 0 0 1-3.1 3.8", "M6.2 6.3C3.8 8 2.5 12 2.5 12S6 18.5 12 18.5c1.1 0 2.1-.2 3-.6", "M9.9 9.9a3 3 0 0 0 4.2 4.2"],
  lock: ["M6 10h12v10H6z", "M8.5 10V7a3.5 3.5 0 0 1 7 0v3", "M12 14v2"],
  star: ["m12 3.2 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.8l6.2-.9Z"],
  chart: ["M4 20V10M10 20V4M16 20v-7M22 20H2"],
  analytics: ["M4 19V5", "M4 19h16", "m4-5 4-3 3 2 5-6"],
  record: ["M12 3a3.5 3.5 0 0 0-3.5 3.5v5a3.5 3.5 0 0 0 7 0v-5A3.5 3.5 0 0 0 12 3Z", "M5 11.5a7 7 0 0 0 14 0", "M12 18.5V21"],
  stop: ["M7 7h10v10H7z"],
  upload: ["M12 16V4", "m8 8 4-4 4 4", "M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5"],
  download: ["M12 4v12", "m8 12 4 4 4-4", "M5 20h14"],
  analyze: ["M10.5 17a6.5 6.5 0 1 1 0-13 6.5 6.5 0 0 1 0 13Z", "m16 16 4.5 4.5", "M10.5 7v7M7 10.5h7"],
  play: ["m8 5 11 7-11 7Z"],
  pause: ["M9 5v14M15 5v14"],
  volume: ["M4 10v4h4l5 4V6l-5 4H4Z", "M17 9a4 4 0 0 1 0 6M19.5 6.5a7.5 7.5 0 0 1 0 11"],
  feedback: ["M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H11l-4.5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5Z", "M8 9h8M8 12h5"],
  message: ["M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H11l-4.5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5Z", "M8 8.5h8M8 12h5"],
  retry: ["M20 11a8 8 0 0 0-14.6-4L3 9", "M3 4v5h5", "M4 13a8 8 0 0 0 14.6 4L21 15", "M21 20v-5h-5"],
  refresh: ["M20 11a8 8 0 0 0-14.9-3", "M5 4v4h4", "M4 13a8 8 0 0 0 14.9 3", "M19 20v-4h-4"],
  check: ["m5 12 4 4L19 6"],
  "check-circle": ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "m8 12 2.7 2.7L16.5 9"],
  "x-circle": ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "m9 9 6 6M15 9l-6 6"],
  warning: ["m12 3 9 17H3L12 3Z", "M12 9v4M12 16h.01"],
  info: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 11v5M12 8h.01"],
  spark: ["m12 3 1.2 5.8L19 10l-5.8 1.2L12 17l-1.2-5.8L5 10l5.8-1.2Z", "m19 16 .5 2.5L22 19l-2.5.5L19 22l-.5-2.5L16 19l2.5-.5Z"],
  idea: ["M9 18h6", "M10 21h4", "M8.5 14.5a6 6 0 1 1 7 0c-.9.7-1.5 1.4-1.5 2.5h-4c0-1.1-.6-1.8-1.5-2.5Z", "M12 5v2"],
  celebrate: ["M5 19 9 9l6 6-10 4Z", "m9 9 2-4M15 15l4-2M7 6l-1-2M19 8l2-1"],
  seedling: ["M12 21V11", "M12 13c-4.5 0-7-2.3-7-6 4.6 0 7 2.1 7 6Z", "M12 11c0-3.8 2.4-6 7-6 0 3.7-2.5 6-7 6Z"],
  sprout: ["M12 21V8", "M12 12C7 12 4 9.4 4 5c5.2 0 8 2.5 8 7Z", "M12 9c0-4.1 2.7-6 8-6 0 4.5-2.8 6.5-8 6.5Z", "M8 21h8"],
  tree: ["M12 21V11", "M8 21h8", "M12 4c-1.8-2.4-5.5-1.1-5.1 1.8-3.5.3-4 5.1-.7 6.2-1.1 3.2 3.2 5.4 5.8 3.3 2.6 2.1 6.9-.1 5.8-3.3 3.3-1.1 2.8-5.9-.7-6.2C17.5 2.9 13.8 1.6 12 4Z"],
  menu: ["M4 7h16M4 12h16M4 17h16"],
  close: ["M6 6l12 12M18 6 6 18"],
  plus: ["M12 5v14M5 12h14"],
  minus: ["M5 12h14"],
  "arrow-left": ["M20 12H5", "m11 6-6 6 6 6"],
  "arrow-right": ["M4 12h15", "m13 6 6 6-6 6"],
  "chevron-left": ["m15 6-6 6 6 6"],
  "chevron-right": ["m9 6 6 6-6 6"],
  "chevron-down": ["m6 9 6 6 6-6"],
  "chevron-up": ["m6 15 6-6 6 6"],
  "arrow-up": ["M12 20V4", "m6 10 6-6 6 6"],
  "arrow-down": ["M12 4v16", "m6 14 6 6 6-6"],
  external: ["M14 5h5v5", "m19 5-8 8", "M18 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"],
  edit: ["M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3Z", "m13.5 7.5 3 3"],
  trash: ["M5 7h14", "M10 11v5M14 11v5", "m8 7 .7-3h6.6l.7 3", "M7 7l.7 13h8.6L17 7"],
  filter: ["M4 5h16l-6.2 7.2v5.3l-3.6 1.5v-6.8Z"],
  search: ["M10.5 17a6.5 6.5 0 1 1 0-13 6.5 6.5 0 0 1 0 13Z", "m16 16 4.5 4.5"],
  file: ["M6 3h8l4 4v14H6z", "M14 3v5h4", "M9 12h6M9 16h6"],
  library: ["M5 4h3v16H5z", "M10.5 4h3v16h-3z", "M16 4h3v16h-3z"],
  inbox: ["M4 5h16v14H4z", "M4 14h4l1.5 2h5L16 14h4"],
  dashboard: ["M4 4h6v6H4z", "M14 4h6v6h-6z", "M4 14h6v6H4z", "M14 14h6v6h-6z"],
  debug: ["M9 3h6M12 3v3", "M7 8h10M6 12h12M8 19h8", "M5 9 3 7M19 9l2-2"],
  help: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M9.3 9a2.8 2.8 0 1 1 5.4 1c0 1.8-2.7 2.5-2.7 4", "M12 17h.01"],
  settings: ["M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z", "m19.4 15 .1.1-1.7 3-2.5-1.1a8 8 0 0 1-2.2 1.3L13 21h-2l-.1-2.7a8 8 0 0 1-2.2-1.3L6.2 18l-1.7-3 .1-.1 2.2-1.5a8 8 0 0 1 0-2.6L4.6 9.3l1.7-3 2.5 1.1A8 8 0 0 1 10.9 6L11 3h2l.1 3a8 8 0 0 1 2.2 1.4l2.5-1.1 1.7 3-2.2 1.5a8 8 0 0 1 0 2.6Z"],
  target: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z", "M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"],
  shield: ["M12 3 19 6v5c0 4.6-2.8 8.2-7 10-4.2-1.8-7-5.4-7-10V6l7-3Z", "m9 12 2 2 4-4"],
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 7v5l3 2"],
  send: ["M3 11.5 21 4l-5.5 17-3.2-7.2L3 11.5Z", "m12.3 13.8 4.4-5.1"],
  dots: ["M5 12h.01M12 12h.01M19 12h.01"],
  quiz: ["M5 4h14v16H5z", "M8.5 8h7M8.5 12h5M8.5 16h3"],
  monitor: ["M4 5h16v11H4z", "M8 20h8M12 16v4"],
  "face-neutral": ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M8.5 10h.01M15.5 10h.01M8.5 15h7"],
  "face-good": ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M8.5 10h.01M15.5 10h.01", "M8 14c1 1.5 2.3 2.2 4 2.2s3-.7 4-2.2"],
  "face-hard": ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M8.5 10h.01M15.5 10h.01", "M8.5 16c1-.8 2.2-1.2 3.5-1.2s2.5.4 3.5 1.2"],
};

/**
 * Small color planes make the family feel illustrated without turning every
 * icon into a separate asset. The outline remains the consumer's current
 * color, while these accents stay semantic and consistent across the app.
 */
const accents: Partial<Record<AppIconName, IconAccent[]>> = {
  home: [{ path: 1, fill: "var(--tone1-soft)" }],
  book: [{ path: 0, fill: "var(--tone1-soft)" }],
  stories: [{ path: 0, fill: "var(--tone1-soft)" }],
  image: [{ path: 0, fill: "var(--tone1-soft)" }, { path: 2, fill: "var(--jade-soft)" }],
  listen: [{ path: 1, fill: "var(--tone1-soft)" }],
  headset: [{ path: 1, fill: "var(--tone1-soft)" }],
  voice: [{ path: 0, fill: "var(--clay-error-soft)" }],
  microphone: [{ path: 0, fill: "var(--clay-error-soft)" }],
  record: [{ path: 0, fill: "var(--clay-error-soft)" }],
  volume: [{ path: 0, fill: "var(--tone1-soft)" }],
  retry: [{ path: 0, fill: "var(--tone1)" }, { path: 2, fill: "var(--jade)" }],
  refresh: [{ path: 0, fill: "var(--tone1)" }, { path: 2, fill: "var(--jade)" }],
  check: [{ path: 0, fill: "var(--jade)" }],
  "check-circle": [{ path: 0, fill: "var(--jade-soft)" }],
  "x-circle": [{ path: 0, fill: "var(--clay-error-soft)" }],
  warning: [{ path: 0, fill: "var(--gold-soft)" }],
  info: [{ path: 0, fill: "var(--tone1-soft)" }],
  star: [{ path: 0, fill: "var(--gold)" }],
  lock: [{ path: 0, fill: "var(--gold-soft)" }],
  users: [{ path: 1, fill: "var(--tone1-soft)" }],
  user: [{ path: 0, fill: "var(--tone1-soft)" }],
  target: [{ path: 0, fill: "var(--tone1-soft)" }, { path: 2, fill: "var(--gold)" }],
  idea: [{ path: 2, fill: "var(--gold-soft)" }],
  celebrate: [{ path: 0, fill: "var(--gold-soft)" }],
  seedling: [{ path: 1, fill: "var(--jade-soft)" }, { path: 2, fill: "var(--jade-soft)" }],
  sprout: [{ path: 1, fill: "var(--jade-soft)" }, { path: 2, fill: "var(--jade-soft)" }],
  tree: [{ path: 2, fill: "var(--jade-soft)" }],
  play: [{ path: 0, fill: "var(--gold)" }],
  stop: [{ path: 0, fill: "var(--clay-error-soft)" }],
  pause: [{ path: 0, fill: "var(--gold-soft)" }],
  edit: [{ path: 0, fill: "var(--gold-soft)" }],
  trash: [{ path: 3, fill: "var(--clay-error-soft)" }],
  file: [{ path: 0, fill: "var(--tone1-soft)" }],
  library: [{ path: 0, fill: "var(--tone1-soft)" }, { path: 1, fill: "var(--jade-soft)" }, { path: 2, fill: "var(--gold-soft)" }],
  inbox: [{ path: 0, fill: "var(--tone1-soft)" }],
  dashboard: [{ path: 0, fill: "var(--tone1-soft)" }, { path: 1, fill: "var(--jade-soft)" }, { path: 2, fill: "var(--gold-soft)" }, { path: 3, fill: "var(--clay-error-soft)" }],
  quiz: [{ path: 0, fill: "var(--tone1-soft)" }],
  monitor: [{ path: 0, fill: "var(--tone1-soft)" }],
  settings: [{ path: 1, fill: "var(--jade-soft)" }],
  shield: [{ path: 0, fill: "var(--jade-soft)" }],
  clock: [{ path: 0, fill: "var(--gold-soft)" }],
  send: [{ path: 0, fill: "var(--tone1-soft)" }],
  "face-neutral": [{ path: 0, fill: "var(--gold-soft)" }],
  "face-good": [{ path: 0, fill: "var(--jade-soft)" }],
  "face-hard": [{ path: 0, fill: "var(--clay-error-soft)" }],
};

export default function AppIcon({ name, size = 18, strokeWidth = 1.75, fill = "none", ...props }: AppIconProps) {
  const iconPaths = paths[name] ?? paths.help;
  const iconAccents = accents[name] ?? [];
  return (
    <svg
      {...props}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={fill}
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={props["aria-label"] ? undefined : true}
      focusable="false"
    >
      {iconAccents.map(({ path, fill: accentFill }) => <path key={`accent-${path}`} d={iconPaths[path]} fill={accentFill} stroke={accentFill} strokeWidth={strokeWidth + 2} />)}
      {iconPaths.map((path) => <path key={path} d={path} />)}
    </svg>
  );
}
