import { useState } from "react";
import type { HelpRequest } from "../services/database";
import { BiLabel, BiText } from "./BiLabel";
import { getSessionName } from "../utils/myStoriesUtils";

/** The quiet "raise your hand" form students use mid-practice. Lives at the
 * bottom of the story-session sidebar during a practice session (compact,
 * stacked) and as a banner strip on the topic browser (two-column) — layout
 * comes from the surrounding container's CSS, the markup is shared. */
export default function StudentHelpPanel({
  helpRequests,
  onRaiseHand,
}: {
  helpRequests: HelpRequest[];
  onRaiseHand?: (message: string) => void;
}) {
  const [message, setMessage] = useState("我的故事需要協助。");
  const studentName = getSessionName("studentSession", "Student");
  const activeRequest = helpRequests.find(
    (request) =>
      request.studentName === studentName && request.status === "open",
  );

  return (
    <section className="student-help-panel" aria-label="Ask teacher for help">
      <div>
        <span className="student-help-icon" aria-hidden="true">
          ?
        </span>
        <div>
          {activeRequest ? (
            <>
              <strong>
                <BiLabel k="teacher_has_your_help_request" />
              </strong>
              <p>
                <BiText k="stay_on_your_task_your_teacher_can_see_t" />
              </p>
            </>
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
