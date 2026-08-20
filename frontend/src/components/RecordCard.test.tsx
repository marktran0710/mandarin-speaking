import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RecordCard from "./RecordCard";
import type { AudioRecord } from "../pages/MyStoriesPage";

vi.mock("./PitchChart", () => ({
  default: () => <div />,
}));

const record: AudioRecord = {
  id: "record-1",
  timestamp: "5/25/2026, 10:00 AM",
  duration: 42,
  transcription: "A practice recording",
  model: "gemini",
  topicId: "adventure",
};

describe("RecordCard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("asks for confirmation before deleting a recording", async () => {
    const confirm = vi.fn(() => false);
    const onDeleteRecord = vi.fn();
    vi.stubGlobal("confirm", confirm);
    const user = userEvent.setup();
    render(<RecordCard record={record} onDeleteRecord={onDeleteRecord} />);

    await user.click(screen.getByTitle(/Delete this story/));

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining(record.timestamp));
    expect(onDeleteRecord).not.toHaveBeenCalled();
  });
});
