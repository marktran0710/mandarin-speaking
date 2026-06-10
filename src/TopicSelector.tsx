import { useState } from "react";
import { loadPublishedTeacherTopics } from "./utils/teacherStories";
import "./TopicSelector.css";

export interface Topic {
  id: string;
  name: string;
  description: string;
  skillFocus: string;
  level: string;
  images: string[];
  vocabulary: Record<number, string[]>;
}

interface TopicSelectorProps {
  onTopicSelect?: (topic: Topic) => void;
}

type SceneIcon =
  | "lantern"
  | "mountainTrain"
  | "temple"
  | "schoolFair"
  | "nightMarket"
  | "dragonBoat";

interface StoryScene {
  title: string;
  subtitle: string;
  moment: string;
  sky: string;
  ground: string;
  accent: string;
  icon: SceneIcon;
}

function escapeSvgText(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function sceneIllustration(icon: SceneIcon, accent: string): string {
  const commonShadow = 'filter="url(#softShadow)"';
  const illustrations: Record<SceneIcon, string> = {
    lantern: `
      <path d="M74 92 C132 48 264 48 326 92" fill="none" stroke="${accent}" stroke-width="10" stroke-linecap="round" opacity="0.45"/>
      <g ${commonShadow}>
        <rect x="84" y="104" width="58" height="76" rx="22" fill="#ffcf56"/>
        <rect x="171" y="82" width="70" height="94" rx="26" fill="#ef6f6c"/>
        <rect x="270" y="112" width="52" height="68" rx="20" fill="#69c0b8"/>
      </g>
      <path d="M113 180 V202 M206 176 V202 M296 180 V202" stroke="#8a4f2f" stroke-width="5" stroke-linecap="round"/>
      <path d="M83 224 C120 204 172 210 202 226 C242 205 302 203 342 222" fill="none" stroke="#5b8c76" stroke-width="11" stroke-linecap="round"/>
      <circle cx="96" cy="230" r="17" fill="#f4b18b"/>
      <circle cx="152" cy="222" r="17" fill="#f7c59f"/>
      <circle cx="255" cy="226" r="17" fill="#d99c77"/>
      <circle cx="310" cy="220" r="17" fill="#f4b18b"/>
    `,
    mountainTrain: `
      <circle cx="318" cy="66" r="30" fill="#ffd166" opacity="0.95"/>
      <path d="M42 202 L126 104 L190 202 Z" fill="#6aa67f" ${commonShadow}/>
      <path d="M112 202 L226 72 L348 202 Z" fill="#4f8d78" ${commonShadow}/>
      <path d="M184 118 L226 72 L270 120 C238 108 215 109 184 118 Z" fill="#f7fafc"/>
      <path d="M54 226 C132 175 228 255 346 174" fill="none" stroke="#6f4e37" stroke-width="12" stroke-linecap="round"/>
      <rect x="124" y="178" width="122" height="42" rx="12" fill="${accent}" ${commonShadow}/>
      <rect x="142" y="188" width="22" height="16" rx="4" fill="#eff6ff"/>
      <rect x="174" y="188" width="22" height="16" rx="4" fill="#eff6ff"/>
      <rect x="206" y="188" width="22" height="16" rx="4" fill="#eff6ff"/>
      <circle cx="154" cy="224" r="8" fill="#1f2937"/>
      <circle cx="216" cy="224" r="8" fill="#1f2937"/>
    `,
    temple: `
      <path d="M72 112 C122 78 274 78 328 112" fill="none" stroke="${accent}" stroke-width="15" stroke-linecap="round"/>
      <path d="M96 128 H304 V216 H96 Z" fill="#fff4d6" ${commonShadow}/>
      <path d="M76 132 L200 72 L324 132" fill="none" stroke="#d9483b" stroke-width="18" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="126" y="150" width="48" height="66" rx="8" fill="#d9483b"/>
      <rect x="226" y="150" width="48" height="66" rx="8" fill="#d9483b"/>
      <circle cx="200" cy="156" r="24" fill="#ffd166"/>
      <path d="M185 184 C196 174 208 174 218 184 V216 H185 Z" fill="#7a3f2d"/>
      <path d="M66 232 C116 214 154 224 200 236 C248 216 292 214 340 232" fill="none" stroke="#4f9f72" stroke-width="11" stroke-linecap="round"/>
    `,
    schoolFair: `
      <rect x="72" y="74" width="256" height="142" rx="18" fill="#ffffff" ${commonShadow}/>
      <rect x="96" y="98" width="208" height="62" rx="10" fill="#29756f"/>
      <path d="M122 126 H178 M202 126 H280 M122 144 H238" stroke="#e8fff8" stroke-width="6" stroke-linecap="round"/>
      <path d="M88 216 H312 L286 252 H114 Z" fill="#f7c86b"/>
      <rect x="126" y="194" width="148" height="32" rx="9" fill="${accent}" ${commonShadow}/>
      <circle cx="126" cy="244" r="18" fill="#f4b18b"/>
      <circle cx="198" cy="244" r="18" fill="#f7c59f"/>
      <circle cx="272" cy="244" r="18" fill="#d99c77"/>
    `,
    nightMarket: `
      <path d="M56 112 H344 L318 176 H82 Z" fill="${accent}" ${commonShadow}/>
      <path d="M78 112 L98 74 H302 L322 112" fill="#fff0bf" stroke="#d9803f" stroke-width="6"/>
      <rect x="92" y="176" width="216" height="58" rx="12" fill="#ffe3a3" ${commonShadow}/>
      <path d="M112 198 H178 M206 198 H282 M122 218 H266" stroke="#9a5a25" stroke-width="6" stroke-linecap="round"/>
      <circle cx="92" cy="78" r="14" fill="#ffcf56"/>
      <circle cx="148" cy="64" r="14" fill="#ef6f6c"/>
      <circle cx="250" cy="64" r="14" fill="#69c0b8"/>
      <circle cx="308" cy="78" r="14" fill="#ffcf56"/>
      <path d="M62 250 C112 228 160 236 204 250 C252 230 302 230 344 250" fill="none" stroke="#6b8f71" stroke-width="10" stroke-linecap="round"/>
    `,
    dragonBoat: `
      <path d="M44 198 C110 226 266 226 356 198 C338 242 90 246 44 198 Z" fill="${accent}" ${commonShadow}/>
      <path d="M318 174 C344 166 358 178 356 198 C342 188 330 184 318 174 Z" fill="#ef6f6c"/>
      <circle cx="337" cy="184" r="5" fill="#1f2937"/>
      <path d="M88 174 L120 142 M146 174 L178 142 M204 174 L236 142 M262 174 L294 142" stroke="#7a3f2d" stroke-width="8" stroke-linecap="round"/>
      <circle cx="104" cy="162" r="17" fill="#f4b18b"/>
      <circle cx="164" cy="162" r="17" fill="#f7c59f"/>
      <circle cx="224" cy="162" r="17" fill="#d99c77"/>
      <circle cx="284" cy="162" r="17" fill="#f4b18b"/>
      <path d="M48 238 C94 224 138 250 184 236 C232 222 280 250 350 232" fill="none" stroke="#4aa3c7" stroke-width="13" stroke-linecap="round"/>
    `,
  };

  return illustrations[icon];
}

function sceneBackdrop(icon: SceneIcon, accent: string): string {
  const backdrops: Record<SceneIcon, string> = {
    lantern: `
      <path d="M34 158 H366" stroke="#8a5a3d" stroke-width="5" stroke-linecap="round" opacity="0.2"/>
      <path d="M54 156 V88 M346 156 V88" stroke="#6f4e37" stroke-width="8" stroke-linecap="round" opacity="0.55"/>
      <path d="M54 88 C130 62 270 62 346 88" fill="none" stroke="${accent}" stroke-width="6" stroke-linecap="round" opacity="0.55"/>
      <circle cx="88" cy="96" r="13" fill="#ffcf56" opacity="0.78"/>
      <circle cx="142" cy="76" r="13" fill="#ef6f6c" opacity="0.72"/>
      <circle cx="204" cy="70" r="13" fill="#69c0b8" opacity="0.72"/>
      <circle cx="262" cy="76" r="13" fill="#ffcf56" opacity="0.72"/>
      <circle cx="318" cy="96" r="13" fill="#ef6f6c" opacity="0.72"/>
      <path d="M30 214 C92 190 146 197 198 216 C252 194 310 190 374 212" fill="none" stroke="#726653" stroke-width="10" stroke-linecap="round" opacity="0.18"/>
    `,
    mountainTrain: `
      <circle cx="324" cy="62" r="34" fill="#ffd166" opacity="0.46"/>
      <path d="M-8 202 L90 96 L168 202 Z" fill="#7fb18b" opacity="0.62"/>
      <path d="M80 204 L214 58 L366 204 Z" fill="#5f957d" opacity="0.72"/>
      <path d="M184 90 L214 58 L248 92 C226 84 206 84 184 90 Z" fill="#fffaf0" opacity="0.8"/>
      <path d="M28 210 C106 158 226 250 372 166" fill="none" stroke="#7a553b" stroke-width="10" stroke-linecap="round" opacity="0.42"/>
      <path d="M42 122 C92 110 134 126 186 112 C238 98 288 116 348 100" fill="none" stroke="#f8fafc" stroke-width="9" stroke-linecap="round" opacity="0.42"/>
    `,
    temple: `
      <path d="M44 150 H356 V220 H44 Z" fill="#f8dfb3" opacity="0.46"/>
      <path d="M58 150 L200 80 L342 150" fill="none" stroke="${accent}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round" opacity="0.55"/>
      <rect x="76" y="154" width="248" height="66" rx="10" fill="#fff4d6" opacity="0.55"/>
      <path d="M100 178 H150 M250 178 H300" stroke="#b84c3f" stroke-width="9" stroke-linecap="round" opacity="0.42"/>
      <path d="M44 234 C96 214 152 220 202 238 C260 212 310 214 356 234" fill="none" stroke="#5c946e" stroke-width="10" stroke-linecap="round" opacity="0.25"/>
      <circle cx="74" cy="112" r="8" fill="#ffcf56" opacity="0.7"/>
      <circle cx="326" cy="112" r="8" fill="#ffcf56" opacity="0.7"/>
    `,
    schoolFair: `
      <rect x="46" y="74" width="308" height="150" rx="16" fill="#fffaf0" opacity="0.72"/>
      <rect x="70" y="96" width="260" height="60" rx="10" fill="#2f6f68" opacity="0.72"/>
      <path d="M98 122 H170 M194 122 H294 M98 140 H244" stroke="#e8fff8" stroke-width="5" stroke-linecap="round" opacity="0.78"/>
      <path d="M66 222 H334 L306 250 H94 Z" fill="#f0c96c" opacity="0.62"/>
      <rect x="84" y="168" width="62" height="42" rx="8" fill="#ffefd2" stroke="${accent}" stroke-width="4" opacity="0.7"/>
      <rect x="254" y="168" width="62" height="42" rx="8" fill="#ffefd2" stroke="${accent}" stroke-width="4" opacity="0.7"/>
    `,
    nightMarket: `
      <rect x="48" y="94" width="304" height="122" rx="14" fill="#3f355d" opacity="0.48"/>
      <path d="M64 116 H336 L314 170 H86 Z" fill="${accent}" opacity="0.64"/>
      <path d="M86 116 L106 82 H294 L314 116" fill="#fff0bf" stroke="#d9803f" stroke-width="5" opacity="0.78"/>
      <circle cx="82" cy="78" r="11" fill="#ffcf56" opacity="0.82"/>
      <circle cx="136" cy="66" r="11" fill="#ef6f6c" opacity="0.8"/>
      <circle cx="200" cy="60" r="11" fill="#69c0b8" opacity="0.8"/>
      <circle cx="264" cy="66" r="11" fill="#ffcf56" opacity="0.8"/>
      <circle cx="318" cy="78" r="11" fill="#ef6f6c" opacity="0.8"/>
      <path d="M58 238 C112 216 162 230 210 242 C264 218 314 218 356 238" fill="none" stroke="#6b8f71" stroke-width="10" stroke-linecap="round" opacity="0.24"/>
    `,
    dragonBoat: `
      <path d="M-20 188 C70 168 138 208 222 186 C300 166 350 178 420 154 V320 H-20 Z" fill="#80c7d8" opacity="0.62"/>
      <path d="M36 226 C92 206 142 238 202 218 C260 198 304 226 366 206" fill="none" stroke="#f8fafc" stroke-width="9" stroke-linecap="round" opacity="0.72"/>
      <path d="M44 118 C108 90 172 108 214 124 C256 96 314 98 362 118" fill="none" stroke="#6da277" stroke-width="10" stroke-linecap="round" opacity="0.32"/>
      <path d="M330 90 V210" stroke="#344054" stroke-width="5" stroke-linecap="round" opacity="0.48"/>
      <path d="M330 96 H362 V142 H330 Z" fill="#fff8dc" stroke="${accent}" stroke-width="4" opacity="0.72"/>
    `,
  };

  return backdrops[icon];
}

function sceneEventLayer(moment: string, accent: string): string {
  const person = (x: number, y: number, color = "#f4b18b") => `
    <g>
      <circle cx="${x}" cy="${y}" r="10" fill="${color}"/>
      <path d="M${x} ${y + 10} V${y + 38}" stroke="#344054" stroke-width="8" stroke-linecap="round"/>
      <path d="M${x - 18} ${y + 24} H${x + 18}" stroke="#344054" stroke-width="7" stroke-linecap="round"/>
      <path d="M${x - 2} ${y + 38} L${x - 18} ${y + 60} M${x + 2} ${y + 38} L${x + 18} ${y + 60}" stroke="#344054" stroke-width="7" stroke-linecap="round"/>
    </g>`;

  const layers: Record<string, string> = {
    lantern_arrive: `
      ${person(90, 150)}
      ${person(134, 156, "#f7c59f")}
      <path d="M154 172 C182 154 216 148 246 158" fill="none" stroke="${accent}" stroke-width="6" stroke-linecap="round"/>
      <path d="M248 150 h30 l10 22 h-50 z" fill="#fff4d6" stroke="#8a4f2f" stroke-width="4"/>
    `,
    lantern_write: `
      ${person(116, 158)}
      ${person(248, 158, "#f7c59f")}
      <rect x="144" y="186" width="112" height="34" rx="8" fill="#fff8dc" stroke="#8a4f2f" stroke-width="4"/>
      <path d="M162 203 H210 M222 203 H240" stroke="${accent}" stroke-width="5" stroke-linecap="round"/>
      <path d="M142 168 L168 196 M258 168 L232 196" stroke="#344054" stroke-width="7" stroke-linecap="round"/>
    `,
    lantern_fall: `
      ${person(96, 162)}
      ${person(300, 162, "#f7c59f")}
      <g transform="rotate(-18 205 142)">
        <rect x="178" y="114" width="54" height="70" rx="18" fill="#ffcf56" stroke="#8a4f2f" stroke-width="5"/>
      </g>
      <path d="M122 178 C154 142 176 132 198 138 M278 178 C250 150 230 140 208 142" fill="none" stroke="${accent}" stroke-width="7" stroke-linecap="round"/>
      <path d="M194 193 C208 184 222 185 236 194" fill="none" stroke="#2f8f68" stroke-width="6" stroke-linecap="round"/>
    `,
    lantern_release: `
      ${person(128, 170)}
      ${person(276, 170, "#f7c59f")}
      <rect x="180" y="126" width="42" height="56" rx="16" fill="#ffcf56" stroke="#8a4f2f" stroke-width="4"/>
      <path d="M201 126 C200 100 212 82 238 70" fill="none" stroke="${accent}" stroke-width="5" stroke-linecap="round"/>
      <path d="M178 184 C190 198 212 198 224 184" fill="none" stroke="#344054" stroke-width="7" stroke-linecap="round"/>
    `,
    train_meet: `
      ${person(100, 160)}
      ${person(284, 160, "#f7c59f")}
      <rect x="150" y="184" width="96" height="24" rx="7" fill="#fff8dc" stroke="#6f4e37" stroke-width="4"/>
      <path d="M172 196 H224" stroke="${accent}" stroke-width="5" stroke-linecap="round"/>
    `,
    train_climb: `
      ${person(286, 156)}
      <path d="M88 210 C148 166 212 210 310 144" fill="none" stroke="#6f4e37" stroke-width="8" stroke-linecap="round"/>
      <path d="M224 152 L244 134 L254 150" fill="none" stroke="${accent}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
    `,
    fog_wait: `
      ${person(152, 164)}
      ${person(236, 164, "#f7c59f")}
      <path d="M76 152 C118 138 158 156 200 144 C242 132 286 148 332 136" fill="none" stroke="#f8fafc" stroke-width="13" stroke-linecap="round" opacity="0.88"/>
      <path d="M82 184 C132 172 172 190 216 178 C260 166 296 180 334 170" fill="none" stroke="#f8fafc" stroke-width="12" stroke-linecap="round" opacity="0.72"/>
    `,
    sunrise_describe: `
      ${person(134, 168)}
      ${person(258, 168, "#f7c59f")}
      <circle cx="200" cy="98" r="34" fill="#ffd166" opacity="0.92"/>
      <path d="M164 152 C180 136 220 136 236 152" fill="none" stroke="${accent}" stroke-width="6" stroke-linecap="round"/>
      <rect x="170" y="190" width="64" height="30" rx="8" fill="#fff8dc" stroke="#6f4e37" stroke-width="4"/>
    `,
    temple_prepare: `
      ${person(106, 162)}
      ${person(286, 162, "#f7c59f")}
      <path d="M154 206 C178 184 218 184 244 206" fill="none" stroke="#2f8f68" stroke-width="8" stroke-linecap="round"/>
      <circle cx="164" cy="200" r="7" fill="#ef6f6c"/><circle cx="204" cy="190" r="7" fill="#ffcf56"/><circle cx="238" cy="202" r="7" fill="${accent}"/>
    `,
    temple_parade: `
      ${person(90, 166)}
      ${person(164, 166, "#f7c59f")}
      ${person(300, 166, "#d99c77")}
      <path d="M116 146 H286" stroke="${accent}" stroke-width="8" stroke-linecap="round"/>
      <path d="M130 128 L150 146 L170 128 M230 128 L250 146 L270 128" fill="none" stroke="#ffcf56" stroke-width="6" stroke-linecap="round"/>
    `,
    temple_lost: `
      ${person(110, 164)}
      ${person(288, 164, "#f7c59f")}
      <circle cx="204" cy="160" r="13" fill="#d99c77"/>
      <path d="M204 173 V204" stroke="#344054" stroke-width="8" stroke-linecap="round"/>
      <path d="M184 138 C198 120 222 120 236 138" fill="none" stroke="${accent}" stroke-width="6" stroke-linecap="round"/>
      <text x="198" y="130" font-family="Inter, Arial" font-size="24" font-weight="800" fill="${accent}">?</text>
    `,
    temple_safe: `
      ${person(128, 164)}
      ${person(202, 156, "#d99c77")}
      ${person(278, 164, "#f7c59f")}
      <path d="M144 146 C166 124 238 124 260 146" fill="none" stroke="${accent}" stroke-width="7" stroke-linecap="round"/>
    `,
    fair_plan: `
      ${person(100, 164)}
      ${person(292, 164, "#f7c59f")}
      <rect x="146" y="144" width="108" height="60" rx="8" fill="#ffffff" stroke="#29756f" stroke-width="5"/>
      <path d="M166 164 H232 M166 184 H214" stroke="${accent}" stroke-width="5" stroke-linecap="round"/>
    `,
    fair_posters: `
      ${person(118, 162)}
      ${person(280, 162, "#f7c59f")}
      <rect x="150" y="130" width="96" height="82" rx="8" fill="#fff8dc" stroke="${accent}" stroke-width="5"/>
      <circle cx="180" cy="158" r="12" fill="#ef6f6c"/><path d="M166 188 H230" stroke="#29756f" stroke-width="6" stroke-linecap="round"/>
    `,
    fair_rain: `
      ${person(112, 164)}
      ${person(286, 164, "#f7c59f")}
      <path d="M154 188 H250" stroke="#8a4f2f" stroke-width="10" stroke-linecap="round"/>
      <path d="M92 98 L82 124 M146 92 L136 120 M256 94 L246 122 M314 98 L304 126" stroke="#4aa3c7" stroke-width="6" stroke-linecap="round"/>
      <path d="M132 166 L162 188 M268 166 L238 188" stroke="#344054" stroke-width="7" stroke-linecap="round"/>
    `,
    fair_share: `
      ${person(92, 166)}
      ${person(200, 156, "#f7c59f")}
      ${person(306, 166, "#d99c77")}
      <rect x="150" y="132" width="98" height="58" rx="8" fill="#ffffff" stroke="${accent}" stroke-width="5"/>
      <path d="M170 154 H226 M170 172 H212" stroke="#29756f" stroke-width="5" stroke-linecap="round"/>
    `,
    market_snack: `
      ${person(116, 162)}
      ${person(284, 162, "#f7c59f")}
      <circle cx="200" cy="188" r="18" fill="#d9a7f5" stroke="#6b5dad" stroke-width="4"/>
      <path d="M200 170 V142" stroke="#6b5dad" stroke-width="5" stroke-linecap="round"/>
    `,
    market_missing: `
      ${person(112, 164)}
      ${person(292, 164, "#f7c59f")}
      <path d="M184 204 C202 190 222 190 240 204" fill="none" stroke="${accent}" stroke-width="7" stroke-linecap="round"/>
      <text x="196" y="166" font-family="Inter, Arial" font-size="30" font-weight="800" fill="${accent}">?</text>
      <rect x="178" y="180" width="42" height="28" rx="6" fill="#8a4f2f" opacity="0.35"/>
    `,
    market_clue: `
      ${person(98, 164)}
      ${person(296, 164, "#f7c59f")}
      <rect x="164" y="152" width="76" height="46" rx="8" fill="#fff8dc" stroke="${accent}" stroke-width="5"/>
      <path d="M182 170 H222 M184 186 H208" stroke="#6b5dad" stroke-width="5" stroke-linecap="round"/>
      <path d="M124 154 C146 134 168 130 188 148" fill="none" stroke="${accent}" stroke-width="6" stroke-linecap="round"/>
    `,
    market_return: `
      ${person(116, 162)}
      ${person(284, 162, "#f7c59f")}
      <rect x="178" y="168" width="44" height="30" rx="7" fill="#8a4f2f" stroke="#fff8dc" stroke-width="4"/>
      <path d="M136 166 C164 146 184 148 198 168 M264 166 C236 146 216 148 202 168" fill="none" stroke="${accent}" stroke-width="7" stroke-linecap="round"/>
    `,
    boat_practice: `
      ${person(108, 150)}
      ${person(170, 150, "#f7c59f")}
      ${person(232, 150, "#d99c77")}
      <path d="M72 216 C140 236 256 236 328 216" fill="none" stroke="${accent}" stroke-width="11" stroke-linecap="round"/>
    `,
    boat_rhythm: `
      ${person(108, 152)}
      ${person(288, 152, "#f7c59f")}
      <circle cx="200" cy="158" r="26" fill="#ffcf56" stroke="#8a4f2f" stroke-width="5"/>
      <path d="M184 134 L170 108 M216 134 L230 108" stroke="#8a4f2f" stroke-width="6" stroke-linecap="round"/>
    `,
    boat_wind: `
      ${person(112, 152)}
      ${person(252, 152, "#f7c59f")}
      <path d="M66 106 C118 84 156 112 206 94 C250 78 296 98 340 82" fill="none" stroke="#f8fafc" stroke-width="11" stroke-linecap="round"/>
      <path d="M92 216 C160 236 242 234 320 214" fill="none" stroke="${accent}" stroke-width="10" stroke-linecap="round"/>
    `,
    boat_finish: `
      ${person(112, 152)}
      ${person(208, 152, "#f7c59f")}
      ${person(296, 152, "#d99c77")}
      <path d="M322 106 V210" stroke="#344054" stroke-width="6" stroke-linecap="round"/>
      <path d="M322 112 H358 V160 H322 Z" fill="#fff8dc" stroke="${accent}" stroke-width="5"/>
      <path d="M88 216 C168 238 252 236 326 214" fill="none" stroke="${accent}" stroke-width="11" stroke-linecap="round"/>
    `,
  };

  return `<g filter="url(#softShadow)" opacity="0.98">${layers[moment] ?? ""}</g>`;
}

function storyImage(scene: StoryScene): string {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
      <defs>
        <linearGradient id="sky" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="${scene.sky}"/>
          <stop offset="100%" stop-color="#fffaf0"/>
        </linearGradient>
        <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#17202a" flood-opacity="0.18"/>
        </filter>
        <filter id="watercolorSoft" x="-10%" y="-10%" width="120%" height="120%">
          <feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="3" seed="7" result="paperNoise"/>
          <feDisplacementMap in="SourceGraphic" in2="paperNoise" scale="1.6" xChannelSelector="R" yChannelSelector="G"/>
        </filter>
        <filter id="paperTexture" x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.72" numOctaves="2" seed="11" result="grain"/>
          <feColorMatrix in="grain" type="matrix" values="0 0 0 0 0.92 0 0 0 0 0.87 0 0 0 0 0.76 0 0 0 0.18 0"/>
        </filter>
        <linearGradient id="warmVignette" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.2"/>
          <stop offset="62%" stop-color="#f4dfbd" stop-opacity="0.04"/>
          <stop offset="100%" stop-color="#6f5b44" stop-opacity="0.16"/>
        </linearGradient>
      </defs>
      <rect x="8" y="8" width="384" height="284" rx="12" fill="#f7efe2" stroke="#223047" stroke-width="5"/>
      <clipPath id="panelClip">
        <rect x="12" y="12" width="376" height="276" rx="8"/>
      </clipPath>
      <g clip-path="url(#panelClip)">
        <rect width="400" height="300" fill="url(#sky)"/>
        <path d="M-20 214 C80 184 124 228 198 204 C274 180 328 192 420 162 V320 H-20 Z" fill="${scene.ground}" opacity="0.78"/>
        <path d="M-20 228 C86 198 140 235 210 216 C282 196 328 206 420 188 V320 H-20 Z" fill="#b9cda9" opacity="0.26"/>
        <circle cx="326" cy="60" r="31" fill="#f6d68b" opacity="0.5"/>
        <path d="M22 82 C72 58 116 54 166 68 M250 48 C292 34 338 40 374 62" fill="none" stroke="#8ea4b2" stroke-width="3" stroke-linecap="round" opacity="0.28"/>
        <g filter="url(#watercolorSoft)">
          ${sceneBackdrop(scene.icon, scene.accent)}
        </g>
        <g filter="url(#watercolorSoft)" opacity="0.94">
          ${sceneIllustration(scene.icon, scene.accent)}
        </g>
        <g filter="url(#watercolorSoft)">
          ${sceneEventLayer(scene.moment, scene.accent)}
        </g>
        <path d="M30 232 C92 212 142 224 202 235 C262 214 314 216 370 232" fill="none" stroke="#726653" stroke-width="2" stroke-linecap="round" opacity="0.22"/>
        <rect width="400" height="300" fill="url(#warmVignette)"/>
        <rect width="400" height="300" filter="url(#paperTexture)" opacity="0.52"/>
        <rect x="26" y="220" width="348" height="56" rx="8" fill="#fff7e6" opacity="0.88" stroke="#7b6650" stroke-width="1.6"/>
        <path d="M38 231 H166" stroke="${scene.accent}" stroke-width="5" stroke-linecap="round" opacity="0.32"/>
        <text x="44" y="244" font-family="Georgia, 'Times New Roman', serif" font-size="18" font-weight="700" fill="#3f3428">${escapeSvgText(scene.title)}</text>
        <text x="44" y="263" font-family="Inter, Arial, sans-serif" font-size="12" font-weight="700" fill="#6b5c49">${escapeSvgText(scene.subtitle)}</text>
      </g>
    </svg>
  `;

  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function storySequence(scenes: StoryScene[]): string[] {
  return scenes.map(storyImage);
}

const topicImages: Record<string, string[]> = {
  adventure: storySequence([
    {
      title: "Morning Bus Stop",
      subtitle: "A student waits before school",
      moment: "lantern_arrive",
      sky: "#dff3ff",
      ground: "#d8ead5",
      accent: "#e85d5a",
      icon: "lantern",
    },
    {
      title: "Ask About the Bus",
      subtitle: "A classmate checks the route",
      moment: "lantern_write",
      sky: "#ffe7c8",
      ground: "#e6d9b8",
      accent: "#e88f3a",
      icon: "lantern",
    },
    {
      title: "Bus Is Crowded",
      subtitle: "Students make room politely",
      moment: "lantern_fall",
      sky: "#dfd7ff",
      ground: "#d5cbe8",
      accent: "#7c6be8",
      icon: "lantern",
    },
    {
      title: "Arrive at School",
      subtitle: "The group walks to class",
      moment: "lantern_release",
      sky: "#fff1b8",
      ground: "#d7e8c4",
      accent: "#0f766e",
      icon: "lantern",
    },
    {
      title: "Forgot a Notebook",
      subtitle: "One student asks for help",
      moment: "lantern_write",
      sky: "#ffe9d6",
      ground: "#e7d8bd",
      accent: "#c65d45",
      icon: "lantern",
    },
    {
      title: "Plan After School",
      subtitle: "Friends decide where to meet",
      moment: "lantern_arrive",
      sky: "#dceeff",
      ground: "#d4e8d5",
      accent: "#2f8f68",
      icon: "lantern",
    },
  ]),
  nature: storySequence([
    {
      title: "Enter a Breakfast Shop",
      subtitle: "Friends look at the menu",
      moment: "train_meet",
      sky: "#cceeff",
      ground: "#c5dfcf",
      accent: "#bd5b42",
      icon: "mountainTrain",
    },
    {
      title: "Order Food",
      subtitle: "A student asks for noodles and tea",
      moment: "train_climb",
      sky: "#cdf2df",
      ground: "#b9d9ba",
      accent: "#0f766e",
      icon: "mountainTrain",
    },
    {
      title: "Check the Price",
      subtitle: "The cashier repeats the total",
      moment: "fog_wait",
      sky: "#d9e6f2",
      ground: "#bdcdbd",
      accent: "#6f8fa0",
      icon: "mountainTrain",
    },
    {
      title: "Find a Seat",
      subtitle: "The table is almost full",
      moment: "sunrise_describe",
      sky: "#ffe2b8",
      ground: "#d9e7bd",
      accent: "#d98c3d",
      icon: "mountainTrain",
    },
    {
      title: "Food Is Too Spicy",
      subtitle: "A friend asks for water",
      moment: "train_meet",
      sky: "#dff6ff",
      ground: "#cfe5cf",
      accent: "#0f766e",
      icon: "mountainTrain",
    },
    {
      title: "Clean the Table",
      subtitle: "Students leave politely",
      moment: "train_climb",
      sky: "#fff1cf",
      ground: "#d6e2bd",
      accent: "#bd6a42",
      icon: "mountainTrain",
    },
  ]),
  fantasy: storySequence([
    {
      title: "Lost Near a Station",
      subtitle: "A student cannot find the platform",
      moment: "temple_prepare",
      sky: "#fff0bf",
      ground: "#e6d7b8",
      accent: "#d9483b",
      icon: "temple",
    },
    {
      title: "Ask for Directions",
      subtitle: "A passerby points to the exit",
      moment: "temple_parade",
      sky: "#ffd9ca",
      ground: "#e8c9b9",
      accent: "#c2413f",
      icon: "temple",
    },
    {
      title: "Read the Map",
      subtitle: "The group checks the route",
      moment: "temple_lost",
      sky: "#d7e4ff",
      ground: "#d1d8e8",
      accent: "#5268a8",
      icon: "temple",
    },
    {
      title: "Call a Friend",
      subtitle: "Someone explains where they are",
      moment: "temple_safe",
      sky: "#dff6e6",
      ground: "#c9e4ca",
      accent: "#2f8f68",
      icon: "temple",
    },
    {
      title: "Find the Right Place",
      subtitle: "The student reaches the meeting point",
      moment: "temple_parade",
      sky: "#fff1cf",
      ground: "#e8d5bd",
      accent: "#d9483b",
      icon: "temple",
    },
    {
      title: "Say Thank You",
      subtitle: "Everyone repeats the directions",
      moment: "temple_prepare",
      sky: "#e6e0ff",
      ground: "#d4d9c7",
      accent: "#7c6be8",
      icon: "temple",
    },
  ]),
  school: storySequence([
    {
      title: "Group Project Starts",
      subtitle: "Students choose a topic",
      moment: "fair_plan",
      sky: "#d7efff",
      ground: "#d5e7d5",
      accent: "#0f766e",
      icon: "schoolFair",
    },
    {
      title: "Divide the Work",
      subtitle: "Each person gets one job",
      moment: "fair_posters",
      sky: "#d6f4ef",
      ground: "#cae6dc",
      accent: "#2e9384",
      icon: "schoolFair",
    },
    {
      title: "One Member Is Late",
      subtitle: "The group changes the plan",
      moment: "fair_rain",
      sky: "#e5dfd1",
      ground: "#d9d0b8",
      accent: "#bf8544",
      icon: "schoolFair",
    },
    {
      title: "Practice the Presentation",
      subtitle: "Students speak in order",
      moment: "fair_share",
      sky: "#dff3d2",
      ground: "#cfe4bc",
      accent: "#4e9d72",
      icon: "schoolFair",
    },
    {
      title: "Teacher Gives Feedback",
      subtitle: "The group revises one part",
      moment: "fair_posters",
      sky: "#e8f7f4",
      ground: "#d7e5d4",
      accent: "#0f766e",
      icon: "schoolFair",
    },
    {
      title: "Submit the Project",
      subtitle: "Students explain what improved",
      moment: "fair_plan",
      sky: "#fff0d6",
      ground: "#e3d4bd",
      accent: "#bf8544",
      icon: "schoolFair",
    },
  ]),
  mystery: storySequence([
    {
      title: "Buy a Raincoat",
      subtitle: "A student chooses a color",
      moment: "market_snack",
      sky: "#ffe5c7",
      ground: "#e3c9aa",
      accent: "#e08a45",
      icon: "nightMarket",
    },
    {
      title: "Check the Size",
      subtitle: "The jacket does not fit",
      moment: "market_missing",
      sky: "#d7d4f3",
      ground: "#c9c2db",
      accent: "#6b5dad",
      icon: "nightMarket",
    },
    {
      title: "Ask to Exchange It",
      subtitle: "The clerk explains the rule",
      moment: "market_clue",
      sky: "#dce7ff",
      ground: "#ccd7e7",
      accent: "#536aa4",
      icon: "nightMarket",
    },
    {
      title: "Find the Receipt",
      subtitle: "The student searches the bag",
      moment: "market_return",
      sky: "#d8f4e6",
      ground: "#c6e4cd",
      accent: "#2f8f68",
      icon: "nightMarket",
    },
    {
      title: "Choose a New One",
      subtitle: "The student compares two options",
      moment: "market_snack",
      sky: "#ffe8c7",
      ground: "#e5c9aa",
      accent: "#d97854",
      icon: "nightMarket",
    },
    {
      title: "Leave the Store",
      subtitle: "The clerk and student say goodbye",
      moment: "market_clue",
      sky: "#dcefff",
      ground: "#cbd9e0",
      accent: "#536aa4",
      icon: "nightMarket",
    },
  ]),
  "daily-life": storySequence([
    {
      title: "Rain After Class",
      subtitle: "Students wait near the door",
      moment: "boat_practice",
      sky: "#cfeeff",
      ground: "#c4dfcf",
      accent: "#238d7a",
      icon: "dragonBoat",
    },
    {
      title: "Share an Umbrella",
      subtitle: "A friend offers help",
      moment: "boat_rhythm",
      sky: "#d6f2e4",
      ground: "#c7e5d0",
      accent: "#55a06f",
      icon: "dragonBoat",
    },
    {
      title: "Puddle on the Street",
      subtitle: "The group walks carefully",
      moment: "boat_wind",
      sky: "#d7e2f3",
      ground: "#c8ddbe",
      accent: "#457f9a",
      icon: "dragonBoat",
    },
    {
      title: "Miss the Bus",
      subtitle: "Students decide what to do",
      moment: "boat_finish",
      sky: "#ffd9ca",
      ground: "#e5cdbb",
      accent: "#d97854",
      icon: "dragonBoat",
    },
    {
      title: "Text the Family",
      subtitle: "Someone explains they will be late",
      moment: "boat_rhythm",
      sky: "#fff0bf",
      ground: "#d9dfbd",
      accent: "#d98c3d",
      icon: "dragonBoat",
    },
    {
      title: "Arrive Home Safely",
      subtitle: "The student thanks the friend",
      moment: "boat_practice",
      sky: "#dff3ff",
      ground: "#c5dfcf",
      accent: "#238d7a",
      icon: "dragonBoat",
    },
  ]),
};

const DEFAULT_CUE_VOCABULARY: string[][] = [
  ["who", "where", "first event", "describe"],
  ["then", "action", "detail", "explain"],
  ["problem", "surprise", "help", "change"],
  ["result", "feeling", "because", "finally"],
  ["revise", "clearer", "connect", "practice"],
  ["ending", "lesson", "next time", "improve"],
];

const BASE_TOPICS: Topic[] = [
  {
    id: "adventure",
    name: "Pingxi Sky Lantern Festival",
    description: "Tell an event story about writing wishes, helping friends, and launching lanterns in Pingxi.",
    skillFocus: "Event sequence and feelings",
    level: "Festival Story",
    images: topicImages.adventure,
    vocabulary: {
      0: ["平溪", "天燈", "街道", "人群"],
      1: ["願望", "祝福", "寫字", "希望"],
      2: ["幫忙", "小心", "朋友", "一起"],
      3: ["升起", "天空", "發光", "感動"],
    },
  },
  {
    id: "nature",
    name: "Alishan Cherry Blossom Train",
    description: "Describe an Alishan festival trip from the forest train to cherry blossoms and sunrise.",
    skillFocus: "Setting and sensory detail",
    level: "Seasonal Event",
    images: topicImages.nature,
    vocabulary: {
      0: ["阿里山", "火車", "車站", "出發"],
      1: ["櫻花", "森林", "山路", "拍照"],
      2: ["霧", "等待", "安靜", "清晨"],
      3: ["日出", "雲海", "漂亮", "風景"],
    },
  },
  {
    id: "fantasy",
    name: "Dajia Mazu Pilgrimage",
    description: "Tell a community story about the Dajia Mazu pilgrimage, volunteers, and helping someone safely.",
    skillFocus: "Community and problem solving",
    level: "Temple Event",
    images: topicImages.fantasy,
    vocabulary: {
      0: ["大甲", "媽祖", "廟", "志工"],
      1: ["遶境", "隊伍", "熱鬧", "香火"],
      2: ["迷路", "孩子", "幫助", "尋找"],
      3: ["平安", "家人", "謝謝", "團結"],
    },
  },
  {
    id: "school",
    name: "Taipei 101 New Year Countdown",
    description: "Tell a countdown event story about preparing posters, solving a rain problem, and watching fireworks.",
    skillFocus: "Explaining and teamwork",
    level: "City Event",
    images: topicImages.school,
    vocabulary: {
      0: ["台北", "一零一", "跨年", "計畫"],
      1: ["海報", "煙火", "安全", "介紹"],
      2: ["下雨", "移動", "合作", "等待"],
      3: ["倒數", "新年", "歡呼", "煙火"],
    },
  },
  {
    id: "mystery",
    name: "Ningxia Night Market Food Festival",
    description: "Build a food festival mystery at Ningxia Night Market using clues, kindness, and a returned ticket.",
    skillFocus: "Problem and solution",
    level: "Market Event",
    images: topicImages.mystery,
    vocabulary: {
      0: ["寧夏夜市", "小吃", "蚵仔煎", "珍珠奶茶"],
      1: ["票券", "不見", "著急", "尋找"],
      2: ["老闆", "線索", "藍色袋子", "記得"],
      3: ["找到", "還給", "誠實", "謝謝"],
    },
  },
  {
    id: "daily-life",
    name: "Lukang Dragon Boat Festival",
    description: "Practice a sports event story about teamwork during a Lukang Dragon Boat Festival race.",
    skillFocus: "Action and encouragement",
    level: "Race Event",
    images: topicImages["daily-life"],
    vocabulary: {
      0: ["鹿港", "端午節", "龍舟", "隊友"],
      1: ["鼓聲", "節奏", "划船", "加油"],
      2: ["風", "努力", "不放棄", "合作"],
      3: ["終點", "成功", "歡呼", "團隊"],
    },
  },
];

const REAL_LIFE_TOPIC_DETAILS: Record<
  string,
  Pick<Topic, "name" | "description" | "skillFocus" | "level">
> = {
  adventure: {
    name: "Taking the Bus to School",
    description:
      "Practice a real morning routine: waiting for the bus, asking about the route, arriving at school, and planning after class.",
    skillFocus: "Daily routine and polite requests",
    level: "Real-life situation",
  },
  nature: {
    name: "Ordering Breakfast",
    description:
      "Practice ordering food, checking the price, finding a seat, and responding when something is too spicy.",
    skillFocus: "Food ordering and preferences",
    level: "Real-life situation",
  },
  fantasy: {
    name: "Asking for Directions",
    description:
      "Practice what to say when you are lost near a station and need to ask, understand, and repeat directions.",
    skillFocus: "Directions and asking for help",
    level: "Real-life situation",
  },
  school: {
    name: "Working on a Group Project",
    description:
      "Practice a classroom situation: choosing a topic, dividing work, handling a late member, and revising after feedback.",
    skillFocus: "Teamwork and explanation",
    level: "School situation",
  },
  mystery: {
    name: "Shopping and Returning an Item",
    description:
      "Practice shopping language: choosing an item, checking size, asking to exchange it, and speaking politely to the clerk.",
    skillFocus: "Shopping and problem solving",
    level: "Real-life situation",
  },
  "daily-life": {
    name: "Rainy Day After School",
    description:
      "Practice a common weather situation: sharing an umbrella, missing the bus, texting family, and arriving home safely.",
    skillFocus: "Weather, help, and updates",
    level: "Real-life situation",
  },
};

const REAL_LIFE_VOCABULARY: Record<string, Record<number, string[]>> = {
  adventure: {
    0: ["bus stop", "school", "wait", "morning"],
    1: ["route", "which bus", "ask", "classmate"],
    2: ["crowded", "please", "make room", "thank you"],
    3: ["arrive", "classroom", "walk", "on time"],
    4: ["forgot", "notebook", "borrow", "help"],
    5: ["after school", "meet", "plan", "together"],
  },
  nature: {
    0: ["breakfast shop", "menu", "hungry", "friend"],
    1: ["order", "noodles", "tea", "please"],
    2: ["price", "total", "cashier", "pay"],
    3: ["seat", "table", "full", "share"],
    4: ["spicy", "water", "too hot", "help"],
    5: ["clean", "tray", "thank you", "leave"],
  },
  fantasy: {
    0: ["station", "platform", "lost", "worried"],
    1: ["direction", "exit", "ask", "turn left"],
    2: ["map", "route", "check", "where"],
    3: ["call", "friend", "explain", "location"],
    4: ["meeting point", "arrive", "right place", "safe"],
    5: ["thank you", "repeat", "direction", "polite"],
  },
  school: {
    0: ["project", "topic", "group", "start"],
    1: ["divide work", "job", "teammate", "plan"],
    2: ["late", "change plan", "message", "problem"],
    3: ["practice", "presentation", "speak", "order"],
    4: ["teacher", "feedback", "revise", "improve"],
    5: ["submit", "explain", "finish", "reflection"],
  },
  mystery: {
    0: ["raincoat", "color", "choose", "store"],
    1: ["size", "too small", "try on", "fit"],
    2: ["exchange", "clerk", "rule", "ask"],
    3: ["receipt", "bag", "find", "search"],
    4: ["new one", "compare", "better", "decision"],
    5: ["goodbye", "thank you", "leave", "polite"],
  },
  "daily-life": {
    0: ["rain", "after class", "door", "wait"],
    1: ["umbrella", "share", "friend", "help"],
    2: ["puddle", "careful", "street", "walk"],
    3: ["miss the bus", "decide", "late", "what now"],
    4: ["text", "family", "explain", "arrive late"],
    5: ["home", "safe", "thank", "friend"],
  },
};

export const TOPICS: Topic[] = BASE_TOPICS.map((topic) => ({
  ...topic,
  ...REAL_LIFE_TOPIC_DETAILS[topic.id],
  vocabulary: REAL_LIFE_VOCABULARY[topic.id] || topic.vocabulary,
}));

export function getTopicVocabulary(topic: Topic, imageIndex: number): string[] {
  return topic.vocabulary[imageIndex] || DEFAULT_CUE_VOCABULARY[imageIndex] || [];
}

export default function TopicSelector({ onTopicSelect }: TopicSelectorProps) {
  const topics = [...TOPICS, ...loadPublishedTeacherTopics()];
  const [selectedTopic, setSelectedTopic] = useState<Topic>(topics[0]);
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);

  const selectedImage = selectedTopic.images[selectedImageIndex];
  const selectedWords = getTopicVocabulary(selectedTopic, selectedImageIndex);

  const chooseTopic = (topic: Topic) => {
    setSelectedTopic(topic);
    setSelectedImageIndex(0);
  };

  return (
    <div className="topic-selector">
      <section className="learning-hero">
        <div className="learning-hero-copy">
          <p className="platform-kicker">Real-life speaking practice</p>
          <h1>Choose a Daily Situation</h1>
          <p>
            Select a real situation students may meet in daily life, study the
            six connected picture cues, prepare useful Mandarin phrases, and
            record each cue for Praat prosody and Gemini language feedback.
          </p>
        </div>

        <div className="learning-objectives" aria-label="Learning objectives">
          <div>
            <strong>1</strong>
            <span>Plan the story</span>
          </div>
          <div>
            <strong>2</strong>
            <span>Record Mandarin speech</span>
          </div>
          <div>
            <strong>3</strong>
            <span>Review pronunciation and language feedback</span>
          </div>
        </div>
      </section>

      <section className="activity-layout">
        <aside className="activity-sidebar" aria-label="Story topics">
          <div className="sidebar-heading">
            <p className="platform-kicker">Activity menu</p>
            <h2>Taiwan story topics</h2>
          </div>

          <div className="topic-list">
            {topics.map((topic) => (
              <button
                type="button"
                key={topic.id}
                className={`topic-row ${
                  selectedTopic.id === topic.id ? "selected" : ""
                }`}
                onClick={() => chooseTopic(topic)}
              >
                <span>
                  <strong>{topic.name}</strong>
                  <small>{topic.skillFocus}</small>
                </span>
                <em>{topic.level}</em>
              </button>
            ))}
          </div>
        </aside>

        <section className="activity-preview" aria-label="Selected activity">
          <div className="preview-header">
            <div>
              <p className="platform-kicker">Selected module</p>
              <h2>{selectedTopic.name}</h2>
              <p>{selectedTopic.description}</p>
            </div>
            <div className="module-badge">{selectedTopic.level}</div>
          </div>

          <div className="preview-grid">
            <div className="main-prompt-card">
              <img
                src={selectedImage}
                alt={`${selectedTopic.name} story part ${
                  selectedImageIndex + 1
                }`}
              />
              <div className="prompt-number">
                Story part {selectedImageIndex + 1} of{" "}
                {selectedTopic.images.length}
              </div>
            </div>

            <div className="prompt-planning-panel">
              <div className="planning-block">
                <h3>Speaking goals</h3>
                <ul>
                  <li>Describe the real situation clearly.</li>
                  <li>Use useful phrases for daily communication.</li>
                  <li>Revise each cue after feedback.</li>
                </ul>
              </div>

              <div className="planning-block">
                <h3>Vocabulary support</h3>
                <div className="vocabulary-chips">
                  {selectedWords.map((word) => (
                    <span key={word}>{word}</span>
                  ))}
                </div>
              </div>

              <button
                type="button"
                className="start-activity-btn"
                onClick={() => onTopicSelect?.(selectedTopic)}
              >
                Start recording this activity
              </button>
            </div>
          </div>

          <div className="prompt-strip" aria-label="Story sequence prompts">
            {selectedTopic.images.map((image, index) => (
              <button
                type="button"
                key={image}
                className={`prompt-thumb ${
                  selectedImageIndex === index ? "active" : ""
                }`}
                onClick={() => setSelectedImageIndex(index)}
              >
                <img src={image} alt={`Story part ${index + 1}`} />
                <span>Part {index + 1}</span>
              </button>
            ))}
          </div>
        </section>
      </section>
    </div>
  );
}

