import { useState } from "react";
import type { Topic } from "@entities/topic";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import "@shared/ui/student/layout.css";
import "./SubmitStoryPage.css";

type SubmitState = "idle" | "submitting" | "error";

interface SubmitStoryPageProps {
  topic: Topic;
  sceneCount: number;
  scenesRecorded: number;
  /** Student turns in the lesson's conversation (0 = no conversation). */
  turnCount: number;
  turnsRecorded: number;
  alreadySubmitted?: boolean;
  onSubmit: () => Promise<void>;
}

function PathRow({ done, count, total, labelKey }: { done: boolean; count: number; total: number; labelKey: "scenesDone" | "turnsDone" }) {
  return (
    <li className={`sa-submit__check-item ${done ? "is-done" : ""}`}>
      <StudentIcon name={done ? "check_circle" : "radio_button_unchecked"} size={18} role="decorative" filled={done} />
      <span>{Math.min(count, total)} / {total} <StudentSystemText k={labelKey} /></span>
    </li>
  );
}

/**
 * The one deliberate checkpoint between finishing a story and the
 * completion stub — turning work in is a real "hand it to the teacher"
 * gesture, not something to fire silently in the background. onSubmit
 * (owned by StudentApp) does the actual createStorySubmission +
 * markStoryLevelSubmitted work and advances the phase once it resolves;
 * this component only owns the button's pending/error state.
 */
export default function SubmitStoryPage({ topic, sceneCount, scenesRecorded, turnCount, turnsRecorded, alreadySubmitted = false, onSubmit }: SubmitStoryPageProps) {
  const [state, setState] = useState<SubmitState>("idle");
  const speakingDone = sceneCount > 0 && scenesRecorded >= sceneCount;
  const conversationDone = turnCount > 0 && turnsRecorded >= turnCount;
  // A half-done path is shown (so the counts are honest) but not submitted.
  const partialPathLeftOut = (!speakingDone && scenesRecorded > 0) || (!conversationDone && turnsRecorded > 0);

  const handleSubmit = async () => {
    setState("submitting");
    try {
      await onSubmit();
    } catch {
      setState("error");
    }
  };

  return (
    <div className="sa-page-container sa-page sa-page-container--narrow">
      <StudentPageHeader
        eyebrowKey="storySpeaking"
        context={<span lang="zh-Hant">準備提交</span>}
        titleKey="submitWork"
      />

      <StudentSection variant="panel" className="sa-submit__card">
        <p className="sa-submit__topic" lang="zh-Hant">{topic.name}</p>

        <ul className="sa-submit__checklist">
          {(speakingDone || scenesRecorded > 0 || !conversationDone) && (
            <PathRow done={speakingDone} count={scenesRecorded} total={sceneCount} labelKey="scenesDone" />
          )}
          {turnCount > 0 && (conversationDone || turnsRecorded > 0) && (
            <PathRow done={conversationDone} count={turnsRecorded} total={turnCount} labelKey="turnsDone" />
          )}
        </ul>

        {partialPathLeftOut && (
          <p className="sa-submit__note"><StudentSystemText k="onlyFinishedPathSent" /></p>
        )}
        {alreadySubmitted && (
          <p className="sa-submit__note"><StudentSystemText k="resubmitReplaces" /></p>
        )}

        {state === "error" && (
          <p className="sa-submit__error">
            <StudentSystemText k="serverSubmitError" />
          </p>
        )}

        <StudentButton
          variant="primary"
          size="lg"
          iconTrailing="send"
          disabled={state === "submitting"}
          onClick={handleSubmit}
        >
          <StudentSystemText k={state === "submitting" ? "submitting" : "submitToTeacher"} withinControl />
        </StudentButton>
      </StudentSection>
    </div>
  );
}
