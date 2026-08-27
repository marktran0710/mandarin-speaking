import type { SVGProps } from "react";

export type UiIconName =
  | "analytics" | "arrow-right" | "book" | "close" | "dashboard" | "debug" | "help"
  | "inbox" | "library" | "menu" | "microphone" | "moon" | "refresh" | "sun" | "users";

const paths: Record<UiIconName, string[]> = {
  analytics: ["M4 19V5", "M4 19h16", "m4-5 4-3 3 2 5-6"],
  "arrow-right": ["M5 12h14", "m13 6 6 6-6 6"],
  book: ["M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z", "M4 5.5v16", "M8 7h8"],
  close: ["m6 6 12 12", "m18 6-12 12"],
  dashboard: ["M4 4h6v6H4z", "M14 4h6v6h-6z", "M4 14h6v6H4z", "M14 14h6v6h-6z"],
  debug: ["M9 3h6", "M12 3v3", "M7 8h10", "M6 12h12", "M8 19h8", "M5 9 3 7", "M19 9l2-2"],
  help: ["M12 18h.01", "M9.1 9a3 3 0 1 1 5.8 1c0 2-2.9 2-2.9 4", "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z"],
  inbox: ["M4 5h16v14H4z", "M4 14h4l1.5 2h5L16 14h4"],
  library: ["M5 4h3v16H5z", "M10.5 4h3v16h-3z", "M16 4h3v16h-3z"],
  menu: ["M4 7h16", "M4 12h16", "M4 17h16"],
  microphone: ["M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z", "M6 11a6 6 0 0 0 12 0", "M12 17v4", "M9 21h6"],
  moon: ["M20 15.5A8 8 0 0 1 8.5 4 8 8 0 1 0 20 15.5z"],
  refresh: ["M20 11a8 8 0 0 0-14.9-3", "M5 4v4h4", "M4 13a8 8 0 0 0 14.9 3", "M19 20v-4h-4"],
  sun: ["M12 4V2", "M12 22v-2", "m4.93 4.93-1.42-1.42", "m20.49 20.49-1.42-1.42", "M4 12H2", "M22 12h-2", "m4.93 19.07-1.42 1.42", "m20.49 3.51-1.42 1.42", "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10z"],
  users: ["M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1", "M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z", "M17 3.2a4 4 0 0 1 0 7.6", "M21 20v-1a4 4 0 0 0-3-3.87"],
};

export default function Icon({ name, size = 18, strokeWidth = 1.8, ...props }: SVGProps<SVGSVGElement> & { name: UiIconName; size?: number; strokeWidth?: number }) {
  const iconPaths = paths[name] ?? paths.dashboard;
  return (
    <svg {...props} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {iconPaths.map((path) => <path key={path} d={path} />)}
    </svg>
  );
}
