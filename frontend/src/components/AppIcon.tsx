import type { SVGProps } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  BarChart3,
  BookOpen,
  Bug,
  ChartLine,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleCheck,
  CircleHelp,
  CircleX,
  ClipboardList,
  Clock3,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  FileText,
  Frown,
  Headphones,
  Headset,
  House,
  Image,
  Inbox,
  Info,
  LayoutDashboard,
  Library,
  Lightbulb,
  LockKeyhole,
  LogOut,
  Meh,
  Menu,
  MessageCircle,
  MessageSquare,
  Mic,
  Minus,
  Monitor,
  Moon,
  MoreHorizontal,
  PartyPopper,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  SearchCheck,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Smile,
  Sparkles,
  Sprout,
  SquareStop,
  Star,
  Sun,
  Target,
  Trash2,
  TreePine,
  TriangleAlert,
  Upload,
  UserRound,
  UsersRound,
  Volume2,
  X,
  Send,
  type LucideIcon,
} from "lucide-react";

/**
 * Semantic icon names shared by student and teacher surfaces.
 *
 * The visual implementation comes from lucide-react, the icon library used
 * by the shadcn/ui ecosystem. Keeping this semantic facade means existing
 * pages can keep asking for `record`, `check-circle`, and similar intent-based
 * names without importing or drawing icons themselves.
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

/**
 * One library mapping for the whole product. Do not add hand-authored SVG
 * paths here; add a semantic name and map it to a lucide-react icon instead.
 */
const iconMap = {
  home: House,
  book: BookOpen,
  stories: Library,
  image: Image,
  listen: Headphones,
  headset: Headset,
  voice: Mic,
  microphone: Mic,
  sun: Sun,
  moon: Moon,
  logout: LogOut,
  user: UserRound,
  users: UsersRound,
  lock: LockKeyhole,
  star: Star,
  chart: BarChart3,
  analytics: ChartLine,
  eye: Eye,
  "eye-off": EyeOff,
  record: Mic,
  stop: SquareStop,
  upload: Upload,
  download: Download,
  analyze: SearchCheck,
  play: Play,
  pause: Pause,
  volume: Volume2,
  feedback: MessageSquare,
  message: MessageCircle,
  retry: RotateCcw,
  refresh: RefreshCw,
  check: Check,
  "check-circle": CircleCheck,
  "x-circle": CircleX,
  warning: TriangleAlert,
  info: Info,
  spark: Sparkles,
  idea: Lightbulb,
  celebrate: PartyPopper,
  seedling: Sprout,
  sprout: Sprout,
  tree: TreePine,
  menu: Menu,
  close: X,
  plus: Plus,
  minus: Minus,
  "arrow-left": ArrowLeft,
  "arrow-right": ArrowRight,
  "chevron-left": ChevronLeft,
  "chevron-right": ChevronRight,
  "chevron-down": ChevronDown,
  "chevron-up": ChevronUp,
  "arrow-up": ArrowUp,
  "arrow-down": ArrowDown,
  external: ExternalLink,
  edit: Pencil,
  trash: Trash2,
  filter: SlidersHorizontal,
  search: Search,
  file: FileText,
  library: Library,
  inbox: Inbox,
  dashboard: LayoutDashboard,
  debug: Bug,
  help: CircleHelp,
  settings: Settings2,
  target: Target,
  shield: ShieldCheck,
  clock: Clock3,
  send: Send,
  dots: MoreHorizontal,
  quiz: ClipboardList,
  monitor: Monitor,
  "face-neutral": Meh,
  "face-good": Smile,
  "face-hard": Frown,
} satisfies Record<AppIconName, LucideIcon>;

export default function AppIcon({ name, size = 18, strokeWidth = 1.5, fill = "none", ...props }: AppIconProps) {
  const Icon = iconMap[name] ?? CircleHelp;

  return (
    <Icon
      {...props}
      size={size}
      width={size}
      height={size}
      fill={fill}
      stroke="currentColor"
      strokeWidth={strokeWidth}
      aria-hidden={props["aria-label"] ? undefined : true}
      focusable="false"
    />
  );
}
