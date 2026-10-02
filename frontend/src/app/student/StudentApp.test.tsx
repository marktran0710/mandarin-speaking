import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "@entities/topic";
import type { ConversationTurn } from "../../components/story-recorder/StoryRecorder";
import type { VocabAssessmentQuestion } from "@entities/vocabulary";
import { recordLocalStars } from "@entities/vocabulary";
import StudentApp from "./StudentApp";

vi.mock("../../utils/studentSession", () => ({
  getStudentId: () => "student-1",
  getStudentScopeKey: () => "student-1",
  getStudentName: () => "Student One",
  isAdminSession: () => false,
}));

vi.mock("../../features/vocabulary/VocabularyQuizPage", () => ({
  default: ({
    onFinished,
    onStartPractice,
  }: {
    onFinished: () => void;
    onStartPractice?: (practice: "story-speaking" | "conversation") => void;
  }) => (
    <div data-testid="quiz-mock">
      <button onClick={onFinished}>完成測驗</button>
      {onStartPractice && (
        <>
          <button onClick={() => onStartPractice("story-speaking")}>
            選擇故事口說
          </button>
          <button onClick={() => onStartPractice("conversation")}>
            選擇對話
          </button>
        </>
      )}
    </div>
  ),
}));
vi.mock("../../features/speaking/StorySpeakingPage", () => ({
  default: ({ onDone }: { onDone: () => void }) => (
    <div data-testid="speaking-mock">
      <button onClick={onDone}>完成口說</button>
    </div>
  ),
}));
vi.mock("../../features/conversation/ConversationPage", () => ({
  default: ({ onDone, onChooseSolo }: { onDone: () => void; onChooseSolo: () => void }) => (
    <div data-testid="conversation-mock">
      <button onClick={onChooseSolo}>選擇自己說</button>
      <button onClick={onDone}>完成對話</button>
    </div>
  ),
}));

function makeVocabAssessment(wordId: string): VocabAssessmentQuestion {
  return {
    questionId: `${wordId}-q1`,
    wordId,
    targetWord: wordId,
    pinyin: "pin1",
    pos: "n",
    simpleEnglishMeaning: "meaning",
    level: "easy",
    difficultyWeight: 1,
    questionType: "basic_meaning_mcq",
    answerFormat: "single_choice",
    prompt: "prompt",
    options: ["a", "b"],
    correctAnswer: "a",
    acceptedAnswers: ["a"],
    explanation: "expl",
  };
}

function makeTopic(overrides: Partial<Topic> = {}): Topic {
  return {
    id: "s1",
    name: "故事一",
    description: "desc",
    skillFocus: "conversation",
    images: ["img.png"],
    vocabulary: {},
    lessonNumber: 5,
    lessonSubOrder: 1,
    vocabAssessment: [makeVocabAssessment("w1")],
    ...overrides,
  };
}

const conversationTurns: ConversationTurn[] = [
  { id: "t0", speaker: "system", text: "你好嗎？" },
  { id: "t1", speaker: "student", text: "我很好", targetText: "我很好" },
];

describe("StudentApp", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("computes lock status and Stars from real gate utils, and the second story is locked until the first finishes", () => {
    const s1 = makeTopic({ id: "s1", lessonSubOrder: 1 });
    const s2 = makeTopic({
      id: "s2",
      name: "故事二",
      lessonSubOrder: 2,
      vocabAssessment: [makeVocabAssessment("w2")],
    });
    recordLocalStars("s1", 3);

    render(
      <StudentApp
        studentName="Student One"
        topics={[s1, s2]}
        onAddRecord={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    const row1 = screen
      .getByText("故事一", { selector: ".study-row-title" })
      .closest("article")!;
    expect(
      within(row1).getByRole("button", { name: /繼續/ }),
    ).toBeInTheDocument();

    const row2 = screen
      .getByText("故事二", { selector: ".study-row-title" })
      .closest("article")!;
    expect(within(row2).getByText(/尚未開放/)).toBeInTheDocument();
    expect(within(row2).queryByRole("button")).not.toBeInTheDocument();

    // Stars widget: 2 quiz-bearing stories * 3 max = 6, s1 already earned 3.
    const starsSection = screen.getByLabelText("學習星星");
    expect(within(starsSection).getByText("3")).toBeInTheDocument();
    expect(within(starsSection).getByText(/\/ 6/)).toBeInTheDocument();
  });

  it("reflects seeded session phase flags in the active row's phase strip", () => {
    const s1 = makeTopic({ id: "s1" });
    sessionStorage.setItem(
      "studentPhaseFlags:student-1:s1",
      JSON.stringify({
        vocab: true,
        quiz: true,
        speaking: false,
        conversation: false,
      }),
    );

    render(
      <StudentApp
        studentName="Student One"
        topics={[s1]}
        onAddRecord={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    const row = screen
      .getByText("故事一", { selector: ".study-row-title" })
      .closest("article")!;
    const vocabPhase = within(row)
      .getByText("詞彙")
      .closest(".study-phases > span")!;
    const quizPhase = within(row)
      .getByText("測驗")
      .closest(".study-phases > span")!;
    const speakingPhase = within(row)
      .getByText("口語")
      .closest(".study-phases > span")!;
    expect(vocabPhase).toHaveClass("is-done");
    expect(quizPhase).toHaveClass("is-done");
    expect(speakingPhase).not.toHaveClass("is-done");
  });

  it("marks the vocab phase flag on a real Start Speaking click, then routes through the real Submit screen to a real Completion screen (no conversationTurns)", async () => {
    const s1 = makeTopic({ id: "s1" });
    render(
      <StudentApp
        studentName="Student One"
        topics={[s1]}
        onAddRecord={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    fireEvent.click(
      within(
        screen
          .getByText("故事一", { selector: ".study-row-title" })
          .closest("article")!,
      ).getByRole("button", { name: /繼續/ }),
    );
    expect(localStorage.getItem("studentPhaseFlags:student-1:s1")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "開始測驗" }));
    expect(
      JSON.parse(
        localStorage.getItem("studentPhaseFlags:student-1:s1") ?? "{}",
      ).vocab,
    ).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "完成測驗" }));
    expect(screen.getByTestId("speaking-mock")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "完成口說" }));
    expect(
      await screen.findByRole("button", { name: "提交給老師" }),
    ).toBeInTheDocument();
    expect(localStorage.getItem("storyLevelProgress:student-1")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "提交給老師" }));

    expect(await screen.findByText("完成！")).toBeInTheDocument();
    expect(
      JSON.parse(localStorage.getItem("storyLevelProgress:student-1") ?? "{}")
        .s1,
    ).toBe(true);
  });

  it("lets a three-star quiz choose Conversation directly, without forcing Story Speaking first", () => {
    const withConversation = makeTopic({
      id: "s3",
      lessonSubOrder: 1,
      conversationTurns,
    });
    render(
      <StudentApp
        studentName="Student One"
        topics={[withConversation]}
        onAddRecord={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    fireEvent.click(
      within(
        screen
          .getByText("故事一", { selector: ".study-row-title" })
          .closest("article")!,
      ).getByRole("button", { name: /繼續/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "開始測驗" }));
    fireEvent.click(
      screen.getByRole("button", { name: "選擇對話" }),
    );

    expect(screen.getByTestId("conversation-mock")).toBeInTheDocument();
  });

  it("skips the quiz phase entirely for a topic with no quiz — CTA reads 'Start speaking' and jumps straight to Story Speaking", () => {
    const noQuizTopic = makeTopic({ id: "s4", vocabAssessment: [] });
    render(
      <StudentApp
        studentName="Student One"
        topics={[noQuizTopic]}
        onAddRecord={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    fireEvent.click(
      within(
        screen
          .getByText("故事一", { selector: ".study-row-title" })
          .closest("article")!,
      ).getByRole("button", { name: /繼續/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "開始口說練習" }));

    expect(screen.getByTestId("speaking-mock")).toBeInTheDocument();
    expect(screen.queryByTestId("quiz-mock")).not.toBeInTheDocument();
  });

  it("keeps vocabulary preview required even when quiz stars were saved", () => {
    const s1 = makeTopic({ id: "s1", conversationTurns });
    recordLocalStars("s1", 3);
    render(
      <StudentApp
        studentName="Student One"
        topics={[s1]}
        onAddRecord={vi.fn()}
        onLogout={vi.fn()}
      />,
    );
    fireEvent.click(screen.getAllByRole("article")[0].querySelector("button") as HTMLElement);

    expect(screen.queryByTestId("speaking-mock")).not.toBeInTheDocument();
    expect(screen.queryByTestId("quiz-mock")).not.toBeInTheDocument();
    const phaseNav = screen.getAllByRole("navigation").find((node) => node.querySelector('[data-phase="vocab-quiz"]'));
    expect(phaseNav?.querySelector('[data-phase="vocab-quiz"]')).toHaveAttribute("aria-disabled", "true");
  });

  it("keeps both practice paths locked until the three quiz rounds are finished", () => {
    const s1 = makeTopic({ id: "s1", conversationTurns });
    localStorage.setItem("studentPhaseFlags:student-1:s1", JSON.stringify({ vocab: true }));
    render(
      <StudentApp
        studentName="Student One"
        topics={[s1]}
        onAddRecord={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    fireEvent.click(
      within(screen.getAllByRole("article")[0]).getByRole("button"),
    );
    // The preview is done, so the lesson resumes at the quiz.
    expect(screen.getByTestId("quiz-mock")).toBeInTheDocument();
    const phaseNav = screen.getByRole("navigation", { name: "課程階段" });
    const phaseButton = (label: string) => within(phaseNav).getByText(label).closest("button")!;
    expect(phaseButton("口語練習")).toHaveAttribute("aria-disabled", "true");
    expect(phaseButton("對話練習")).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(phaseButton("對話練習"));
    expect(within(phaseNav).getByRole("status")).toHaveTextContent("做完三輪詞彙練習後解鎖");
    expect(screen.getByTestId("quiz-mock")).toBeInTheDocument();
  });

  it("reopens lesson 5-1 with both practice paths available after three stars", () => {
    const fiveOne = makeTopic({
      id: "story-5-1",
      name: "Lesson 5-1",
      lessonNumber: 5,
      lessonSubOrder: 1,
      conversationTurns,
    });
    recordLocalStars("story-5-1", 3);
    sessionStorage.setItem("studentPhaseFlags:student-1:story-5-1", JSON.stringify({ vocab: true }));

    render(
      <StudentApp
        studentName="Student One"
        topics={[fiveOne]}
        onAddRecord={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    fireEvent.click(
      within(screen.getByText("Lesson 5-1", { selector: ".study-row-title" }).closest("article")!)
        .getByRole("button"),
    );

    const phaseNav = screen.getByRole("navigation", { name: "課程階段" });
    const phaseButton = (label: string) => within(phaseNav).getByText(label).closest("button")!;
    expect(phaseButton("口語練習")).not.toBeDisabled();
    expect(phaseButton("對話練習")).not.toBeDisabled();

    fireEvent.click(phaseButton("口語練習"));
    expect(screen.getByTestId("speaking-mock")).toBeInTheDocument();

    fireEvent.click(phaseButton("對話練習"));
    expect(screen.getByTestId("conversation-mock")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "選擇自己說" }));
    expect(screen.getByTestId("speaking-mock")).toBeInTheDocument();
  });

  it("records the practice branch chosen from the unlocked sidebar before Submit", async () => {
    const s1 = makeTopic({ id: "s1", conversationTurns });
    recordLocalStars("s1", 3);
    sessionStorage.setItem("studentPhaseFlags:student-1:s1", JSON.stringify({ vocab: true }));
    render(
      <StudentApp
        studentName="Student One"
        topics={[s1]}
        onAddRecord={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    fireEvent.click(
      within(
        screen.getAllByRole("article")[0],
      ).getByRole("button", { name: /繼續/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: /對話練習/ }));
    fireEvent.click(screen.getByRole("button", { name: "完成對話" }));

    expect(screen.getByText(/對話已完成/)).toBeInTheDocument();
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "提交給老師" }));
    expect(await screen.findByText("完成！")).toBeInTheDocument();
    expect(screen.getByText("0 / 1 場景")).toBeInTheDocument();
    expect(screen.getByText("1 / 1 句對話")).toBeInTheDocument();
  });

  it("makes Placement a real, reachable section (not disabled) alongside Progress", () => {
    const s1 = makeTopic({ id: "s1" });
    render(
      <StudentApp
        studentName="Student One"
        topics={[s1]}
        onAddRecord={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    const placementButton = screen.getByRole("button", { name: /入門測驗/ });
    expect(placementButton).not.toBeDisabled();
    fireEvent.click(placementButton);
    expect(screen.getAllByText("入門測驗").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /進度/ }));
    expect(screen.getByText("學習進度")).toBeInTheDocument();
  });
});
