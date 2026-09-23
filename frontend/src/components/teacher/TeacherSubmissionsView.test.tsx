import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { updateSubmissionReview, type StorySubmission } from "../../services/database";
import TeacherSubmissionsView from "./TeacherSubmissionsView";

vi.mock("../../services/database", () => ({
  updateSubmissionReview: vi.fn(),
}));

const submissions: StorySubmission[] = [
  {
    id: "submission-garden",
    storyId: "story-garden",
    storyTitle: "Garden Adventure",
    studentName: "Mei",
    submittedAt: "2026-07-30T09:00:00Z",
    reviewStatus: "pending",
    scenes: [{
      sceneIndex: 0,
      imageUrl: "",
      transcription: "A garden story.",
      vocabUsed: [],
      vocabMissing: [],
      vocabScore: 90,
      toneAccuracy: 85,
      pronScore: 88,
    }],
  },
  {
    id: "submission-mountain",
    storyId: "story-mountain",
    storyTitle: "Mountain Walk",
    studentName: "Wei",
    submittedAt: "2026-07-29T09:00:00Z",
    reviewStatus: "reviewed",
    scenes: [{
      sceneIndex: 0,
      imageUrl: "",
      transcription: "A mountain story.",
      vocabUsed: [],
      vocabMissing: [],
      vocabScore: 82,
      toneAccuracy: 80,
      pronScore: 84,
    }],
  },
];

describe("TeacherSubmissionsView", () => {
  beforeEach(() => {
    vi.mocked(updateSubmissionReview).mockReset();
  });

  it("marks a pending submission reviewed and updates its badge", async () => {
    const user = userEvent.setup();
    const onReviewUpdate = vi.fn();
    const pendingSubmission = submissions[0];
    const reviewedSubmission = { ...pendingSubmission, reviewStatus: "reviewed" as const };
    vi.mocked(updateSubmissionReview).mockResolvedValue(reviewedSubmission);

    render(
      <TeacherSubmissionsView
        submissions={[pendingSubmission]}
        onReviewUpdate={onReviewUpdate}
      />,
    );

    expect(screen.getByText("Pending review")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mark reviewed" }));

    await waitFor(() =>
      expect(updateSubmissionReview).toHaveBeenCalledWith(
        "submission-garden",
        "reviewed",
        null,
      ),
    );
    expect(screen.getByText("Reviewed")).toBeInTheDocument();
    expect(onReviewUpdate).toHaveBeenCalledWith(reviewedSubmission);
  });

  it("shows the student's self-eval next to the scene score, only for scenes that have it, once expanded", async () => {
    const user = userEvent.setup();
    const withSelfEval: StorySubmission = {
      ...submissions[0],
      scenes: [
        { ...submissions[0].scenes[0], selfEvalContent: "good", selfEvalPronunciation: "ok" },
        { ...submissions[0].scenes[0], sceneIndex: 1 },
      ],
    };

    render(<TeacherSubmissionsView submissions={[withSelfEval]} onReviewUpdate={vi.fn()} />);

    // Scene detail is collapsed until a teacher asks to see it.
    expect(screen.queryByText(/Self-eval:/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Details" }));

    expect(screen.getByText(/Self-eval:.*meaning.*pronunciation/)).toBeInTheDocument();
    expect(screen.getAllByText(/Self-eval:/)).toHaveLength(1);
  });

  it("collapses scene detail behind a Details toggle and shows an overall score up front", async () => {
    const user = userEvent.setup();

    render(<TeacherSubmissionsView submissions={[submissions[0]]} onReviewUpdate={vi.fn()} />);

    // (90 + 85 + 88) / 3 = 87.67 -> 88
    expect(screen.getByText("88%")).toBeInTheDocument();
    expect(screen.queryByText("A garden story.")).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Details" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);

    expect(screen.getByText(/A garden story\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide" })).toHaveAttribute("aria-expanded", "true");
  });

  it("labels conversation turns as distinct exchanges instead of colliding on the same scene number", async () => {
    // Every turn in a Conversation Practice submission shares one
    // sceneIndex (the story's single selected image, not a per-turn
    // counter) - Epic 11 regression: labeling/keying by sceneIndex alone
    // used to render every exchange as "Scene 1".
    const user = userEvent.setup();
    const conversationSubmission: StorySubmission = {
      ...submissions[0],
      scenes: [
        { ...submissions[0].scenes[0], transcription: "你好！", conversationId: "conversation:story-garden", turnId: "student-1", turnIndex: 1 },
        { ...submissions[0].scenes[0], transcription: "我很好。", conversationId: "conversation:story-garden", turnId: "student-2", turnIndex: 3 },
      ],
    };

    render(<TeacherSubmissionsView submissions={[conversationSubmission]} onReviewUpdate={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Details" }));

    expect(screen.getByText("Exchange 1")).toBeInTheDocument();
    expect(screen.getByText("Exchange 2")).toBeInTheDocument();
    expect(screen.queryByText(/^Scene \d/)).not.toBeInTheDocument();
    expect(screen.getByText("你好！", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("我很好。", { exact: false })).toBeInTheDocument();
  });

  it("still labels a legacy (non-conversation) submission by scene number", async () => {
    const user = userEvent.setup();
    render(<TeacherSubmissionsView submissions={[submissions[0]]} onReviewUpdate={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Details" }));
    expect(screen.getByText("Scene 1")).toBeInTheDocument();
  });

  it("narrows the list with the student filter", async () => {
    const user = userEvent.setup();

    render(<TeacherSubmissionsView submissions={submissions} onReviewUpdate={vi.fn()} />);

    await user.selectOptions(screen.getByLabelText("Student"), "Wei");
    expect(screen.getByText("Mountain Walk")).toBeInTheDocument();
    expect(screen.queryByText("Garden Adventure")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Student"), "all");
    expect(screen.getByText("Garden Adventure")).toBeInTheDocument();
    expect(screen.getByText("Mountain Walk")).toBeInTheDocument();
  });
});
