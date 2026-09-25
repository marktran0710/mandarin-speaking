// @ts-nocheck
import { getAudioUploadError, getImageUploadError } from "../../../../utils/myStoriesUtils";

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

  const handleUploadFrameAudio = (index: number, file?: File) => {
    if (!file) {
      return;
    }

    const error = getAudioUploadError(file);
    if (error) {
      setValidationErrors((errors) => ({ ...errors, form: error }));
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        updateDraftFrame("listenAudioUrls", index, reader.result);
        updateDraftFrame("listenAudioSources", index, "teacher");
      }
    };
    reader.readAsDataURL(file);
  };

  const handleRemoveFrameAudio = (index: number) => {
    updateDraftFrame("listenAudioUrls", index, "");
    updateDraftFrame("listenAudioSources", index, "");
  };

  return {
    handlePasteFrameImage, handleUploadFrameImage,
    handleUploadFrameAudio, handleRemoveFrameAudio,
  };
}
