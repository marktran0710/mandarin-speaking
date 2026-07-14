import type {
  PauseAnalysis,
  PraatMetrics,
  WordProsody,
} from "../components/StoryRecorder";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

export function getBackendUrl(): string {
  if (BACKEND_URL) {
    return BACKEND_URL;
  }

  throw new Error(
    "Praat analysis needs a deployed backend in production. Deploy the FastAPI backend and set VITE_BACKEND_URL to its public URL.",
  );
}

/** Maps a Mandarin tone number to the TONE_SHAPES key for its target pitch shape. */
export const TONE_NUMBER_TO_SHAPE: Record<number, string> = {
  1: "level",
  2: "rising",
  3: "dip",
  4: "falling",
};

export const TONE_SHAPES: Record<
  string,
  { label: string; arrow: string; tip: string; drill: string }
> = {
  level: {
    label: "平直 Level →",
    arrow: "→",
    tip: "全程保持平直。 Stays flat throughout.",
    drill:
      "再說一次，試著加入更多變化 — 上升或下降。 Say it again and try to add more movement — either rise or fall.",
  },
  rising: {
    label: "上升 Rising ↗",
    arrow: "↗",
    tip: "音高從頭到尾上升。 Pitch rises start to end.",
    drill:
      "上升形狀不錯。把開頭降低一點，結尾再推高一點。 Good upward shape. Make the start lower and push the end higher.",
  },
  falling: {
    label: "下降 Falling ↘",
    arrow: "↘",
    tip: "音高從頭到尾下降。 Pitch falls start to end.",
    drill:
      "下降形狀不錯。開頭要高，然後急速下降。 Good downward shape. Start high and let it drop sharply.",
  },
  dip: {
    label: "低降 Dip ↘↗",
    arrow: "↘↗",
    tip: "先下降再上升。 Dips down, then rises.",
    drill:
      "低降形狀不錯。最低點要更深一點再回升。 Good dip shape. Make the lowest point deeper before rising back.",
  },
  variable: {
    label: "不清楚 Unclear ??",
    arrow: "??",
    tip: "未偵測到清楚的形狀。 No clear shape was detected.",
    drill:
      "把這個字單獨拿出來，慢慢說 3 次，再放回句子。 Isolate this character, say it 3 times slowly, then put it back.",
  },
};

export const TONE_NUMBER_ARROW_LABEL: Record<number, string> = {
  1: "一聲 Tone 1 (ā) →",
  2: "二聲 Tone 2 (á) ↗",
  3: "三聲 Tone 3 (ǎ) ↘↗",
  4: "四聲 Tone 4 (à) ↘",
};

/** Actionable improvement tip for this character — only shown when the
 * character actually needs work. Gated directly off item.feedback's own
 * verdict (backend's _word_prosody_feedback), not a separate threshold
 * re-check, so the tip can never disagree with the feedback text shown right
 * above it. When there's an expected Mandarin tone, the tip points at THAT
 * tone's target shape, not whatever (possibly wrong) shape the attempt
 * happened to produce. */
export function prosodyImprovementTip(item: WordProsody): string | null {
  const feedback = item.feedback ?? "";

  if (item.expected_tones && item.expected_tones.length > 0) {
    // item.feedback already says "Good match for ..." vs "Recognizable ...
    // but contrast could be sharper" / "Expected ... doesn't match yet" —
    // key off that text directly instead of re-deriving from tone_accuracy.
    if (feedback.startsWith("Good match")) return null;

    // Tone 5 (neutral) has no fixed target shape — it's short, light, and
    // takes its pitch from the preceding syllable — so don't claim "no clear
    // shape detected" (false; a shape WAS detected, it just isn't graded
    // against rising/falling/level/dip the way tones 1-4 are).
    if (item.expected_tones[0] === 5) {
      return "輕聲沒有固定的音高形狀 — 試著把這個字說得更短、更輕。 Neutral tone has no fixed pitch shape — try making this syllable shorter and lighter instead.";
    }

    const targetKey =
      TONE_NUMBER_TO_SHAPE[item.expected_tones[0]] ?? "variable";
    const target = TONE_SHAPES[targetKey];
    return `目標形狀：${target.tip} 刻意誇大這個音高變化，再說一次。 Target shape: ${target.tip} Exaggerate that pitch movement and try again.`;
  }

  // No expected tone (open-vocabulary): backend only flags a problem when no
  // clear shape was detected, which is the same "variable" case here.
  if (item.contour_shape !== "variable") return null;
  return TONE_SHAPES.variable.drill;
}

export function sceneReady(prog: {
  attempts: number;
  bestTone: number;
  bestFluency: number;
}): boolean {
  // Short-phrase threshold: tone accuracy ≥ 70%
  // Long-sentence threshold: fluency ≥ 65%
  // Override: 4+ attempts always unlocks next scene
  return prog.bestTone >= 70 || prog.bestFluency >= 65 || prog.attempts >= 4;
}

/** Real, measured prosody score — the average per-character tone_accuracy from
 * word_prosody — as opposed to the AI's generic pronunciation_note.score, which
 * isn't grounded in the actual measured pitch data. */
/** Pronunciation feedback only matters once the sentence's meaning is accepted. */
export function isContentAccepted(praatMetrics: PraatMetrics): boolean {
  const contentAccuracy = praatMetrics.ai_feedback?.content_accuracy;
  if (!contentAccuracy?.feedback) return true;
  return contentAccuracy.accepted !== false;
}

export function averageWordProsodyAccuracy(
  wordProsody?: WordProsody[],
): number | null {
  const accuracies = (wordProsody ?? [])
    .map((item) => item.tone_accuracy)
    .filter((value): value is number => typeof value === "number");
  if (accuracies.length === 0) return null;
  return Math.round(
    accuracies.reduce((sum, value) => sum + value, 0) / accuracies.length,
  );
}

export function buildPracticeAnalysisText(vocabulary: string[]): string {
  return vocabulary
    .map((word) => word.trim())
    .filter(Boolean)
    .join(" ");
}

export function hasAudioFileExtension(fileName: string): boolean {
  return /\.(wav|wave|webm|mp3|m4a|ogg)$/i.test(fileName);
}

export function formatContourShape(shape: string): string {
  const labels: Record<string, string> = {
    dip: "低降 Dipping",
    falling: "下降 Falling",
    level: "平直 Level",
    rising: "上升 Rising",
    variable: "變化 Variable",
  };
  return labels[shape] || "變化 Variable";
}

export function studentStrength(
  toneAccuracy: number,
  fluencyScore: number,
): string {
  if (toneAccuracy >= 68 && fluencyScore >= 65) {
    return "你的聲調和節奏夠清楚，可以試著造更長的句子。 Your tones and rhythm are clear enough to build a longer sentence.";
  }
  if (toneAccuracy >= 60) {
    return "你的聲調形狀可以辨識。 Your tone shape is recognizable.";
  }
  if (fluencyScore >= 62) {
    return "你的說話節奏很穩定。 Your speaking rhythm is steady.";
  }
  return "你完成了一次錄音，現在改進一個小地方。 You completed a recording. Now improve one small part.";
}

export function studentFix(
  toneAccuracy: number,
  fluencyScore: number,
  speechRate: number,
  focus?: WordProsody,
  pauseAnalysis?: PauseAnalysis,
): string {
  if (speechRate > 6.5) {
    return "放慢速度 — 每個普通話聲調都需要時間才能完整呈現。 Slow down — each Mandarin tone needs time to complete its shape.";
  }
  if (pauseAnalysis && pauseAnalysis.longest_pause >= 0.8) {
    return `你停頓了 ${pauseAnalysis.longest_pause.toFixed(1)} 秒 — 試著把這些詞連起來不要停。 You paused ${pauseAnalysis.longest_pause.toFixed(1)}s — try linking those words without stopping.`;
  }
  if (toneAccuracy < 50 && focus) {
    return `把「${focus.token}」的聲調變化說得更清楚 — 先誇張一點，再放鬆。 Make the tone movement clearer on "${focus.token}" — exaggerate it first, then smooth it out.`;
  }
  if (fluencyScore < 48) {
    return "把每個字連成一口氣 — 不要在每個詞之間停頓。 Connect the characters into one breath — don't stop between every word.";
  }
  if (focus) {
    return `「${focus.token}」的音高不穩 — 先單獨說兩次，再說完整句子。 "${focus.token}" has uneven pitch — isolate it, say it twice, then say the full sentence.`;
  }
  return "把句子說短一點，並讓每個聲調形狀都清晰分明。 Keep the sentence short and make every tone shape distinct.";
}

export function studentNextStep(
  speechRate: number,
  focus?: WordProsody,
  pauseAnalysis?: PauseAnalysis,
): string {
  if (focus) {
    return `練習「${focus.token}」：單獨說 3 次，再放回句子裡。 Drill "${focus.token}": say it alone 3×, then put it back in the sentence.`;
  }
  if (pauseAnalysis && pauseAnalysis.pause_count > 2) {
    return "再錄一次，試著一口氣說完整個句子。 Record again but try to say the whole sentence in one breath.";
  }
  if (speechRate < 2.5) {
    return "再試一次這個句子 — 稍微快一點，並保持聲調清晰。 Try the sentence again — a little faster, keeping the tones clear.";
  }
  return "再錄一次，把聲調形狀做得更誇張一些。 Record again and push the tone shapes a bit further (exaggerate).";
}

/** The characters actually dragging this attempt's tone score down — used to
 * personalize the "how to reach 100%" guide with the specific tone(s) this
 * student got wrong, instead of a generic list of all four tones every time.
 * Threshold and neutral-tone exclusion match prosodyImprovementTip's own
 * "Good match" cutoff so the two never disagree about what needs work. */
export function weakToneGuideItems(
  wordProsody: WordProsody[],
  limit = 3,
): WordProsody[] {
  return wordProsody
    .filter(
      (item) =>
        (item.expected_tones?.length ?? 0) > 0 &&
        item.expected_tones![0] !== 5 &&
        (item.tone_accuracy ?? 100) < 68,
    )
    .sort((a, b) => (a.tone_accuracy ?? 0) - (b.tone_accuracy ?? 0))
    .slice(0, limit);
}

export function getToneFocusItems(items: WordProsody[]): WordProsody[] {
  const scored = items.map((item) => ({
    item,
    score:
      (item.contour_shape === "variable" ? 3 : 0) +
      (item.pitch_range < 15 ? 2 : 0) +
      (item.pitch_range > 95 ? 1 : 0),
  }));

  const focus = scored
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((entry) => entry.item)
    .slice(0, 4);

  return focus.length > 0 ? focus : items.slice(0, 4);
}

export async function readErrorResponse(
  response: Response,
): Promise<{ detail?: string }> {
  try {
    return await response.json();
  } catch {
    return { detail: `${response.status} ${response.statusText}` };
  }
}

export function formatBackendError(error: unknown, backendUrl: string): string {
  const message = error instanceof Error ? error.message : String(error);
  const networkFailures = [
    "Failed to fetch",
    "NetworkError",
    "Load failed",
    "The operation was aborted",
  ];

  if (networkFailures.some((failure) => message.includes(failure))) {
    return `無法連線到語音分析後端 ${backendUrl}。請先啟動 FastAPI 後端（連接埠 8000），再重新錄音。 Cannot reach the speech analysis backend at ${backendUrl}. Start the FastAPI backend on port 8000, then record again.`;
  }

  return message || "語音分析發生錯誤 Speech analysis error occurred";
}
