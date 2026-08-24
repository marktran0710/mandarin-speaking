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
  jsonResponse,
  mockBackendAnalyze,
  resetStoryRecorderTestEnvironment,
  topic,
  topicWithQuizVocab,
} from "./StoryRecorder.test.helpers";

describe("StoryRecorder student prototype", () => {
  beforeEach(resetStoryRecorderTestEnvironment);
  afterEach(cleanupStoryRecorderTestEnvironment);
  describe("pilot progression policy overrides legacy passed=false (PARTS 2/3)", () => {
    afterEach(() => {
      window.history.pushState({}, "", "/");
    });

    async function uploadAndAnalyze(user: UserEvent) {
      await user.click(screen.getByRole("tab", { name: /Speaking/ }));
      await user.click(screen.getByText("Recording options"));
      const voiceFile = new File(["RIFF....WAVEfmt "], "attempt.wav", { type: "audio/wav" });
      const input = document.querySelector(".submit-voice-input") as HTMLInputElement;
      await user.upload(input, voiceFile);
      await user.click(await screen.findByRole("button", { name: /Analyze audio/i }));
      await screen.findByRole("region", { name: "Recording results" });
    }

    it("blocks progression on a legacy fail when assistive feedback is NOT active (unchanged default behavior)", async () => {
      // Default buildAnalyzeResponse() has one word with passed:false and no
      // assistive_feedback -- legacy gating applies exactly as before this task.
      mockBackendAnalyze(buildAnalyzeResponse());
      const user = userEvent.setup();
      const { container } = render(
        <StoryRecorder
          topic={topic}
          selectedImage={topic.images[0]}
          selectedImageIndex={0}
          onImageSelect={vi.fn()}
          onImageChange={vi.fn()}
          onAddRecord={vi.fn()}
        />,
      );
      await uploadAndAnalyze(user);
      await waitFor(() => {
        expect(container.querySelector(".sfc-unlock-note")).toBeInTheDocument();
      });
      expect(screen.queryByRole("button", { name: /Next scene/ })).not.toBeInTheDocument();
    });

    it("does not block progression on a legacy fail for a pilot session with active assistive feedback", async () => {
      window.history.pushState({}, "", "/?pilot=1");
      mockBackendAnalyze(
        buildAnalyzeResponse({
          assistive_feedback: [
            {
              syllable_index: 0,
              character: "A",
              expected_underlying_tone: 2,
              accepted_surface_tones: [2],
              context_rule: null,
              realization: "plain",
              assistive_state: "NEEDS_PRACTICE",
              assistive_state_label: "CHECK_THIS_TONE",
              assistive_message: "This tone may be worth checking.",
              e2_diagnostic_category: "T2",
              explanation: { e2_provenance: "measured", e2_matched_tone: 2, boundary_before: false, boundary_after: false },
            },
          ],
        }),
      );
      const user = userEvent.setup();
      const { container } = render(
        <StoryRecorder
          topic={topic}
          selectedImage={topic.images[0]}
          selectedImageIndex={0}
          onImageSelect={vi.fn()}
          onImageChange={vi.fn()}
          onAddRecord={vi.fn()}
        />,
      );
      await uploadAndAnalyze(user);
      // The legacy lock note must be gone even though word "A" still has
      // passed:false in word_prosody -- PART 3's non-interference rule.
      await waitFor(() => {
        expect(container.querySelector(".sfc-unlock-note")).not.toBeInTheDocument();
      });
      expect(await screen.findByRole("button", { name: /Next scene/ })).toBeInTheDocument();
      // The bounded, optional one-retry offer (never a hard gate) is still shown.
      expect(container.querySelector(".sfc-assistive-retry-hint")).toBeInTheDocument();
    });
  });

});
