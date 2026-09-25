// @ts-nocheck
import { getAudioUploadError, getImageUploadError } from "../../../../utils/myStoriesUtils";

export function useStoryBuilderFrameActions(deps) {
  const { customDraft, onSetDraft, updateDraftFrame, setValidationErrors } = deps;

  const readAudioAsDataUrl = (file: File): Promise<string> => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") resolve(reader.result);
      else reject(new Error("Could not read the audio file."));
    };
    reader.onerror = () => reject(new Error("Could not read the audio file."));
    reader.readAsDataURL(file);
  });
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

  const handleUploadFrameAudioBatch = async (files?: FileList | File[]) => {
    const selectedFiles = Array.from(files ?? []).sort((left, right) =>
      left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: "base" }),
    );
    const frameCount = customDraft.listenAudioUrls[customDraft.activeLevel].length;

    if (!selectedFiles.length) return;
    if (selectedFiles.length !== frameCount) {
      setValidationErrors((errors) => ({
        ...errors,
        form: `Select exactly ${frameCount} audio files so each file maps to one scene (01 → Scene 1, 02 → Scene 2, ...).`,
      }));
      return;
    }

    const firstError = selectedFiles.map(getAudioUploadError).find(Boolean);
    if (firstError) {
      setValidationErrors((errors) => ({ ...errors, form: firstError }));
      return;
    }

    try {
      const dataUrls = await Promise.all(selectedFiles.map(readAudioAsDataUrl));
      const level = customDraft.activeLevel;
      onSetDraft((draft) => ({
        ...draft,
        listenAudioUrls: {
          ...draft.listenAudioUrls,
          [level]: dataUrls,
        },
        listenAudioSources: {
          ...draft.listenAudioSources,
          [level]: dataUrls.map(() => "teacher"),
        },
      }));
      setValidationErrors((errors) => ({ ...errors, form: undefined }));
    } catch {
      setValidationErrors((errors) => ({
        ...errors,
        form: "One or more audio files could not be read. Please try again.",
      }));
    }
  };

  const handleRemoveFrameAudio = (index: number) => {
    updateDraftFrame("listenAudioUrls", index, "");
    updateDraftFrame("listenAudioSources", index, "");
  };

  return {
    handlePasteFrameImage, handleUploadFrameImage,
    handleUploadFrameAudio, handleUploadFrameAudioBatch, handleRemoveFrameAudio,
  };
}
