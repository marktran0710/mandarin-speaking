import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StoryBuilderSection from "./StoryBuilderSection";
import {
  CUSTOM_STORY_STORAGE_KEY,
  type CustomTeacherStory,
} from "../../utils/teacherStories";

// The builder's blank draft ships 6 default prompts, so a story with MORE
// frames than that is the interesting case: teachers do create 7- and 9-frame
// stories, and the last frames often have no prompt text.
function storyWithFrames(count: number): CustomTeacherStory {
  return {
    id: "custom-story-test",
    title: "Taiwan Community Story",
    learningGoal: "Students describe who, where, and what happened.",
    frames: Array.from({ length: count }, (_, index) => ({
      imageUrl: `/uploads/images/frame-${index + 1}.png`,
      // Frames past the 6th carry no prompt — exactly what the saved stories
      // in the teacher library look like.
      prompt: index < 6 ? `Prompt ${index + 1}` : "",
      vocabulary: "媽, 友美",
    })),
    narrativeMode: "story",
  };
}

const saveToDatabase = vi.fn(async (story: CustomTeacherStory) => story);

// The builder syncs its library from the backend on mount, so this has to
// serve the same story the test seeded or the row disappears before the click.
let storiesOnServer: CustomTeacherStory[] = [];

vi.mock("../../services/database", () => ({
  canUseDatabase: () => true,
  createCustomStory: (story: CustomTeacherStory) => saveToDatabase(story),
  deleteCustomStoryFromDatabase: vi.fn(async () => {}),
  listCustomStories: vi.fn(async () => storiesOnServer),
}));

async function editAndUpdate(story: CustomTeacherStory) {
  const user = userEvent.setup();
  storiesOnServer = [story];
  window.localStorage.setItem(CUSTOM_STORY_STORAGE_KEY, JSON.stringify([story]));

  render(<StoryBuilderSection />);

  await user.click(await screen.findByRole("button", { name: /^edit$/i }));
  await user.click(
    await screen.findByRole("button", { name: /update custom story/i }),
  );
}

describe("StoryBuilderSection – updating a saved story", () => {
  beforeEach(() => {
    saveToDatabase.mockClear();
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("saves a 6-frame story", async () => {
    await editAndUpdate(storyWithFrames(6));

    await waitFor(() => expect(saveToDatabase).toHaveBeenCalledTimes(1));
  });

  it("saves a story with more frames than the default prompt list", async () => {
    await editAndUpdate(storyWithFrames(7));

    await waitFor(() => expect(saveToDatabase).toHaveBeenCalledTimes(1));
  });
});

describe("StoryBuilderSection – quiz needs review badge", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function storyWithAiMaterial(overrides: Partial<CustomTeacherStory> = {}): CustomTeacherStory {
    return {
      id: "custom-story-quiz-badge",
      title: "Badge Story",
      learningGoal: "goal",
      published: true,
      frames: [
        {
          imageUrl: "",
          prompt: "p",
          vocabulary: "知道",
          vocabularyTranslation: "to know",
          vocabularyDistractors: JSON.stringify([["a", "b", "c"]]),
        },
      ],
      ...overrides,
    };
  }

  it("shows the badge when live AI material has never been approved", async () => {
    const story = storyWithAiMaterial();
    storiesOnServer = [story];
    window.localStorage.setItem(CUSTOM_STORY_STORAGE_KEY, JSON.stringify([story]));

    render(<StoryBuilderSection />);
    expect(await screen.findByText(/Quiz needs review/)).toBeInTheDocument();
  });

  it("hides the badge once the approved snapshot matches live material", async () => {
    const story = storyWithAiMaterial({
      quizApprovedSnapshot: {
        easy: [
          {
            word: "知道",
            translation: "to know",
            distractors: ["a", "b", "c"],
            cloze: [],
            synonym: [],
            lookalike: [],
          },
        ],
      },
    });
    storiesOnServer = [story];
    window.localStorage.setItem(CUSTOM_STORY_STORAGE_KEY, JSON.stringify([story]));

    render(<StoryBuilderSection />);
    await screen.findByText("Badge Story");
    expect(screen.queryByText(/Quiz needs review/)).not.toBeInTheDocument();
  });

  it("hides the badge for a story with no AI-generated material at all", async () => {
    const story: CustomTeacherStory = {
      id: "custom-story-no-ai",
      title: "No AI Story",
      learningGoal: "goal",
      published: true,
      frames: [{ imageUrl: "", prompt: "p", vocabulary: "知道", vocabularyTranslation: "to know" }],
    };
    storiesOnServer = [story];
    window.localStorage.setItem(CUSTOM_STORY_STORAGE_KEY, JSON.stringify([story]));

    render(<StoryBuilderSection />);
    await screen.findByText("No AI Story");
    expect(screen.queryByText(/Quiz needs review/)).not.toBeInTheDocument();
  });
});

describe("StoryBuilderSection – post-update Quiz Review nudge", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the nudge banner after updating an existing story, not after creating a new one", async () => {
    const story = storyWithFrames(6);
    await editAndUpdate(story);

    expect(
      await screen.findByText(/Quiz material may need review/),
    ).toBeInTheDocument();
  });

  it("calls onGoToQuizReview with the story's lesson number and dismisses the banner", async () => {
    const story = { ...storyWithFrames(6), lessonNumber: 5 };
    const onGoToQuizReview = vi.fn();
    const user = userEvent.setup();
    storiesOnServer = [story];
    window.localStorage.setItem(CUSTOM_STORY_STORAGE_KEY, JSON.stringify([story]));

    render(<StoryBuilderSection onGoToQuizReview={onGoToQuizReview} />);
    await user.click(await screen.findByRole("button", { name: /^edit$/i }));
    await user.click(await screen.findByRole("button", { name: /update custom story/i }));

    await user.click(await screen.findByRole("button", { name: /Go to Quiz Review/ }));
    expect(onGoToQuizReview).toHaveBeenCalledWith(5);
    expect(screen.queryByText(/Quiz material may need review/)).not.toBeInTheDocument();
  });

  it("dismissing the banner directly does not call onGoToQuizReview", async () => {
    const onGoToQuizReview = vi.fn();
    const story = storyWithFrames(6);
    const user = userEvent.setup();
    storiesOnServer = [story];
    window.localStorage.setItem(CUSTOM_STORY_STORAGE_KEY, JSON.stringify([story]));

    render(<StoryBuilderSection onGoToQuizReview={onGoToQuizReview} />);
    await user.click(await screen.findByRole("button", { name: /^edit$/i }));
    await user.click(await screen.findByRole("button", { name: /update custom story/i }));

    await user.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(onGoToQuizReview).not.toHaveBeenCalled();
    expect(screen.queryByText(/Quiz material may need review/)).not.toBeInTheDocument();
  });
});
