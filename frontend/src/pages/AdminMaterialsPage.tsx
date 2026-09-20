import { useState } from "react";
import Icon, { type UiIconName } from "../shared/ui/Icon";
import StoryBuilderSection from "../components/teacher/StoryBuilderSection";
import TeacherImageBuilderPage from "./TeacherImageBuilderPage";
import TeacherQuizReviewPage from "./TeacherQuizReviewPage";
import "../pages/MyStoriesPage.css";
import "./TeacherDashboardPage.css";

export type AdminMaterialsTool = "builder" | "imageBuilder" | "quizReview";

const MATERIALS_TOOLS: Array<{ id: AdminMaterialsTool; icon: UiIconName; title: string; blurb: string }> = [
  {
    id: "builder",
    icon: "library",
    title: "Story Builder",
    blurb: "Write a story, set its scenes, and publish it to students.",
  },
  {
    id: "imageBuilder",
    icon: "image",
    title: "AI Image Builder",
    blurb: "Generate and attach scene images for a story you have written.",
  },
  {
    id: "quizReview",
    icon: "check",
    title: "Quiz Review",
    blurb: "Check generated quiz questions, then publish the approved set.",
  },
];

export default function AdminMaterialsPage({ initialTool }: { initialTool?: AdminMaterialsTool } = {}) {
  const [tool, setTool] = useState<AdminMaterialsTool | null>(initialTool ?? null);
  const [quizReviewJump, setQuizReviewJump] = useState<{ lessonNumber: number | null; nonce: number } | null>(null);

  if (tool) {
    return (
      <>
        <button type="button" className="tdash-back" onClick={() => setTool(null)}>
          Back to Materials
        </button>
        {tool === "builder" && (
          <StoryBuilderSection
            onGoToQuizReview={(lessonNumber) => {
              setQuizReviewJump({ lessonNumber, nonce: Date.now() });
              setTool("quizReview");
            }}
          />
        )}
        {tool === "imageBuilder" && <TeacherImageBuilderPage />}
        {tool === "quizReview" && <TeacherQuizReviewPage jumpToLesson={quizReviewJump} />}
      </>
    );
  }

  return (
    <section className="tdash-card admin-materials-card">
      <div className="tdash-card-head">
        <div>
          <p className="stories-kicker">Content operations</p>
          <h2>Materials</h2>
        </div>
      </div>
      <p className="tdash-card-note">Create and review the published story content used by students.</p>
      <div className="tdash-tool-list">
        {MATERIALS_TOOLS.map((item) => (
          <button type="button" className="tdash-tool" key={item.id} onClick={() => setTool(item.id)}>
            <Icon name={item.icon} size={20} />
            <span>
              <strong>{item.title}</strong>
              <small>{item.blurb}</small>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
