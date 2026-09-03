import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import StoryRecorder, { practiceSceneIndicesFor } from "./StoryRecorder";
import {
  TEST_BACKEND_URL,
  activeRecognition,
  activeRecorder,
  buildAnalyzeResponse,
  cleanupStoryRecorderTestEnvironment,
  completeVocabQuiz,
  jsonResponse,
  mockBackendAnalyze,
  resetStoryRecorderTestEnvironment,
  topic,
  topicWithVocabDetails,
  topicWithQuizVocab,
} from "./StoryRecorder.test.helpers";

describe("StoryRecorder student prototype", () => {
  beforeEach(resetStoryRecorderTestEnvironment);
  afterEach(cleanupStoryRecorderTestEnvironment);
  describe("pilot mode hides the Stable/Experimental selector (PART 1)", () => {
    afterEach(() => {
      window.history.pushState({}, "", "/");
    });

    it.skip("shows the analysis-version selector by default (non-pilot, ordinary use)", async () => {
      const user = userEvent.setup();
      render(
        <StoryRecorder
          topic={topic}
          selectedImage={topic.images[0]}
          selectedImageIndex={0}
          onImageSelect={vi.fn()}
          onImageChange={vi.fn()}
          onAddRecord={vi.fn()}
      />,
      );
      await user.click(screen.getByRole("tab", { name: /Speaking/ }));
      await user.click(screen.getByText("Recording options"));
      expect(screen.getByRole("group", { name: "Analysis version" })).toBeInTheDocument();
    });

    it("hides the analysis-version selector for a pilot student session", async () => {
      window.history.pushState({}, "", "/?pilot=1");
      const user = userEvent.setup();
      render(
        <StoryRecorder
          topic={topic}
          selectedImage={topic.images[0]}
          selectedImageIndex={0}
          onImageSelect={vi.fn()}
          onImageChange={vi.fn()}
          onAddRecord={vi.fn()}
      />,
      );
      await user.click(screen.getByRole("tab", { name: /Speaking/ }));
      await user.click(screen.getByText("Recording options"));
      expect(screen.queryByRole("group", { name: "Analysis version" })).not.toBeInTheDocument();
      expect(screen.queryByText(/Experimental V2/)).not.toBeInTheDocument();
    });

    it.skip("still shows the analysis-version selector for the admin backdoor even in pilot mode", async () => {
      window.history.pushState({}, "", "/?pilot=1");
      localStorage.setItem(
        "session",
        JSON.stringify({ role: "student", name: "admin", signedInAt: new Date().toISOString() }),
      );
      const user = userEvent.setup();
      render(
        <StoryRecorder
          topic={topic}
          selectedImage={topic.images[0]}
          selectedImageIndex={0}
          onImageSelect={vi.fn()}
          onImageChange={vi.fn()}
          onAddRecord={vi.fn()}
      />,
      );
      await user.click(screen.getByRole("tab", { name: /Speaking/ }));
      await user.click(screen.getByText("Recording options"));
      expect(screen.getByRole("group", { name: "Analysis version" })).toBeInTheDocument();
    });
  });

  it("shows the sorting challenge when enableSorting is true and allows skipping it", async () => {
    const onAddRecord = vi.fn();
    const user = userEvent.setup();

    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={onAddRecord}
        enableSorting={true}
      />,
    );

    // Verify sorting challenge is shown
    expect(screen.getByText("Put the Story in Order")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Record your story" })).not.toBeInTheDocument();

    // Verify prompts are rendered as hints
    expect(screen.getByText("First prompt")).toBeInTheDocument();
    expect(screen.getByText("Second prompt")).toBeInTheDocument();

    // Click Skip to unlock standard UI
    await user.click(screen.getByRole("button", { name: /Skip/ }));

    // Verify it unlocks the standard recording UI — scene 0 has vocabulary,
    // so practice lands on the Vocabulary step first, then jump to Speaking.
    expect(screen.queryByText("Put the Story in Order")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    expect(screen.getByRole("region", { name: "Record your story" })).toBeInTheDocument();
  });

  it("requires finishing the vocabulary quiz once before Practice Speaking unlocks, then remembers it's done", async () => {
    const user = userEvent.setup();

    const { unmount } = render(
      <StoryRecorder
        topic={topicWithQuizVocab}
        selectedImage={topicWithQuizVocab.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
        enableOverview={true}
      />,
    );

    // Lands on the choice screen first, not straight into practice.
    expect(screen.getByText("Your Challenge")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Vocabulary quiz" })).not.toBeInTheDocument();

    // Vocabulary is available (this topic has translated words), but
    // Speaking starts locked until the quiz has been completed once.
    const vocabChoice = screen.getByRole("button", { name: /Vocabulary Quiz/ });
    const speakingChoice = screen.getByRole("button", { name: /Speaking Practice/ });
    expect(vocabChoice).toBeEnabled();
    expect(speakingChoice).toBeDisabled();

    // Picking "Practice Vocabulary" goes to the quiz — never a skip button,
    // in any mode, whether or not it's been completed before.
    await user.click(vocabChoice);
    expect(screen.getByRole("region", { name: "Vocabulary quiz" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Skip/ })).not.toBeInTheDocument();

    // The story session header remains the way out of the lesson itself;
    // the quiz no longer duplicates that navigation inside its surface.
    expect(screen.queryByRole("button", { name: /Back to activities/ })).not.toBeInTheDocument();

    // Complete the quiz ladder from the mode-select screen.
    await completeVocabQuiz(user);

    // Landed in practice directly (quiz auto-advances on completion), with
    // the scene vocabulary table visible.
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();

    // Simulate a reload of the same session: it resumes the last active
    // phase (practice) instead of dropping back to the choice screen —
    // the scene vocabulary table is visible immediately, no re-click
    // needed. Speaking's unlock still holds too (completion was persisted).
    unmount();
    render(
      <StoryRecorder
        topic={topicWithQuizVocab}
        selectedImage={topicWithQuizVocab.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
        enableOverview={true}
      />,
    );
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();

    // This used to go on to click back to the choice screen via the phase
    // nav's "Overview" step, re-enter the quiz, and re-check both the
    // unlock and the missing skip button there. That step was removed (the
    // whole Prepare/Speak/Feedback stepper was, at the user's request), and
    // nothing replaced its "return to the choice screen from mid-practice"
    // capability — this is a real, product-level regression, not just a
    // test gap, flagged to the user rather than silently dropped here.
  });

  it("disables the vocabulary quiz choice when a story has no translated words", () => {
    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
        enableOverview={true}
      />,
    );

    expect(screen.getByRole("button", { name: /Vocabulary Quiz/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Speaking Practice/ })).toBeEnabled();
  });

  it("shows the scene vocabulary as a read-only table with pos/translation, no status before analysis", async () => {
    const user = userEvent.setup();
    render(
      <StoryRecorder
        topic={topicWithVocabDetails}
        selectedImage={topicWithVocabDetails.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    // This topic now has 1 translated word, enough to trigger the vocab
    // quiz gate — it's mandatory the first time, so answer through it to
    // reach practice, which is what this test actually covers.
    await completeVocabQuiz(user);

    const table = screen.getByRole("table", { name: "Scene vocabulary" });
    expect(within(table).getByText("market")).toBeInTheDocument();
    expect(within(table).getByText("shìchǎng")).toBeInTheDocument();
    expect(within(table).getByText("N")).toBeInTheDocument();
    expect(within(table).getByText("marketplace")).toBeInTheDocument();

    // "help" has no translation supplied — cell should just be empty, not crash.
    expect(within(table).getByText("help")).toBeInTheDocument();
    expect(within(table).getByText("bāngmáng")).toBeInTheDocument();
    expect(within(table).getByText("V")).toBeInTheDocument();

    // No recording analyzed yet: no used/missing status tint or tick.
    const rows = within(table).getAllByRole("row");
    for (const row of rows) {
      expect(row.className).not.toContain("scene-vocab-used");
      expect(row.className).not.toContain("scene-vocab-missed");
    }
  });

  it("keeps the overview focused on the challenge actions without a vocabulary table or popup", () => {
    render(
      <StoryRecorder
        topic={topicWithVocabDetails}
        selectedImage={topicWithVocabDetails.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
        enableSorting={true}
        enableOverview={true}
      />,
    );

    expect(screen.queryByRole("table", { name: "Key vocabulary" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Flashcards/i })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Your Challenge/i })).toBeInTheDocument();
  });

  it("keeps the scene vocabulary row focused on listening instead of a duplicate recorder", async () => {
    const user = userEvent.setup();
    render(
      <StoryRecorder
        topic={topicWithVocabDetails}
        selectedImage={topicWithVocabDetails.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    // Finish the mandatory vocab quiz gate (this topic has 1 translated
    // word, enough to trigger it) to reach the practice-phase vocab table.
    await completeVocabQuiz(user);

    const listenButton = screen.getByRole("button", {
      name: "Listen to the model pronunciation of market",
    });
    expect(listenButton).toHaveAttribute("title", "Listen to this word");
    expect(screen.queryByRole("button", { name: /Record market/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Practice pronouncing market/i })).not.toBeInTheDocument();

  });

  it("shows a vocabulary quiz before practice when the story has enough translated words", async () => {
    const user = userEvent.setup();
    render(
      <StoryRecorder
        topic={topicWithQuizVocab}
        selectedImage={topicWithQuizVocab.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    expect(screen.getByRole("region", { name: "Vocabulary quiz" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Scene vocabulary" })).not.toBeInTheDocument();
    // Mandatory the first time through — no skip button yet.
    expect(screen.queryByRole("button", { name: /Skip/ })).not.toBeInTheDocument();

    await completeVocabQuiz(user);

    expect(screen.queryByRole("region", { name: "Vocabulary quiz" })).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();
  });

  it("does not show the vocabulary quiz when a story has no translated words", () => {
    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    expect(screen.queryByRole("region", { name: "Vocabulary quiz" })).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();
  });

  it("walks a scene through a merged Study step (vocabulary + phrases together) then Speaking, instead of a separate tab per reference type", async () => {
    const user = userEvent.setup();
    const topicWithPhrases = {
      ...topicWithVocabDetails,
      phrases: { 0: ["我要去市場"] },
      phrasesTranslation: { 0: ["I'm going to the market"] },
    };

    render(
      <StoryRecorder
        topic={topicWithPhrases}
        selectedImage={topicWithPhrases.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    // Finish the mandatory vocab quiz gate (this topic has a translated
    // word, enough to trigger it) to reach the practice-phase Study step.
    await completeVocabQuiz(user);

    // Lands on Study by default — vocabulary and phrases show together, no
    // record controls yet.
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();
    expect(screen.getByText("我要去市場")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Record your story" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Continue to Speaking/ }));

    // Speaking step: record controls are back, the Study panels are gone.
    expect(screen.getByRole("region", { name: "Record your story" })).toBeInTheDocument();
    expect(screen.queryByText("我要去市場")).not.toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Scene vocabulary" })).not.toBeInTheDocument();

    // The tab bar lets a student jump straight back to Study at any time.
    await user.click(screen.getByRole("tab", { name: /Study/ }));
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();
    expect(screen.getByText("我要去市場")).toBeInTheDocument();
  });

  it("shows the teacher's suggested-answer sentence during the Speaking step so students can read along", async () => {
    const user = userEvent.setup();
    const topicWithSuggestedAnswer = {
      ...topicWithVocabDetails,
      suggestedAnswers: { 0: "我在餐廳吃飯。" },
    };

    render(
      <StoryRecorder
        topic={topicWithSuggestedAnswer}
        selectedImage={topicWithSuggestedAnswer.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    await completeVocabQuiz(user);
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));

    expect(screen.getAllByText("我在餐廳吃飯。")).toHaveLength(1);
  });

  it("exposes the teacher's model recording in the Speaking step", async () => {
    const user = userEvent.setup();
    const topicWithModelRecording = {
      ...topic,
      suggestedAnswers: { 0: "我在市場幫助朋友。" },
      listenAudioUrls: { 0: "https://example.com/model-scene-1.wav" },
    };

    render(
      <StoryRecorder
        topic={topicWithModelRecording}
        selectedImage={topicWithModelRecording.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    expect(
      screen.getByLabelText("Model recording: 我在市場幫助朋友。"),
    ).toHaveAttribute(
      "src",
      "https://example.com/model-scene-1.wav",
    );
  });
});
