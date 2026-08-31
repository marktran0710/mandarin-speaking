import type { ImgHTMLAttributes, SVGProps } from "react";
import "./AppIcon.css";

/**
 * Semantic icon names shared by student and teacher surfaces.
 *
 * The visual implementation is a shared family of colorful, transparent PNG
 * assets. Keeping this semantic facade means existing pages can keep asking
 * for `record`, `check-circle`, and similar intent-based names without
 * drawing icons in individual components.
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

type IconAsset = {
  file: string;
  rotation?: number;
};

/** One coherent raster family for the whole product. Add semantic aliases here. */
const iconMap: Record<AppIconName, IconAsset> = {
  home: { file: "home.png" },
  book: { file: "book.png" },
  stories: { file: "stories.png" },
  image: { file: "image.png" },
  listen: { file: "listen.png" },
  headset: { file: "headset.png" },
  voice: { file: "voice.png" },
  microphone: { file: "microphone.png" },
  sun: { file: "sun.png" },
  moon: { file: "moon.png" },
  logout: { file: "logout.png" },
  user: { file: "user.png" },
  users: { file: "users.png" },
  lock: { file: "lock.png" },
  star: { file: "star.png" },
  chart: { file: "chart.png" },
  analytics: { file: "analytics.png" },
  eye: { file: "eye.png" },
  "eye-off": { file: "eye-off.png" },
  record: { file: "record.png" },
  stop: { file: "stop.png" },
  upload: { file: "upload.png" },
  download: { file: "download.png" },
  analyze: { file: "analyze.png" },
  play: { file: "play.png" },
  pause: { file: "pause.png" },
  volume: { file: "volume.png" },
  feedback: { file: "feedback.png" },
  message: { file: "message.png" },
  retry: { file: "retry.png" },
  refresh: { file: "refresh.png" },
  check: { file: "check.png" },
  "check-circle": { file: "check-circle.png" },
  "x-circle": { file: "x-circle.png" },
  warning: { file: "warning.png" },
  info: { file: "info.png" },
  spark: { file: "spark.png" },
  idea: { file: "idea.png" },
  celebrate: { file: "celebrate.png" },
  seedling: { file: "seedling.png" },
  sprout: { file: "sprout.png" },
  tree: { file: "tree.png" },
  menu: { file: "menu.png" },
  close: { file: "close.png" },
  plus: { file: "plus.png" },
  minus: { file: "minus.png" },
  "arrow-left": { file: "arrow-left.png" },
  "arrow-right": { file: "arrow-right.png" },
  "chevron-left": { file: "chevron-left.png" },
  "chevron-right": { file: "chevron-right.png" },
  "chevron-down": { file: "chevron-down.png" },
  "chevron-up": { file: "chevron-up.png" },
  "arrow-up": { file: "arrow-right.png", rotation: -90 },
  "arrow-down": { file: "arrow-right.png", rotation: 90 },
  external: { file: "external.png" },
  edit: { file: "edit.png" },
  trash: { file: "trash.png" },
  filter: { file: "filter.png" },
  search: { file: "search.png" },
  file: { file: "file.png" },
  library: { file: "stories.png" },
  inbox: { file: "inbox.png" },
  dashboard: { file: "dashboard.png" },
  debug: { file: "debug.png" },
  help: { file: "help.png" },
  settings: { file: "settings.png" },
  target: { file: "target.png" },
  shield: { file: "shield.png" },
  clock: { file: "clock.png" },
  send: { file: "send.png" },
  dots: { file: "dots.png" },
  quiz: { file: "quiz.png" },
  monitor: { file: "monitor.png" },
  "face-neutral": { file: "face-neutral.png" },
  "face-good": { file: "face-good.png" },
  "face-hard": { file: "face-hard.png" },
};

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
  const imageProps = { ...props } as Record<string, unknown>;

  for (const attribute of SVG_ONLY_ATTRIBUTES) {
    delete imageProps[attribute];
  }

  const authoredTransform = props.style?.transform;
  const transform = icon.rotation
    ? [authoredTransform, `rotate(${icon.rotation}deg)`].filter(Boolean).join(" ")
    : authoredTransform;
  const accessibleLabel = props["aria-label"];

  return (
    <img
      {...(imageProps as unknown as ImgHTMLAttributes<HTMLImageElement>)}
      className={`app-icon${props.className ? ` ${props.className}` : ""}`}
      src={`/assets/icons/clean/${icon.file}`}
      alt={accessibleLabel ?? ""}
      aria-hidden={accessibleLabel ? undefined : props["aria-hidden"] ?? true}
      width={size}
      height={size}
      draggable={false}
      data-icon={name}
      style={{
        ...props.style,
        width: size,
        height: size,
        transform,
      }}
    />
  );
}
