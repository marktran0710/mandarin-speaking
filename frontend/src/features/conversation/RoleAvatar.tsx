import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useStudentSettingsValue } from "@features/settings/StudentSettingsContext";

type RoleAvatarProps = {
  role: "character" | "student";
  compact?: boolean;
};

type MascotProps = {
  directions: string;
  reactions: string;
  size: number;
  label: string;
  className: string;
};

const DIRECTIONS = [
  "up-left",
  "up",
  "up-right",
  "left",
  "center",
  "right",
  "down-left",
  "down",
  "down-right",
] as const;

const REACTIONS = [
  "blink",
  "heart",
  "sparkle",
  "surprised",
  "wink",
  "bashful",
  "sleepy",
  "dizzy",
  "delighted",
] as const;

const CLOCKWISE = ["right", "down-right", "down", "down-left", "left", "up-left", "up", "up-right"] as const;
const SECTOR = (Math.PI * 2) / CLOCKWISE.length;
const DEAD_ZONE = 70;
const HYSTERESIS = 0.12;
const PAYOFFS = ["heart", "sparkle", "delighted"] as const;
const BOOP_PAYOFF = 120;
const BOOP_END = 560;
const DIZZY_AFTER = 4;
const DIZZY_WINDOW = 1600;
const DIZZY_END = 1100;

const mascotBase = `${import.meta.env.BASE_URL}mascots`;
const mascotAssets = {
  fox: {
    directions: `${mascotBase}/fox-directions.webp`,
    reactions: `${mascotBase}/fox-reactions.webp`,
  },
  male: {
    directions: `${mascotBase}/beard-directions.webp`,
    reactions: `${mascotBase}/beard-reactions.webp`,
  },
  female: {
    directions: `${mascotBase}/ballerina-directions.webp`,
    reactions: `${mascotBase}/ballerina-reactions.webp`,
  },
} as const;
const spriteLayer: CSSProperties = {
  position: "absolute",
  inset: 0,
  backgroundSize: "300% 300%",
  backgroundRepeat: "no-repeat",
};

function spritePosition(index: number): CSSProperties {
  return {
    backgroundPosition: `${(index % 3) * 50}% ${Math.floor(index / 3) * 50}%`,
  };
}

function wrap(angle: number) {
  return Math.atan2(Math.sin(angle), Math.cos(angle));
}

function hasMediaMatch(query: string) {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(query).matches;
}

function SpriteMascot({ directions, reactions, size, label, className }: MascotProps) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const squashRef = useRef<HTMLSpanElement>(null);
  const timersRef = useRef<number[]>([]);
  const boopsRef = useRef({ count: 0, at: 0 });
  const [direction, setDirection] = useState<(typeof DIRECTIONS)[number]>("center");
  const [reaction, setReaction] = useState<(typeof REACTIONS)[number] | null>(null);

  useEffect(() => {
    if (!hasMediaMatch("(hover: hover) and (pointer: fine)")) return;

    let sector = -1;
    let pointer: { x: number; y: number } | null = null;
    const aim = () => {
      const button = buttonRef.current;
      if (!button || !pointer) return;
      const box = button.getBoundingClientRect();
      const dx = pointer.x - (box.left + box.width / 2);
      const dy = pointer.y - (box.top + box.height / 2);
      if (Math.hypot(dx, dy) < DEAD_ZONE) {
        sector = -1;
        setDirection("center");
        return;
      }

      const angle = Math.atan2(dy, dx);
      if (sector !== -1 && Math.abs(wrap(angle - sector * SECTOR)) < SECTOR / 2 + HYSTERESIS) return;
      sector = (Math.round(angle / SECTOR) + CLOCKWISE.length) % CLOCKWISE.length;
      setDirection(CLOCKWISE[sector]);
    };
    const onPointerMove = (event: PointerEvent) => {
      pointer = { x: event.clientX, y: event.clientY };
      aim();
    };

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("scroll", aim, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("scroll", aim);
    };
  }, []);

  useEffect(() => () => timersRef.current.forEach(window.clearTimeout), []);

  const boop = () => {
    timersRef.current.forEach(window.clearTimeout);
    timersRef.current = [];
    const later = (delay: number, next: (typeof REACTIONS)[number] | null) => {
      timersRef.current.push(window.setTimeout(() => setReaction(next), delay));
    };
    const now = Date.now();
    const boops = boopsRef.current;
    boops.count = now - boops.at < DIZZY_WINDOW ? boops.count + 1 : 1;
    boops.at = now;

    if (boops.count >= DIZZY_AFTER) {
      boops.count = 0;
      setReaction("dizzy");
      later(DIZZY_END, null);
    } else {
      setReaction("blink");
      later(BOOP_PAYOFF, PAYOFFS[(boops.count - 1) % PAYOFFS.length]);
      later(BOOP_END, null);
    }

    if (!hasMediaMatch("(prefers-reduced-motion: reduce)")) {
      squashRef.current?.animate?.(
        [
          { transform: "scale(1, 1)", easing: "ease-in" },
          { transform: "scale(1.10, 0.86)", offset: 0.18, easing: "ease-out" },
          { transform: "scale(0.95, 1.08)", offset: 0.45, easing: "ease-in-out" },
          { transform: "scale(1.03, 0.97)", offset: 0.72, easing: "ease-in-out" },
          { transform: "scale(1, 1)" },
        ],
        { duration: 420, easing: "linear" },
      );
    }
  };

  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={boop}
      aria-label={`Boop the ${label}`}
      className={className}
      style={{
        position: "relative",
        display: "block",
        flexShrink: 0,
        width: size,
        height: size,
        padding: 0,
        border: 0,
        background: "transparent",
        appearance: "none",
        cursor: "pointer",
        userSelect: "none",
      }}
    >
      <span ref={squashRef} style={{ position: "relative", display: "block", width: "100%", height: "100%", transformOrigin: "50% 78%" }}>
        <span
          aria-hidden="true"
          style={{
            ...spriteLayer,
            backgroundImage: `url(${directions})`,
            ...spritePosition(DIRECTIONS.indexOf(direction)),
            opacity: reaction ? 0 : 1,
          }}
        />
        <span
          aria-hidden="true"
          style={{
            ...spriteLayer,
            backgroundImage: `url(${reactions})`,
            ...spritePosition(REACTIONS.indexOf(reaction ?? "blink")),
            opacity: reaction ? 1 : 0,
          }}
        />
      </span>
    </button>
  );
}

export default function RoleAvatar({ role, compact = false }: RoleAvatarProps) {
  const settings = useStudentSettingsValue();
  const assets = role === "character"
    ? mascotAssets[settings.partnerMascot]
    : mascotAssets[settings.studentMascot];
  return (
    <SpriteMascot
      directions={assets.directions}
      reactions={assets.reactions}
      size={compact ? 48 : 68}
      label={role === "character" ? "conversation character mascot" : "your conversation avatar"}
      className="sa-conversation__mascot"
    />
  );
}
