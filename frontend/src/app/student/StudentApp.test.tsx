import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "@entities/topic";
import type { ConversationTurn } from "../../components/story-recorder/StoryRecorder";
import type { VocabAssessmentQuestion } from "@entities/vocabulary";
import { loadLocalStars, recordLocalStars } from "@entities/vocabulary";
import { loadSubmittedStoryIds, markStoryLevelSubmitted } from "../../utils/storyLevelProgress";
import { canUseDatabase } from "../../services/database";
import { getVocabularyProgression, type VocabularyProgression } from "../../services/api/quiz-analytics";
import StudentApp from "./StudentApp";

vi.mock("../../services/database", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../services/database")>(),
  canUseDatabase: vi.fn(() => false),
}));
vi.mock("../../services/api/quiz-analytics", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../services/api/quiz-analytics")>(),
  getVocabularyProgression: vi.fn(),
}));

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
  default: ({ onDone }: { onDone: () => void }) => (
    <div data-testid="conversation-mock">
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

function makeProgression(quizStars: VocabularyProgression["quizStars"]): VocabularyProgression {
  const tier = { earned: false, correctCount: 0, totalQuestions: 0, requiredCorrect: 0 };
  return {
    storyId: "s1", quizStars, requiredStars: 3,
    tiers: { tier1: tier, tier2: tier, tier3: tier },
    speakingUnlocked: quizStars === 3,
    conversationAvailable: false,
    conversationUnlocked: quizStars === 3,
  };
}

describe("StudentApp", () => {
  beforeEach(() => {
    vi.mocked(canUseDatabase).mockReturnValue(false);
    vi.mocked(getVocabularyProgression).mockReset();
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
    expect(sessionStorage.getItem("studentPhaseFlags:student-1:s1")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "開始測驗" }));
    expect(
      JSON.parse(
        sessionStorage.getItem("studentPhaseFlags:student-1:s1") ?? "{}",
      ).vocab,
    ).toBe(true);

    recordLocalStars("s1", 3);
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
    recordLocalStars("s3", 3);
    fireEvent.click(
      screen.getByRole("button", { name: "選擇對話" }),
    );

    expect(screen.getByTestId("conversation-mock")).toBeInTheDocument();
    const phaseNav = screen.getByRole("navigation", { name: "課程階段" });
    expect(within(phaseNav).getByText("口語練習").closest("button")).not.toBeDisabled();
    expect(within(phaseNav).getByText("對話練習").closest("button")).not.toBeDisabled();
  });

  it.each([false, true])("skips the quiz phase entirely for a topic with no quiz (database available: %s)", (databaseAvailable) => {
    vi.mocked(canUseDatabase).mockReturnValue(databaseAvailable);
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
    const phaseNav = screen.getByRole("navigation", { name: "課程階段" });
    expect(within(phaseNav).getByText("口語練習").closest("button")).not.toBeDisabled();
    expect(within(phaseNav).getByText("對話練習").closest("button")).not.toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "開始口說練習" }));

    expect(screen.getByTestId("speaking-mock")).toBeInTheDocument();
    expect(screen.queryByTestId("quiz-mock")).not.toBeInTheDocument();
    expect(getVocabularyProgression).not.toHaveBeenCalled();
  });

  it("opens both practices at three stars and keeps Submit locked until either practice finishes", () => {
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

    fireEvent.click(
      within(
        screen
          .getByText("故事一", { selector: ".study-row-title" })
          .closest("article")!,
      ).getByRole("button", { name: /繼續/ }),
    );

    // Reopening a three-star lesson keeps both practice paths available;
    // the learner may still review the vocabulary quiz.
    const phaseNav = screen.getByRole("navigation", { name: "課程階段" });
    const phaseButton = (label: string) => within(phaseNav).getByText(label).closest("button")!;
    expect(
      phaseButton("生詞預習"),
    ).not.toBeDisabled();
    expect(phaseButton("詞彙練習")).toBeDisabled();
    expect(
      phaseButton("口語練習"),
    ).not.toBeDisabled();
    expect(
      phaseButton("對話練習"),
    ).not.toBeDisabled();
    expect(phaseButton("提交")).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "開始測驗" }));
    expect(
      phaseButton("詞彙練習"),
    ).not.toBeDisabled();
    expect(
      phaseButton("口語練習"),
    ).not.toBeDisabled();
    expect(
      phaseButton("對話練習"),
    ).not.toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "完成測驗" }));
    // The three earned stars keep both practice modes available.
    expect(
      phaseButton("口語練習"),
    ).not.toBeDisabled();
    expect(
      phaseButton("對話練習"),
    ).not.toBeDisabled();
    expect(phaseButton("提交")).toBeDisabled();

    // Completing either practice branch is the point at which Submit opens.
    fireEvent.click(screen.getByRole("button", { name: "完成口說" }));
    expect(
      phaseButton("提交"),
    ).not.toBeDisabled();
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
  });

  it.each([0, 1, 2, 3] as const)("keeps both practice paths in the same lock state at %i stars, including stories without conversation content", (stars) => {
    const topic = makeTopic({ id: "shared-gate" });
    if (stars !== 0) recordLocalStars(topic.id, stars);
    render(
      <StudentApp studentName="Student One" topics={[topic]} onAddRecord={vi.fn()} onLogout={vi.fn()} />,
    );
    fireEvent.click(within(screen.getAllByRole("article")[0]).getByRole("button"));

    const phaseNav = screen.getByRole("navigation", { name: "課程階段" });
    const speaking = within(phaseNav).getByText("口語練習").closest("button")!;
    const conversation = within(phaseNav).getByText("對話練習").closest("button")!;
    expect(speaking.disabled).toBe(stars < 3);
    expect(conversation.disabled).toBe(stars < 3);
    fireEvent.click(conversation);
    expect(Boolean(screen.queryByTestId("conversation-mock"))).toBe(stars === 3);
  });

  it("keeps both practices locked when a quiz callback has fired without three earned stars, even after reaching Submit", () => {
    const topic = makeTopic({ id: "incomplete-quiz", conversationTurns });
    recordLocalStars(topic.id, 2);
    render(
      <StudentApp studentName="Student One" topics={[topic]} onAddRecord={vi.fn()} onLogout={vi.fn()} />,
    );
    fireEvent.click(within(screen.getAllByRole("article")[0]).getByRole("button"));
    fireEvent.click(screen.getByRole("button", { name: "開始測驗" }));
    fireEvent.click(screen.getByRole("button", { name: "完成測驗" }));
    fireEvent.click(screen.getByRole("button", { name: "完成口說" }));

    const phaseNav = screen.getByRole("navigation", { name: "課程階段" });
    for (const label of ["口語練習", "對話練習"]) {
      const button = within(phaseNav).getByText(label).closest("button")!;
      expect(button).toBeDisabled();
      fireEvent.click(button);
    }
    expect(screen.getByRole("button", { name: "提交給老師" })).toBeInTheDocument();
    expect(screen.queryByTestId("conversation-mock")).not.toBeInTheDocument();
  });

  it.each([0, 2, 3] as const)("applies the server's %i-star result to both practice modes", async (stars) => {
    vi.mocked(canUseDatabase).mockReturnValue(true);
    vi.mocked(getVocabularyProgression).mockResolvedValue(makeProgression(stars));
    // The server must override a stale local result, in either direction.
    if (stars < 3) recordLocalStars("s1", 3);
    render(
      <StudentApp studentName="Student One" topics={[makeTopic({ conversationTurns })]} onAddRecord={vi.fn()} onLogout={vi.fn()} />,
    );
    fireEvent.click(within(screen.getAllByRole("article")[0]).getByRole("button"));

    await waitFor(() => {
      expect(getVocabularyProgression).toHaveBeenCalledWith("s1", "student-1");
      const phaseNav = screen.getByRole("navigation", { name: "課程階段" });
      expect(within(phaseNav).getByText("口語練習").closest("button")!.disabled).toBe(stars < 3);
      expect(within(phaseNav).getByText("對話練習").closest("button")!.disabled).toBe(stars < 3);
    });
  });

  it("ignores an older progression response after the quiz completes and refreshes the shared gate", async () => {
    vi.mocked(canUseDatabase).mockReturnValue(true);
    let resolveInitial!: (progression: VocabularyProgression) => void;
    vi.mocked(getVocabularyProgression)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveInitial = resolve; }))
      .mockResolvedValue(makeProgression(3));
    render(
      <StudentApp studentName="Student One" topics={[makeTopic({ conversationTurns })]} onAddRecord={vi.fn()} onLogout={vi.fn()} />,
    );
    fireEvent.click(within(screen.getAllByRole("article")[0]).getByRole("button"));
    fireEvent.click(screen.getByRole("button", { name: "開始測驗" }));
    recordLocalStars("s1", 3);
    fireEvent.click(screen.getByRole("button", { name: "選擇對話" }));
    await waitFor(() => expect(getVocabularyProgression).toHaveBeenCalledTimes(3));
    await act(async () => { resolveInitial(makeProgression(2)); });

    const phaseNav = screen.getByRole("navigation", { name: "課程階段" });
    expect(within(phaseNav).getByText("口語練習").closest("button")).not.toBeDisabled();
    expect(within(phaseNav).getByText("對話練習").closest("button")).not.toBeDisabled();
  });

  it("revokes cached completion and locks the next lesson when quiz evidence is deleted", async () => {
    vi.mocked(canUseDatabase).mockReturnValue(true);
    vi.mocked(getVocabularyProgression).mockImplementation(async (storyId) => ({ ...makeProgression(0), storyId }));
    recordLocalStars("s1", 3);
    markStoryLevelSubmitted("s1");
    const topics = [makeTopic({ id: "s1", lessonSubOrder: 1 }), makeTopic({ id: "s2", name: "故事二", lessonSubOrder: 2 })];
    render(<StudentApp studentName="Student One" topics={topics} onAddRecord={vi.fn()} onLogout={vi.fn()} />);

    await waitFor(() => expect(loadLocalStars("s1")).toBe(0));
    expect(loadSubmittedStoryIds().has("s1")).toBe(false);
    const secondRow = screen.getByText("故事二", { selector: ".study-row-title" }).closest("article")!;
    expect(within(secondRow).queryByRole("button")).not.toBeInTheDocument();
    fireEvent.click(within(screen.getAllByRole("article")[0]).getByRole("button"));
    const phaseNav = screen.getByRole("navigation", { name: "課程階段" });
    await waitFor(() => expect(within(phaseNav).getByText("口語練習").closest("button")).toBeDisabled());
    expect(within(phaseNav).getByText("對話練習").closest("button")).toBeDisabled();
  });

  it("keeps both practice modes locked while the server is pending or unavailable", async () => {
    vi.mocked(canUseDatabase).mockReturnValue(true);
    vi.mocked(getVocabularyProgression).mockRejectedValue(new Error("Unavailable"));
    recordLocalStars("s1", 3);
    render(<StudentApp studentName="Student One" topics={[makeTopic({ conversationTurns })]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);
    fireEvent.click(within(screen.getAllByRole("article")[0]).getByRole("button"));
    const phaseNav = screen.getByRole("navigation", { name: "課程階段" });
    expect(within(phaseNav).getByText("口語練習").closest("button")).toBeDisabled();
    await act(async () => {});
    expect(within(phaseNav).getByText("口語練習").closest("button")).toBeDisabled();
    expect(within(phaseNav).getByText("對話練習").closest("button")).toBeDisabled();
  });

  it("records the practice branch chosen from the unlocked sidebar before Submit", () => {
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

    fireEvent.click(
      within(
        screen.getAllByRole("article")[0],
      ).getByRole("button", { name: /繼續/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "開始測驗" }));
    fireEvent.click(screen.getByRole("button", { name: "完成測驗" }));
    fireEvent.click(screen.getByRole("button", { name: /對話練習/ }));
    fireEvent.click(screen.getByRole("button", { name: "完成對話" }));

    expect(screen.getByText(/對話已完成/)).toBeInTheDocument();
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
