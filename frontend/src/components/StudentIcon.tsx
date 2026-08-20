import type { SVGProps } from "react";

export type StudentIconName =
  | "home"
  | "stories"
  | "image"
  | "listen"
  | "voice"
  | "sun"
  | "moon"
  | "logout"
  | "user"
  | "lock"
  | "star"
  | "chart"
  | "record"
  | "stop"
  | "upload"
  | "analyze"
  | "play"
  | "feedback"
  | "retry"
  | "check"
  | "spark"
  | "seedling"
  | "sprout"
  | "tree";

interface StudentIconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: StudentIconName;
  size?: number;
}

/**
 * Small outline icon family for student-facing chrome.
 *
 * The icons deliberately share one 24px grid, 1.8px stroke, and round joins
 * so navigation, metric cards, and recording actions read as one product.
 */
export default function StudentIcon({ name, size = 18, ...props }: StudentIconProps) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
    ...props,
  };

  switch (name) {
    case "home":
      return <svg {...common}><path d="m3 10 9-7 9 7" /><path d="M5 9.5V21h14V9.5" /><path d="M9.5 21v-6h5v6" /></svg>;
    case "stories":
      return <svg {...common}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z" /><path d="M4 5.5v16" /><path d="M8 7h8M8 10h6" /></svg>;
    case "image":
      return <svg {...common}><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9" r="1.4" /><path d="m5 17 4.5-4 3 2.5 2.5-2 4 3.5" /></svg>;
    case "listen":
      return <svg {...common}><path d="M4 13v-2a8 8 0 0 1 16 0v2" /><path d="M4 13v3a2 2 0 0 0 2 2h1v-7H6a2 2 0 0 0-2 2ZM20 13v3a2 2 0 0 1-2 2h-1v-7h1a2 2 0 0 1 2 2Z" /><path d="M15 19c-.8 1.3-2 2-3.7 2H10" /></svg>;
    case "voice":
      return <svg {...common}><rect x="8" y="3" width="8" height="12" rx="4" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" /></svg>;
    case "sun":
      return <svg {...common}><circle cx="12" cy="12" r="3.5" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>;
    case "moon":
      return <svg {...common}><path d="M20 15.2A8.4 8.4 0 0 1 8.8 4a8.8 8.8 0 1 0 11.2 11.2Z" /></svg>;
    case "logout":
      return <svg {...common}><path d="M10 4H5v16h5M14 8l4 4-4 4M8 12h10" /></svg>;
    case "user":
      return <svg {...common}><circle cx="12" cy="8" r="3.5" /><path d="M5 20a7 7 0 0 1 14 0" /></svg>;
    case "lock":
      return <svg {...common}><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>;
    case "star":
      return <svg {...common}><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z" /></svg>;
    case "chart":
      return <svg {...common}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></svg>;
    case "record":
      return <svg {...common}><rect x="8" y="3" width="8" height="12" rx="4" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>;
    case "stop":
      return <svg {...common}><rect x="6" y="6" width="12" height="12" rx="2" /></svg>;
    case "upload":
      return <svg {...common}><path d="M12 16V4M8 8l4-4 4 4" /><path d="M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" /></svg>;
    case "analyze":
      return <svg {...common}><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5M10.5 7v7M7 10.5h7" /></svg>;
    case "play":
      return <svg {...common}><path d="m8 5 11 7-11 7Z" /></svg>;
    case "feedback":
      return <svg {...common}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H11l-4.5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5Z" /><path d="M8 9h8M8 12h5" /></svg>;
    case "retry":
      return <svg {...common}><path d="M20 11a8 8 0 0 0-14.6-4L3 9" /><path d="M3 4v5h5M4 13a8 8 0 0 0 14.6 4L21 15" /><path d="M21 20v-5h-5" /></svg>;
    case "check":
      return <svg {...common}><path d="m5 12 4 4L19 6" /></svg>;
    case "spark":
      return <svg {...common}><path d="m12 3 1.2 5.8L19 10l-5.8 1.2L12 17l-1.2-5.8L5 10l5.8-1.2Z" /><path d="m19 16 .5 2.5L22 19l-2.5.5L19 22l-.5-2.5L16 19l2.5-.5Z" /></svg>;
    case "seedling":
      return <svg {...common}><path d="M12 21V11" /><path d="M12 13c-4.5 0-7-2.3-7-6 4.6 0 7 2.1 7 6Z" /><path d="M12 11c0-3.8 2.4-6 7-6 0 3.7-2.5 6-7 6Z" /></svg>;
    case "sprout":
      return <svg {...common}><path d="M12 21V8" /><path d="M12 12C7 12 4 9.4 4 5c5.2 0 8 2.5 8 7Z" /><path d="M12 9c0-4.1 2.7-6 8-6 0 4.5-2.8 6.5-8 6.5Z" /><path d="M8 21h8" /></svg>;
    case "tree":
      return <svg {...common}><path d="M12 21V11" /><path d="M8 21h8" /><path d="M12 4c-1.8-2.4-5.5-1.1-5.1 1.8-3.5.3-4 5.1-.7 6.2-1.1 3.2 3.2 5.4 5.8 3.3 2.6 2.1 6.9-.1 5.8-3.3 3.3-1.1 2.8-5.9-.7-6.2C17.5 2.9 13.8 1.6 12 4Z" /></svg>;
  }
}
