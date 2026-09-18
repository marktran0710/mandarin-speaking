// @ts-nocheck
import { getImageUploadError } from "../../utils/myStoriesUtils";

export function useStoryBuilderFrameActions(deps) {
  const { updateDraftFrame, setValidationErrors } = deps;
  const handlePasteFrameImage = (index: number, event: React.ClipboardEvent) => {
    const items = event.clipboardData?.items;
    if (!items) {
      return;
    }
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        event.preventDefault();
        handleUploadFrameImage(index, item.getAsFile() ?? undefined);
        return;
      }
    }
  };

  const handleUploadFrameImage = (index: number, file?: File) => {
    if (!file) {
      return;
    }

    const error = getImageUploadError(file);
    if (error) {
      setValidationErrors((errors) => ({ ...errors, form: error }));
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        updateDraftFrame("imageUrls", index, reader.result);
      }
    };
    reader.readAsDataURL(file);
  };

  return {
    handlePasteFrameImage, handleUploadFrameImage,
  };
}
