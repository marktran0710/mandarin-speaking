import { unzip, type UnzipFileInfo } from "fflate";

const MAX_AUDIO_FILE_BYTES = 5_000_000;
const MAX_ZIP_FILE_BYTES = 100_000_000;
const MAX_EXTRACTED_AUDIO_BYTES = 200_000_000;

const AUDIO_MIME_BY_EXTENSION: Record<string, string> = {
  ".aac": "audio/aac",
  ".flac": "audio/flac",
  ".m4a": "audio/mp4",
  ".mp3": "audio/mpeg",
  ".oga": "audio/ogg",
  ".ogg": "audio/ogg",
  ".opus": "audio/opus",
  ".wav": "audio/wav",
  ".weba": "audio/webm",
  ".webm": "audio/webm",
};

export interface ExpandedAudioSelection {
  files: File[];
  issues: string[];
}

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot < 0 ? "" : filename.slice(dot).toLowerCase();
}

function audioFilename(filename: string): string {
  return filename.replace(/\\/g, "/").split("/").pop() ?? filename;
}

function makeAudioFile(data: BlobPart, filename: string, declaredType = ""): File {
  const mimeType = AUDIO_MIME_BY_EXTENSION[extensionOf(filename)]
    ?? (declaredType.startsWith("audio/") ? declaredType : "");
  return new File([data], audioFilename(filename), { type: mimeType });
}

function unzipAudio(file: File, remainingBytes: number): Promise<ExpandedAudioSelection> {
  return new Promise((resolve, reject) => {
    void file.arrayBuffer().then((buffer) => {
      const skipped: string[] = [];
      let acceptedBytes = 0;

      unzip(new Uint8Array(buffer), {
        filter(entry: UnzipFileInfo) {
          const name = audioFilename(entry.name);
          const extension = extensionOf(name);
          if (!name || !AUDIO_MIME_BY_EXTENSION[extension]) return false;
          if (!Number.isFinite(entry.originalSize) || entry.originalSize < 0) {
            skipped.push(`${name} has an invalid file size`);
            return false;
          }
          if (entry.originalSize > MAX_AUDIO_FILE_BYTES) {
            skipped.push(`${name} exceeds the 5 MB per-audio limit`);
            return false;
          }
          if (acceptedBytes + entry.originalSize > remainingBytes) {
            skipped.push(`${name} exceeds the 200 MB extracted-audio limit`);
            return false;
          }
          acceptedBytes += entry.originalSize;
          return true;
        },
      }, (error, entries) => {
        if (error) {
          reject(new Error(`Could not extract ${file.name}: ${error.message}`));
          return;
        }

        const extracted = Object.entries(entries).map(([path, data]) =>
          makeAudioFile(data, path, AUDIO_MIME_BY_EXTENSION[extensionOf(path)]),
        );
        if (!extracted.length && !skipped.length) {
          skipped.push(`${file.name} contains no supported audio files`);
        }
        resolve({ files: extracted, issues: skipped });
      });
    }).catch(() => reject(new Error(`Could not read ZIP file ${file.name}.`)));
  });
}

export async function expandAudioSelection(files: File[]): Promise<ExpandedAudioSelection> {
  const result: ExpandedAudioSelection = { files: [], issues: [] };
  let remainingExtractedBytes = MAX_EXTRACTED_AUDIO_BYTES;

  for (const file of files) {
    if (extensionOf(file.name) === ".zip") {
      if (file.size > MAX_ZIP_FILE_BYTES) {
        result.issues.push(`${file.name} exceeds the 100 MB ZIP limit`);
        continue;
      }
      try {
        const expanded = await unzipAudio(file, remainingExtractedBytes);
        result.files.push(...expanded.files);
        result.issues.push(...expanded.issues);
        remainingExtractedBytes -= expanded.files.reduce((total, audio) => total + audio.size, 0);
      } catch (error) {
        result.issues.push(error instanceof Error ? error.message : `Could not extract ${file.name}.`);
      }
      continue;
    }

    if (file.type.startsWith("audio/") || AUDIO_MIME_BY_EXTENSION[extensionOf(file.name)]) {
      result.files.push(makeAudioFile(file, file.name, file.type));
    } else {
      result.issues.push(`${file.name} is not a supported audio file or ZIP archive`);
    }
  }

  return result;
}
