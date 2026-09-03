import { useState } from "react";
import type { HelpRequest } from "../../services/database";
import { BiLabel, BiText } from "../BiLabel";
import { getStudentName } from "../../utils/studentSession";
import StudentIcon from "../StudentIcon";

/** The quiet "raise your hand" form students use mid-practice. Lives at the
 * bottom of the story-session sidebar during a practice session (compact,
 * stacked) and as a banner strip on the topic browser (two-column) — layout
 * comes from the surrounding container's CSS, the markup is shared. */
export default function StudentHelpPanel({
  helpRequests,
  onRaiseHand,
  variant = "banner",
}: {
  helpRequests: HelpRequest[];
  onRaiseHand?: (message: string) => void;
  /** Sidebar context: the icon + button already say "this raises a hand" —
   * drop the full explanatory sentence (and its pinyin line) down to a
   * short label, since it's visible on every screen of a practice session,
   * not just the first time. The topic-browser banner has room and keeps
   * the full prompt. */
  variant?: "banner" | "compact";
}) {
  const [message, setMessage] = useState("我的故事需要協助。");
  const studentName = getStudentName();
  const isCompact = variant === "compact";
  const activeRequest = helpRequests.find(
    (request) =>
      request.studentName === studentName && request.status === "open",
  );

  return (
    <section className="student-help-panel" aria-label="Ask teacher for help">
      <div>
        <span className="student-help-icon" aria-hidden="true">
          <StudentIcon name="help" size={18} />
        </span>
        <div>
          {activeRequest ? (
            isCompact ? (
              <p><BiLabel zh="老師已看到" en="Teacher notified" /></p>
            ) : (
              <>
                <strong>
                  <BiLabel k="teacher_has_your_help_request" />
                </strong>
                <p>
                  <BiText k="stay_on_your_task_your_teacher_can_see_t" />
                </p>
              </>
            )
          ) : isCompact ? (
            <p><BiLabel zh="需要幫忙？" en="Need help?" /></p>
          ) : (
            <p>
              <BiText k="need_teacher_help_prompt" />
            </p>
          )}
        </div>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onRaiseHand?.(message);
        }}
      >
        <input
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          aria-label="Help request message"
          placeholder="需要什麼幫助？ What do you need help with?"
        />
        <button type="submit" disabled={!onRaiseHand}>
          {activeRequest ? <BiLabel k="update_request" /> : <BiLabel k="raise_hand" />}
        </button>
      </form>
    </section>
  );
}
