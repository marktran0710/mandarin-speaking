import { useEffect, useState } from "react";
import { BiLabel } from "./BiLabel";
import { canUseDatabase, listVocabQuizAttempts } from "../services/database";
import { loadLocalStars, starsByStory } from "../utils/quizTiers";
import { pickStripMessage, type StripMessage } from "../utils/journeyStrip";
import "./JourneyStrip.css";

/** The unified opener of every non-practice student page (see the
 * student-shell design): greeting + total earned stars + one motivational
 * slot — a near-miss nudge with a jump button when a story is 1-2 answers
 * from its next star, else the freshest milestone, else a welcome. */
export default function JourneyStrip({
  studentName,
  studentId,
  storyCount,
  storyTitles,
  onJumpToStory,
}: {
  studentName?: string;
  studentId?: string;
  // How many stories exist (denominator: 3 stars each) and their display
  // titles by quiz storyId — used for the near-miss button label.
  storyCount: number;
  storyTitles: Record<string, string>;
  onJumpToStory?: (storyId: string) => void;
}) {
  // Device-local stars paint instantly; the attempts fetch below raises the
  // total and picks the message once (and if) the backend answers.
  const localTotal = Object.keys(storyTitles).reduce(
    (sum, id) => sum + loadLocalStars(id),
    0,
  );
  const [totalStars, setTotalStars] = useState(localTotal);
  const [message, setMessage] = useState<StripMessage>({ kind: "welcome" });

  useEffect(() => {
    if (!canUseDatabase() || (!studentId && !studentName)) return;
    let cancelled = false;
    listVocabQuizAttempts(undefined, { studentId, studentName })
      .then((attempts) => {
        if (cancelled) return;
        const derived = Object.values(starsByStory(attempts)).reduce<number>(
          (sum, stars) => sum + stars,
          0,
        );
        setTotalStars((current) => Math.max(current, derived));
        setMessage(pickStripMessage(attempts));
      })
      .catch(() => {
        /* best-effort — the strip just keeps its local numbers */
      });
    return () => {
      cancelled = true;
    };
  }, [studentId, studentName]);

  return (
    <div className="journey-strip" role="region" aria-label="Your learning journey">
      <span className="journey-strip-greeting">
        👋{" "}
        <BiLabel
          zh={studentName ? `你好，${studentName}！` : "你好！"}
          pinyin={studentName ? `Nǐ hǎo, ${studentName}!` : "Nǐ hǎo!"}
          en={studentName ? `Hi, ${studentName}!` : "Hi!"}
        />
      </span>
      <span className="journey-strip-stars" aria-label={`${totalStars} of ${storyCount * 3} stars earned`}>
        ⭐ {totalStars} / {storyCount * 3}
      </span>
      <span className="journey-strip-message">
        {message.kind === "near_miss" && (
          <>
            🎯{" "}
            <BiLabel
              zh={`再答對 ${message.gap} 題就有星星！`}
              pinyin={`Zài dá duì ${message.gap} tí jiù yǒu xīngxing!`}
              en={`Just ${message.gap} more right for a star!`}
            />
            {onJumpToStory && (
              <button
                type="button"
                className="journey-strip-jump"
                onClick={() => onJumpToStory(message.storyId)}
              >
                {storyTitles[message.storyId] ?? message.storyId} →
              </button>
            )}
          </>
        )}
        {message.kind === "milestone" && (
          <>
            🎉{" "}
            <BiLabel
              zh={`你拿到 ${"⭐".repeat(message.stars)} 了，太棒了！`}
              pinyin={`Nǐ nádào ${"⭐".repeat(message.stars)} le, tài bàng le!`}
              en={`You earned ${"⭐".repeat(message.stars)} — great work!`}
            />
          </>
        )}
        {message.kind === "welcome" && (
          <>
            🌱{" "}
            <BiLabel
              zh="開始拿你的第一顆星吧！"
              pinyin="Kāishǐ ná nǐ de dì yī kē xīng ba!"
              en="Start earning your first star!"
            />
          </>
        )}
      </span>
    </div>
  );
}
