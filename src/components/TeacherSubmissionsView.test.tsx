import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { updateSubmissionReview, type StorySubmission } from "../services/database";
import TeacherSubmissionsView from "./TeacherSubmissionsView";

vi.mock("../services/database", () => ({
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

  it("narrows the list with search and student filters", async () => {
    const user = userEvent.setup();

    render(<TeacherSubmissionsView submissions={submissions} onReviewUpdate={vi.fn()} />);

    await user.type(screen.getByRole("searchbox", { name: "Search submissions" }), "garden");
    expect(screen.getByText("Garden Adventure")).toBeInTheDocument();
    expect(screen.queryByText("Mountain Walk")).not.toBeInTheDocument();

    await user.clear(screen.getByRole("searchbox", { name: "Search submissions" }));
    await user.selectOptions(screen.getByLabelText("Student"), "Wei");
    expect(screen.getByText("Mountain Walk")).toBeInTheDocument();
    expect(screen.queryByText("Garden Adventure")).not.toBeInTheDocument();
  });
});
