// @ts-nocheck
import { GENERATED_POOL_FIELD } from "./constants";
import { applyLocalEdit, freshGeneratedStrings } from "./model-core";

function removedCandidatesFromSnapshot(snapshot: MaterialSnapshotEntry[] | null, topic: ReviewTopic): PendingCandidate[] {
  if (!snapshot) return [];
  const currentWords = new Set<string>();
  topic.images.forEach((_, si) => {
    (topic.vocabulary[si] || []).forEach((word) => currentWords.add(word));
  });

  const pending: PendingCandidate[] = [];
  for (const entry of snapshot) {
    if (currentWords.has(entry.word)) continue;
    if (entry.distractors.length > 0) {
      pending.push({
        frameIndex: -1,
        wordIndex: -1,
        word: entry.word,
        kind: "distractors",
        origin: "removed",
        value: [...entry.distractors],
        decision: "pending",
      });
    }
    entry.cloze.forEach((value, poolIndex) => {
      pending.push({
        frameIndex: -1,
        wordIndex: -1,
        word: entry.word,
        kind: "cloze",
        origin: "removed",
        value: { sentence: value.sentence, distractors: [...value.distractors] },
        poolIndex,
        decision: "pending",
      });
    });
    entry.synonym.forEach((value, poolIndex) => {
      pending.push({
        frameIndex: -1,
        wordIndex: -1,
        word: entry.word,
        kind: "synonym",
        origin: "removed",
        value: { synonym: value.synonym, distractors: [...value.distractors] },
        poolIndex,
        decision: "pending",
      });
    });
  }
  return pending;
}

/** Appends every accepted candidate into a local copy of the story's
 * frames, mirroring what the merge PATCH endpoints do server-side — so
 * storyToTopic recomputes with the new material without waiting on a
 * refetch. Pure: returns a new story, doesn't mutate the one passed in. */
function applyAcceptedCandidatesLocally(story: CustomTeacherStory, accepted: PendingCandidate[]): CustomTeacherStory {
  const caps: Record<GeneratedKind, number> = {
    distractors: 8,
    cloze: 1,
    synonym: 1,
  };
  let frames = story.frames;
  for (const candidate of accepted) {
    if (candidate.origin !== "new") continue;
    frames = frames.map((frame, fi) => {
      if (fi !== candidate.frameIndex) return frame;
      const field = GENERATED_POOL_FIELD[candidate.kind];
      const pool: unknown[] = JSON.parse((frame[field] as string | undefined) || "[]");
      while (pool.length <= candidate.wordIndex) pool.push([]);
      if (candidate.kind === "distractors") {
        const existing = Array.isArray(pool[candidate.wordIndex]) ? (pool[candidate.wordIndex] as string[]) : [];
        pool[candidate.wordIndex] = [
          ...existing,
          ...freshGeneratedStrings(
            candidate.value as string[],
            existing,
            candidate.kind === "distractors",
          ),
        ].slice(0, caps[candidate.kind]);
      } else {
        const existing = Array.isArray(pool[candidate.wordIndex])
          ? (pool[candidate.wordIndex] as Array<{ sentence?: string; synonym?: string }>)
          : [];
        const key = candidate.kind === "cloze"
          ? (candidate.value as { sentence: string }).sentence.trim()
          : (candidate.value as { synonym: string }).synonym.trim();
        const duplicate = existing.some((item) =>
          (candidate.kind === "cloze" ? item.sentence : item.synonym)?.trim() === key,
        );
        pool[candidate.wordIndex] = duplicate || !key
          ? existing
          : [...existing, candidate.value].slice(0, caps[candidate.kind]);
      }
      return { ...frame, [field]: JSON.stringify(pool) };
    });
  }
  return { ...story, frames };
}

function isChangedCandidate(
  candidate: PendingCandidate,
): candidate is PendingCandidate & { kind: QuizApprovalKind; value: ReplaceValue } {
  return candidate.origin === "changed";
}

function applyChangedCandidatesLocally(story: CustomTeacherStory, accepted: PendingCandidate[]): CustomTeacherStory {
  let frames = story.frames;
  for (const candidate of accepted) {
    if (!isChangedCandidate(candidate)) continue;
    frames = frames.map((frame, fi) =>
      fi === candidate.frameIndex
        ? applyLocalEdit(frame, candidate.kind, candidate.wordIndex, candidate.poolIndex, candidate.value)
        : frame,
    );
  }
  return { ...story, frames };
}

function appendUniqueExclusions(exclusions: QuizExclusion[], additions: QuizExclusion[]): QuizExclusion[] {
  const next = [...exclusions];
  for (const addition of additions) {
    if (
      !next.some(
        (exclusion) =>
          exclusion.word === addition.word &&
          exclusion.kind === addition.kind &&
          exclusion.index === addition.index,
      )
    ) {
      next.push(addition);
    }
  }
  return next;
}


export { removedCandidatesFromSnapshot, applyAcceptedCandidatesLocally, isChangedCandidate, applyChangedCandidatesLocally, appendUniqueExclusions };
