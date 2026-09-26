// @ts-nocheck
import { useState } from "react";
import { canUseDatabase, createCustomStory as saveCustomStoryToDatabase } from "../../../../services/database";
import { saveCustomStories } from "@entities/story";
import { getAudioUploadError, parseLessonAudioFilename } from "../../../../utils/myStoriesUtils";
import { expandAudioSelection } from "./bulkAudioFiles";

const readAudioAsDataUrl = (file: File): Promise<string> => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => {
    if (typeof reader.result === "string") resolve(reader.result);
    else reject(new Error("Could not read the audio file."));
  };
  reader.onerror = () => reject(new Error("Could not read the audio file."));
  reader.readAsDataURL(file);
});

/** Lets a teacher pick every scene recording for several stories at once
 * (e.g. all of lesson 5-8) instead of opening each story's editor and using
 * its per-story "Upload audio for all scenes" batch upload. Files are
 * matched to a story via parseLessonAudioFilename (lesson-subOrder-scene,
 * e.g. "5-1-01.mp3"), grouped, applied to the matching story's frames, and
 * saved through the same createCustomStory endpoint a normal save uses. */
export function useBulkAudioUpload(customStories, setCustomStories) {
  const [isUploading, setIsUploading] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const handleBulkUploadAudio = async (files?: FileList | File[]) => {
    const selectedFiles = Array.from(files ?? []);
    if (!selectedFiles.length) return;
    setNotice("");
    setError("");

    setIsUploading(true);
    let expanded;
    try {
      expanded = await expandAudioSelection(selectedFiles);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Could not extract the selected ZIP archive.");
      setIsUploading(false);
      return;
    }

    const audioFiles = expanded.files;
    const badFile = audioFiles.map(getAudioUploadError).find(Boolean);
    if (badFile) {
      setError([badFile, ...expanded.issues].join(" "));
      setIsUploading(false);
      return;
    }

    const groups = new Map();
    const skippedFiles: string[] = [];
    for (const file of audioFiles) {
      const parsed = parseLessonAudioFilename(file.name);
      if (!parsed) {
        skippedFiles.push(file.name);
        continue;
      }
      const key = `${parsed.lessonNumber}-${parsed.lessonSubOrder}`;
      if (!groups.has(key)) {
        groups.set(key, {
          lessonNumber: parsed.lessonNumber,
          lessonSubOrder: parsed.lessonSubOrder,
          files: [],
        });
      }
      groups.get(key).files.push({ file, sceneIndex: parsed.sceneIndex });
    }

    if (groups.size === 0) {
      setError(
        [
          ...expanded.issues,
          'No files matched the "lesson-story-scene" naming pattern, e.g. "5-1-01.mp3" for Lesson 5, story 1, scene 1.',
        ].join(" "),
      );
      setIsUploading(false);
      return;
    }

    const updatedStories = [];
    const failures: string[] = [...expanded.issues];

    for (const { lessonNumber, lessonSubOrder, files: sceneFiles } of groups.values()) {
      const label = `Lesson ${lessonNumber}-${lessonSubOrder}`;
      const story = customStories.find(
        (candidate) => candidate.lessonNumber === lessonNumber && candidate.lessonSubOrder === lessonSubOrder,
      );
      if (!story) {
        failures.push(`${label}: no saved story matches this lesson/story number.`);
        skippedFiles.push(...sceneFiles.map((entry) => entry.file.name));
        continue;
      }

      const frames = story.frames.map((frame) => ({ ...frame }));
      const inRange = sceneFiles.filter((entry) => entry.sceneIndex >= 1 && entry.sceneIndex <= frames.length);
      const outOfRange = sceneFiles.filter((entry) => entry.sceneIndex < 1 || entry.sceneIndex > frames.length);
      if (outOfRange.length) {
        failures.push(
          `${label}: scene ${outOfRange.map((entry) => entry.sceneIndex).join(", ")} out of range (story has ${frames.length} scenes).`,
        );
        skippedFiles.push(...outOfRange.map((entry) => entry.file.name));
      }
      if (!inRange.length) continue;

      try {
        const dataUrls = await Promise.all(inRange.map((entry) => readAudioAsDataUrl(entry.file)));
        inRange.forEach((entry, i) => {
          frames[entry.sceneIndex - 1] = {
            ...frames[entry.sceneIndex - 1],
            listenAudioUrl: dataUrls[i],
            listenAudioSource: "teacher",
          };
        });

        let updatedStory = { ...story, frames };
        if (canUseDatabase()) {
          const persisted = await saveCustomStoryToDatabase(updatedStory);
          if (persisted) {
            updatedStory = {
              ...updatedStory,
              ...persisted,
              frames: persisted.frames.map((persistedFrame, i) => ({
                ...updatedStory.frames[i],
                ...persistedFrame,
              })),
            };
          }
        }
        updatedStories.push(updatedStory);
      } catch (uploadError) {
        failures.push(`${label}: ${uploadError instanceof Error ? uploadError.message : "could not save audio"}.`);
      }
    }

    if (updatedStories.length) {
      setCustomStories((current) => {
        const next = current.map(
          (story) => updatedStories.find((updated) => updated.id === story.id) ?? story,
        );
        try {
          saveCustomStories(next);
        } catch {
          // localStorage is only a cache; the backend save above already succeeded.
        }
        return next;
      });
    }

    setIsUploading(false);
    const messageParts: string[] = [];
    if (updatedStories.length) {
      messageParts.push(
        `Updated audio for ${updatedStories.length} ${updatedStories.length === 1 ? "story" : "stories"}.`,
      );
    }
    if (skippedFiles.length) {
      const preview = skippedFiles.slice(0, 5).join(", ");
      messageParts.push(
        `Skipped ${skippedFiles.length} file${skippedFiles.length === 1 ? "" : "s"}: ${preview}${skippedFiles.length > 5 ? ", ..." : ""}.`,
      );
    }
    messageParts.push(...failures);

    if (updatedStories.length) {
      setNotice(messageParts.join(" "));
    } else {
      setError(messageParts.join(" ") || "No files matched a saved story.");
    }
  };

  return {
    handleBulkUploadAudio,
    bulkAudioNotice: notice,
    bulkAudioError: error,
    isBulkUploadingAudio: isUploading,
  };
}
