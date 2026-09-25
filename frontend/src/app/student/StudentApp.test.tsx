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
  default: ({ onFinished, onStartPractice }: { onFinished: () => void; onStartPractice?: (practice: "story-speaking" | "conversation") => void }) => (
    <div data-testid="quiz-mock">
      <button onClick={onFinished}>Finish Quiz</button>
      {onStartPractice && <>
        <button onClick={() => onStartPractice("story-speaking")}>Choose Story Speaking</button>
        <button onClick={() => onStartPractice("conversation")}>Choose Conversation</button>
      </>}
    </div>
  ),
}));
vi.mock("../../features/speaking/StorySpeakingPage", () => ({
  default: ({ onDone }: { onDone: () => void }) => (
    <div data-testid="speaking-mock">
      <button onClick={onDone}>Finish Speaking</button>
    </div>
  ),
}));
vi.mock("../../features/conversation/ConversationPage", () => ({
  default: ({ onDone }: { onDone: () => void }) => (
    <div data-testid="conversation-mock">
      <button onClick={onDone}>Finish Conversation</button>
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
    const s2 = makeTopic({ id: "s2", name: "故事二", lessonSubOrder: 2, vocabAssessment: [makeVocabAssessment("w2")] });
    recordLocalStars("s1", 3);

    render(<StudentApp studentName="Student One" topics={[s1, s2]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);

    const row1 = screen.getByText("故事一").closest("article")!;
    expect(within(row1).getByText("進行中")).toBeInTheDocument();
    expect(within(row1).getByRole("button", { name: "繼續" })).toBeInTheDocument();

    const row2 = screen.getByText("故事二").closest("article")!;
    expect(within(row2).getByText("未開啟")).toBeInTheDocument();
    expect(within(row2).queryByRole("button")).not.toBeInTheDocument();

    // Stars widget: 2 quiz-bearing stories * 3 max = 6, s1 already earned 3.
    const starsSection = screen.getByLabelText("Learning stars");
    expect(within(starsSection).getByText("3")).toBeInTheDocument();
    expect(within(starsSection).getByText(/\/ 6/)).toBeInTheDocument();
  });

  it("reflects seeded session phase flags in the active row's phase strip", () => {
    const s1 = makeTopic({ id: "s1" });
    sessionStorage.setItem(
      "studentPhaseFlags:student-1:s1",
      JSON.stringify({ vocab: true, quiz: true, speaking: false, conversation: false }),
    );

    render(<StudentApp studentName="Student One" topics={[s1]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);

    const row = screen.getByText("故事一").closest("article")!;
    const vocabPhase = within(row).getByText("生詞").closest(".sa-study__phase")!;
    const quizPhase = within(row).getByText("測驗").closest(".sa-study__phase")!;
    const speakingPhase = within(row).getByText("口語").closest(".sa-study__phase")!;
    expect(vocabPhase).toHaveClass("is-done");
    expect(quizPhase).toHaveClass("is-done");
    expect(speakingPhase).not.toHaveClass("is-done");
  });

  it("marks the vocab phase flag on a real Start Speaking click, then routes through the real Submit screen to a real Completion screen (no conversationTurns)", async () => {
    const s1 = makeTopic({ id: "s1" });
    render(<StudentApp studentName="Student One" topics={[s1]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "繼續" }));
    expect(sessionStorage.getItem("studentPhaseFlags:student-1:s1")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Start quiz/i }));
    expect(JSON.parse(sessionStorage.getItem("studentPhaseFlags:student-1:s1") ?? "{}").vocab).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Finish Quiz" }));
    expect(screen.getByTestId("speaking-mock")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Finish Speaking" }));
    expect(await screen.findByRole("button", { name: /Submit to Teacher/ })).toBeInTheDocument();
    expect(localStorage.getItem("storyLevelProgress:student-1")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Submit to Teacher/ }));

    expect(await screen.findByText("完成！")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("storyLevelProgress:student-1") ?? "{}").s1).toBe(true);
  });

  it("lets a three-star quiz choose Conversation directly, without forcing Story Speaking first", () => {
    const withConversation = makeTopic({ id: "s3", lessonSubOrder: 1, conversationTurns });
    render(<StudentApp studentName="Student One" topics={[withConversation]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "繼續" }));
    fireEvent.click(screen.getByRole("button", { name: /Start quiz/i }));
    fireEvent.click(screen.getByRole("button", { name: "Choose Conversation" }));

    expect(screen.getByTestId("conversation-mock")).toBeInTheDocument();
  });

  it("skips the quiz phase entirely for a topic with no quiz — CTA reads 'Start speaking' and jumps straight to Story Speaking", () => {
    const noQuizTopic = makeTopic({ id: "s4", vocabAssessment: [] });
    render(<StudentApp studentName="Student One" topics={[noQuizTopic]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "繼續" }));
    fireEvent.click(screen.getByRole("button", { name: /Start speaking/i }));

    expect(screen.getByTestId("speaking-mock")).toBeInTheDocument();
    expect(screen.queryByTestId("quiz-mock")).not.toBeInTheDocument();
  });

  it("gates the sidebar's phase-nav by furthest phase reached and the real quiz-stars gate", () => {
    const s1 = makeTopic({ id: "s1" });
    recordLocalStars("s1", 3);
    render(<StudentApp studentName="Student One" topics={[s1]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "繼續" }));

    // Freshly opened: quiz-complete stars make both practice choices reachable.
    expect(screen.getByRole("button", { name: /Vocab Preview/ })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: /Vocab Quiz/ })).toBeDisabled();
    const phaseNav = screen.getByRole("navigation", { name: "Lesson phase" });
    expect(within(phaseNav).getByRole("button", { name: /Story Speaking/ })).not.toBeDisabled();
    expect(within(phaseNav).getByRole("button", { name: /Conversation/ })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: /Submit/ })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /Start quiz/i }));
    expect(screen.getByRole("button", { name: /Vocab Quiz/ })).not.toBeDisabled();
    expect(within(phaseNav).getByRole("button", { name: /Story Speaking/ })).not.toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Finish Quiz" }));
    // The 3 real stars seeded above clear the star gate once the watermark also reaches it.
    expect(within(phaseNav).getByRole("button", { name: /Story Speaking/ })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: /Submit/ })).toBeDisabled();

    // Clicking a still-locked item is a no-op — the rendered body is unchanged.
    fireEvent.click(screen.getByRole("button", { name: /Submit/ }));
    expect(screen.getByTestId("speaking-mock")).toBeInTheDocument();
  });

  it("makes Placement a real, reachable section (not disabled) alongside Progress", () => {
    const s1 = makeTopic({ id: "s1" });
    render(<StudentApp studentName="Student One" topics={[s1]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);

    const placementButton = screen.getByRole("button", { name: /Placement/ });
    expect(placementButton).not.toBeDisabled();
    fireEvent.click(placementButton);
    expect(screen.getByText("Placement Test")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Progress/ }));
    expect(screen.getByText("Study Progress")).toBeInTheDocument();
  });
});
