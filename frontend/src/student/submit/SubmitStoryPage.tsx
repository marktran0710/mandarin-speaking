import { useState } from "react";
import type { Topic } from "../../components/content/topic-selector/types";
import StudentPageHeader from "../primitives/StudentPageHeader";
import StudentSection from "../primitives/StudentSection";
import StudentButton from "../primitives/StudentButton";
import StudentIcon from "../primitives/StudentIcon";
import "../primitives/layout.css";
import "./SubmitStoryPage.css";

type SubmitState = "idle" | "submitting" | "error";

interface SubmitStoryPageProps {
  topic: Topic;
  sceneCount: number;
  hasConversation: boolean;
  onSubmit: () => Promise<void>;
}

/**
 * The one deliberate checkpoint between finishing a story and the
 * completion stub — turning work in is a real "hand it to the teacher"
 * gesture, not something to fire silently in the background. onSubmit
 * (owned by StudentApp) does the actual createStorySubmission +
 * markStoryLevelSubmitted work and advances the phase once it resolves;
 * this component only owns the button's pending/error state.
 */
export default function SubmitStoryPage({ topic, sceneCount, hasConversation, onSubmit }: SubmitStoryPageProps) {
  const [state, setState] = useState<SubmitState>("idle");

  const handleSubmit = async () => {
    setState("submitting");
    try {
      await onSubmit();
    } catch {
      setState("error");
    }
  };

  return (
    <div className="sa-page-container sa-page-container--narrow">
      <StudentPageHeader
        eyebrowEn="Story Speaking · Ready to Submit"
        titleZh="準備提交"
        titleEn="Turn in your work"
      />

      <StudentSection variant="panel" className="sa-submit__card">
        <p className="sa-submit__topic" lang="zh-Hant">{topic.name}</p>

        <ul className="sa-submit__checklist">
          <li className="sa-submit__check-item is-done">
            <StudentIcon name="check_circle" size={18} role="decorative" filled />
            <span>{sceneCount} / {sceneCount} 幕已完成 · Scenes spoken</span>
          </li>
          {hasConversation && (
            <li className="sa-submit__check-item is-done">
              <StudentIcon name="check_circle" size={18} role="decorative" filled />
              <span>對話已完成 · Conversation finished</span>
            </li>
          )}
        </ul>

        {state === "error" && (
          <p className="sa-submit__error">
            Couldn't reach the server to notify your teacher yet — your progress is still saved on this device. Try again.
          </p>
        )}

        <StudentButton
          variant="primary"
          size="lg"
          iconTrailing="send"
          disabled={state === "submitting"}
          onClick={handleSubmit}
        >
          {state === "submitting" ? "Submitting…" : "提交給老師 Submit to Teacher"}
        </StudentButton>
      </StudentSection>
    </div>
  );
}
