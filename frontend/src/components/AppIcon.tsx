import type { HTMLAttributes, SVGProps } from "react";
import "./AppIcon.css";

/**
 * Semantic icon names shared by student and teacher surfaces.
 *
 * The visual implementation is a small, colorful PNG atlas. Keeping this
 * semantic facade means existing pages can keep asking for `record`,
 * `check-circle`, and similar intent-based names without drawing icons in
 * individual components.
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

/**
 * Kept source-compatible with the previous SVG facade so StudentIcon and
 * shared/ui/Icon do not need page-by-page changes. SVG-only presentation
 * props are accepted for compatibility and ignored by the raster renderer.
 */
export interface AppIconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: AppIconName;
  size?: number;
  strokeWidth?: number;
}

type AtlasName = "primary" | "utility" | "eye";

type AtlasCell = {
  atlas: AtlasName;
  row: number;
  column: number;
  columns: number;
  rows: number;
  rotation?: number;
};

const ATLAS_URLS = {
  primary: "/assets/icons/mandarin-icon-atlas.png",
  utility: "/assets/icons/mandarin-utility-atlas.png",
  eye: "/assets/icons/mandarin-eye-atlas.png",
} as const;

const primary = (row: number, column: number): AtlasCell => ({
  atlas: "primary",
  row,
  column,
  columns: 6,
  rows: 6,
});

const utility = (row: number, column: number): AtlasCell => ({
  atlas: "utility",
  row,
  column,
  columns: 6,
  rows: 6,
});

const eye = (column: number): AtlasCell => ({
  atlas: "eye",
  row: 0,
  column,
  columns: 2,
  rows: 1,
});

/** One coherent raster family for the whole product. Add semantic aliases here. */
const iconMap = {
  home: primary(0, 0),
  book: primary(0, 1),
  stories: primary(0, 2),
  image: primary(0, 3),
  listen: primary(0, 4),
  headset: primary(0, 4),
  voice: primary(0, 5),
  microphone: primary(0, 5),
  sun: utility(0, 0),
  moon: utility(0, 1),
  logout: utility(0, 2),
  user: primary(1, 0),
  users: primary(1, 1),
  lock: primary(2, 5),
  star: primary(1, 4),
  chart: primary(1, 2),
  analytics: primary(1, 3),
  eye: eye(0),
  "eye-off": eye(1),
  record: primary(0, 5),
  stop: utility(5, 3),
  upload: primary(3, 3),
  download: primary(3, 4),
  analyze: primary(3, 5),
  play: primary(3, 0),
  pause: primary(3, 1),
  volume: primary(3, 2),
  feedback: primary(5, 3),
  message: primary(5, 3),
  retry: primary(5, 0),
  refresh: primary(5, 1),
  check: utility(5, 2),
  "check-circle": primary(2, 0),
  "x-circle": primary(2, 1),
  warning: primary(2, 2),
  info: primary(2, 3),
  spark: primary(1, 4),
  idea: primary(5, 4),
  celebrate: primary(5, 5),
  seedling: utility(4, 0),
  sprout: utility(4, 1),
  tree: utility(4, 2),
  menu: utility(0, 3),
  close: utility(0, 4),
  plus: utility(0, 5),
  minus: utility(1, 0),
  "arrow-left": primary(4, 0),
  "arrow-right": primary(4, 1),
  "chevron-left": primary(4, 2),
  "chevron-right": primary(4, 3),
  "chevron-down": primary(4, 4),
  "chevron-up": primary(4, 5),
  "arrow-up": { ...primary(4, 1), rotation: -90 },
  "arrow-down": { ...primary(4, 1), rotation: 90 },
  external: utility(3, 3),
  edit: utility(1, 1),
  trash: utility(1, 2),
  filter: utility(1, 3),
  search: utility(5, 5),
  file: utility(1, 4),
  library: primary(0, 2),
  inbox: utility(1, 5),
  dashboard: utility(2, 0),
  debug: utility(2, 1),
  help: primary(2, 4),
  settings: utility(5, 4),
  target: primary(1, 5),
  shield: utility(3, 4),
  clock: utility(3, 5),
  send: utility(2, 2),
  dots: utility(2, 3),
  quiz: utility(2, 4),
  monitor: utility(2, 5),
  "face-neutral": utility(3, 0),
  "face-good": utility(3, 1),
  "face-hard": utility(3, 2),
} satisfies Record<AppIconName, AtlasCell>;

const SVG_ONLY_ATTRIBUTES = [
  "fill",
  "stroke",
  "strokeWidth",
  "strokeLinecap",
  "strokeLinejoin",
  "viewBox",
  "xmlns",
  "focusable",
  "vectorEffect",
  "preserveAspectRatio",
  "shapeRendering",
  "version",
  "xmlSpace",
] as const;

export default function AppIcon({ name, size = 18, strokeWidth: _strokeWidth = 1.5, fill: _fill = "none", ...props }: AppIconProps) {
  const icon = iconMap[name] ?? iconMap.help;
  const spanProps = { ...props } as Record<string, unknown>;

  for (const attribute of SVG_ONLY_ATTRIBUTES) {
    delete spanProps[attribute];
  }

  const authoredTransform = props.style?.transform;
  const transform = icon.rotation
    ? [authoredTransform, `rotate(${icon.rotation}deg)`].filter(Boolean).join(" ")
    : authoredTransform;
  const positionX = icon.columns === 1 ? 0 : (icon.column / (icon.columns - 1)) * 100;
  const positionY = icon.rows === 1 ? 0 : (icon.row / (icon.rows - 1)) * 100;

  return (
    <span
      {...(spanProps as unknown as HTMLAttributes<HTMLSpanElement>)}
      className={`app-icon${props.className ? ` ${props.className}` : ""}`}
      role={props["aria-label"] ? "img" : undefined}
      aria-hidden={props["aria-label"] ? undefined : true}
      data-icon={name}
      data-icon-atlas={icon.atlas}
      style={{
        ...props.style,
        width: size,
        height: size,
        backgroundImage: `url("${ATLAS_URLS[icon.atlas]}")`,
        backgroundPosition: `${positionX}% ${positionY}%`,
        backgroundSize: `${icon.columns * 100}% ${icon.rows * 100}%`,
        backgroundRepeat: "no-repeat",
        transform,
      }}
    />
  );
}
