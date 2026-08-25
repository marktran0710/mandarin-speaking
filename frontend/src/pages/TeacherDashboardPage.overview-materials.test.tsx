import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TopicSelector from "../components/TopicSelector";
import TeacherDashboardPage from "./TeacherDashboardPage";
import MyStoriesPage, { type AudioRecord } from "./MyStoriesPage";
import * as db from "../services/database";
import type { VocabQuizAttempt } from "../services/database";
import { loadPublishedTeacherTopics } from "../utils/teacherStories";

const analyzedRecord = {
  id: "record-1",
  timestamp: "5/25/2026, 10:00 AM",
  duration: 42,
  transcription: "我和朋友去森林冒險，最後找到了地圖。",
  model: "gemini",
  topicId: "adventure",
  imageUrl: "https://picsum.photos/400/300?random=1",
  imageIndex: 0,
  praatMetrics: {
    pitch_contour: [
      [0, 180],
      [0.2, 195],
      [0.4, 188],
    ],
    word_prosody: [
      {
        token: "冒",
        index: 0,
        pitch_contour: [
          [0, 180],
          [0.2, 195],
        ],
        tone_accuracy: 86,
        judged: true,
        mean_pitch: 188,
        pitch_range: 15,
        contour_shape: "rising",
        feedback: "The tone is clear.",
      },
    ],
    detected_tone: 2,
    tone_accuracy: 86,
    formants: {
      F1: 500,
      F2: 1500,
      F3: 2500,
    },
    speech_rate: 3.2,
    fluency_score: 78,
    pitch_statistics: {},
    feedback: "Your pitch movement is clear.",
    ai_feedback: {
      provider: "gemini",
      fluency: {
        score: 82,
        feedback: "Good pacing with a clear story sequence.",
      },
      grammar: {
        score: 76,
        feedback: "Use more complete connectors between events.",
        corrections: ["Add 然後 before the second event."],
      },
      vocabulary: {
        score: 80,
        feedback: "Good topic words. Add one feeling word.",
        suggestions: ["興奮", "緊張"],
      },
      improved_version: "我和朋友去森林冒險，然後找到了地圖。",
      practice_prompt: "Try adding one sentence about how you felt.",
    },
  },
};

vi.mock("../components/PitchChart", () => ({
  default: () => <div data-testid="pitch-chart">Pitch chart</div>,
}));

function renderDashboard(records: AudioRecord[] = []) {
  return render(
    <TeacherDashboardPage
      records={records}
      onDeleteRecord={vi.fn()}
      helpRequests={[]}
      onLogout={vi.fn()}
    />,
  );
}

describe("TeacherDashboardPage", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("summarizes analyzed student recordings on the overview", async () => {
    const user = userEvent.setup();
    renderDashboard([analyzedRecord]);

    expect(
      screen.getByRole("heading", { name: "Class Overview" }),
    ).toBeInTheDocument();
    const overview = screen.getByRole("region", { name: "Class overview" });
    expect(within(overview).getAllByText("1")).toHaveLength(2);
    expect(within(overview).getByText("78/100")).toBeInTheDocument();
    expect(within(overview).getByText("86%")).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Teacher tools" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Recordings & Help/ }));
    expect(
      screen.getByText("Good pacing with a clear story sequence."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("pitch-chart")).toBeInTheDocument();
  });

  it("uses the complete recording count and loads another page of recordings", async () => {
    const loadMoreRecords = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <TeacherDashboardPage
        records={[analyzedRecord]}
        totalRecordCount={125}
        hasMoreAudioRecords
        onDeleteRecord={vi.fn()}
        onLoadMoreAudioRecords={loadMoreRecords}
        helpRequests={[]}
        onLogout={vi.fn()}
      />,
    );

    const overview = screen.getByRole("region", { name: "Class overview" });
    expect(within(overview).getByText("125")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Recordings & Help/ }));
    await user.click(screen.getByRole("button", { name: "Load more" }));

    expect(loadMoreRecords).toHaveBeenCalledOnce();
  });

  it("toggles dark mode from the shell and persists the choice", async () => {
    const user = userEvent.setup();
    renderDashboard();

    await user.click(screen.getByRole("button", { name: /Dark/ }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("colorMode")).toBe("dark");

    await user.click(screen.getByRole("button", { name: /Light/ }));
    expect(document.documentElement.getAttribute("data-theme")).toBeNull();
    expect(localStorage.getItem("colorMode")).toBe("light");
  });

  it("doesn't crash the whole dashboard when a record's AI feedback is missing a category", async () => {
    const user = userEvent.setup();
    const partialFeedbackRecord = {
      ...analyzedRecord,
      id: "record-partial-feedback",
      praatMetrics: {
        ...analyzedRecord.praatMetrics,
        ai_feedback: {
          provider: "gemini",
          fluency: { score: 82, feedback: "Good pacing with a clear story sequence." },
          // grammar intentionally omitted — some real recordings' AI feedback
          // is missing a category, which must not crash the dashboard.
          vocabulary: { score: 80, feedback: "Good topic words.", suggestions: [] },
          improved_version: "我和朋友去森林冒險，然後找到了地圖。",
          practice_prompt: "Try adding one sentence about how you felt.",
        },
      },
    };

    renderDashboard([partialFeedbackRecord]);
    const user2 = user;
    await user2.click(screen.getByRole("button", { name: /Recordings & Help/ }));

    expect(
      screen.getByText("Good pacing with a clear story sequence."),
    ).toBeInTheDocument();
    expect(screen.getByText("Good topic words.")).toBeInTheDocument();
  });

  it("lets teachers save a custom image-based story activity", async () => {
    const user = userEvent.setup();
    renderDashboard();

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.type(screen.getByLabelText("Story title"), "Taipei Rain Rescue");
    const imageInputs = screen.getAllByLabelText("Image URL or uploaded file");
    for (let index = 0; index < imageInputs.length; index += 1) {
      await user.type(
        imageInputs[index],
        `https://example.com/rain-scene-${index + 1}.jpg`,
      );
    }
    await user.click(screen.getByRole("button", { name: /Edit learning content/ }));
    await user.click(screen.getAllByRole("button", { name: "+ Add word" })[0]);
    await user.type(screen.getAllByLabelText("Chinese word")[0], "下雨");
    await user.click(screen.getByRole("button", { name: "Close learning content" }));

    await user.click(screen.getByRole("button", { name: "Save custom story" }));

    const library = screen.getByLabelText("Saved custom stories");
    expect(within(library).getByText("Taipei Rain Rescue")).toBeInTheDocument();
    expect(localStorage.getItem("teacherCustomStories")).toContain(
      "Taipei Rain Rescue",
    );
  }, 10000);

  it("saves all four vocabulary table columns for a word", async () => {
    const user = userEvent.setup();
    renderDashboard();

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.type(screen.getByLabelText("Story title"), "Restaurant Story");
    const imageInputs = screen.getAllByLabelText("Image URL or uploaded file");
    for (let index = 0; index < imageInputs.length; index += 1) {
      await user.type(
        imageInputs[index],
        `https://example.com/restaurant-scene-${index + 1}.jpg`,
      );
    }

    await user.click(screen.getByRole("button", { name: /Edit learning content/ }));
    await user.click(screen.getAllByRole("button", { name: "+ Add word" })[0]);
    await user.type(screen.getAllByLabelText("Chinese word")[0], "餐廳");
    await user.type(screen.getAllByLabelText("Pinyin")[0], "cāntīng");
    await user.selectOptions(screen.getAllByLabelText("Part of speech")[0], "N");
    await user.type(screen.getAllByLabelText("English translation")[0], "restaurant");
    await user.click(screen.getByRole("button", { name: "Close learning content" }));

    await user.click(screen.getByRole("button", { name: "Save custom story" }));

    const stored = localStorage.getItem("teacherCustomStories") || "";
    expect(stored).toContain('"vocabulary":"餐廳"');
    expect(stored).toContain('"vocabularyPinyin":"cāntīng"');
    expect(stored).toContain('"vocabularyPos":"N"');
    expect(stored).toContain('"vocabularyTranslation":"restaurant"');
  }, 10000);

  it("fills the vocabulary table from the suggested-answer sentence via AI, without overwriting cells already filled in", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({
        words: [
          { word: "餐廳", pinyin: "cāntīng", pos: "N", translation: "restaurant" },
          { word: "吃", pinyin: "chī", pos: "V", translation: "to eat" },
        ],
      }),
    })));

    renderDashboard();

    await user.click(screen.getByRole("button", { name: /Materials/ }));

    // Teacher already typed one word in by hand, with its own translation —
    // autofill must fill the blank pinyin cell but leave "diner" untouched.
    await user.type(
      screen.getAllByLabelText("Script")[0],
      "我在餐廳吃飯。",
    );
    await user.click(screen.getByRole("button", { name: /Edit learning content/ }));
    await user.click(screen.getAllByRole("button", { name: "+ Add word" })[0]);
    await user.type(screen.getAllByLabelText("Chinese word")[0], "餐廳");
    await user.type(screen.getAllByLabelText("English translation")[0], "diner");
    await user.click(
      screen.getByRole("button", { name: "✨ Fill vocab from story scripts" }),
    );

    await waitFor(() => {
      expect(screen.getAllByLabelText("Chinese word").map((el) => (el as HTMLInputElement).value)).toEqual(
        expect.arrayContaining(["餐廳", "吃"]),
      );
    });
    expect((screen.getAllByLabelText("Pinyin")[0] as HTMLInputElement).value).toBe("cāntīng");
    expect((screen.getAllByLabelText("English translation")[0] as HTMLInputElement).value).toBe("diner");

    vi.unstubAllGlobals();
  }, 10000);

  it("disables the vocab autofill button until a suggested-answer sentence is entered", async () => {
    renderDashboard();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.click(screen.getByRole("button", { name: /Edit learning content/ }));

    expect(
      screen.getByRole("button", { name: "✨ Fill vocab from story scripts" }),
    ).toBeDisabled();
  });

  it("generates phrases from the suggested-answer sentence via AI, scaled to the active difficulty tier", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({
        phrases: [{ phrase: "想要", translation: "want to" }],
      }),
    })));

    renderDashboard();

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.type(
      screen.getAllByLabelText("Script")[0],
      "我想要在餐廳吃飯。",
    );
    await user.click(screen.getByRole("button", { name: /Edit learning content/ }));

    // Easy tier (the default) asks for 1 phrase.
    const generateButton = screen.getAllByRole("button", {
      name: "✨ +1 phrase",
    })[0];
    await user.click(generateButton);

    await waitFor(() => {
      expect(
        screen.getAllByLabelText("Phrase").map((el) => (el as HTMLInputElement).value),
      ).toContain("想要");
    });
    const fetchCall = vi.mocked(fetch).mock.calls.find(([url]) =>
      String(url).includes("/api/phrases-from-sentence"),
    );
    const body = JSON.parse(fetchCall![1]!.body as string);
    expect(body).toEqual({ sentence: "我想要在餐廳吃飯。", count: 1 });

    vi.unstubAllGlobals();
  }, 10000);

  it("disables the phrase generate button until a suggested-answer sentence is entered", async () => {
    renderDashboard();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.click(screen.getByRole("button", { name: /Edit learning content/ }));

    expect(
      screen.getAllByRole("button", { name: "✨ +1 phrase" })[0],
    ).toBeDisabled();
  });

  it("lets teachers edit a saved custom story activity", async () => {
    const user = userEvent.setup();
    renderDashboard();

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.type(screen.getByLabelText("Story title"), "Original Story");
    for (const [index, input] of screen
      .getAllByLabelText("Image URL or uploaded file")
      .entries()) {
      await user.type(input, `https://example.com/edit-scene-${index + 1}.jpg`);
    }
    await user.click(screen.getByRole("button", { name: "Save custom story" }));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.type(screen.getByLabelText("Story title"), "Edited Story");
    await user.click(
      screen.getByRole("button", { name: "Update custom story" }),
    );

    const stored = localStorage.getItem("teacherCustomStories") || "";
    expect(stored).toContain("Edited Story");
    expect(stored).not.toContain("Original Story");
    expect(JSON.parse(stored)).toHaveLength(1);
  }, 10000);

  it("publishes a teacher story into the student topic selector", async () => {
    const user = userEvent.setup();
    const { unmount } = renderDashboard();

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.type(screen.getByLabelText("Story title"), "Published MRT Help");
    for (const [index, input] of screen
      .getAllByLabelText("Image URL or uploaded file")
      .entries()) {
      await user.type(
        input,
        `https://example.com/published-scene-${index + 1}.jpg`,
      );
    }
    await user.click(screen.getByRole("button", { name: "Save custom story" }));
    await user.click(screen.getByRole("button", { name: "Publish" }));

    expect(localStorage.getItem("teacherCustomStories")).toContain(
      '"published":true',
    );

    unmount();
    render(<TopicSelector />);

    expect(
      screen.getByRole("button", { name: /Published MRT Help/ }),
    ).toBeInTheDocument();
  }, 10000);

  it("shows validation errors when a teacher saves an incomplete custom story", async () => {
    const user = userEvent.setup();
    renderDashboard();

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.click(screen.getByRole("button", { name: "Save custom story" }));

    expect(
      screen.getByText("Add a story title for students."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Frame 1 needs an image URL or uploaded image."),
    ).toBeInTheDocument();
    expect(screen.getByText("No custom stories yet")).toBeInTheDocument();
  });

  it("lets teachers upload a local image for a custom story frame", async () => {
    const user = userEvent.setup();
    renderDashboard();

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    const imageFile = new File(["story-image"], "story-frame.png", {
      type: "image/png",
    });

    await user.upload(
      screen.getAllByLabelText("Upload from computer")[0],
      imageFile,
    );
    const imageInputs = screen.getAllByLabelText("Image URL or uploaded file");
    for (let index = 1; index < imageInputs.length; index += 1) {
      await user.type(
        imageInputs[index],
        `https://example.com/upload-support-${index + 1}.jpg`,
      );
    }
    await waitFor(() => {
      const imageInput = screen.getAllByLabelText(
        "Image URL or uploaded file",
      )[0] as HTMLInputElement;
      expect(imageInput.value).toContain("data:image/png");
    });

    await user.click(screen.getByRole("button", { name: "Save custom story" }));
    expect(localStorage.getItem("teacherCustomStories")).toContain(
      "data:image/png",
    );
  });

});
