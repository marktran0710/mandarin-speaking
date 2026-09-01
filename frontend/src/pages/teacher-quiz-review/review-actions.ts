// @ts-nocheck
import { useQuizReviewContext } from "./context";
import { approveQuizMaterial, generateVocabCloze, generateVocabDistractors, generateVocabSynonym, replaceQuizQuestion, saveQuizPendingApprovals, updateQuizExclusions, updateVocabularyCloze, updateVocabularyDistractors, updateVocabularySynonym, validateQuizMaterial } from "../../services/database";
import { buildClozePatchUpdates, buildDistractorPatchUpdates, buildSynonymPatchUpdates, planClozeGrowth, planDistractorGrowth, planSynonymGrowth } from "../../components/story-recorder/StoryRecorder";
import { buildMaterialSnapshot, storyMaterialSnapshot, withUpdatedSnapshot } from "../../utils/quizMaterialDiff";
import { buildApprovedMaterial, buildApprovedMaterialFromApprovals } from "../../utils/quizApprovedMaterial";
import { protectGeneratedQuizMaterial } from "../../utils/quizGenerationGate";
import { exportQuizMarksFile, isExcluded, readQuizMarksImportFile, toggleExclusion } from "../../utils/quizExclusions";
import { isApproved, toggleApproval } from "../../utils/quizPendingApprovals";
import { storyToTopic } from "../../utils/teacherStories";
import { applyAcceptedCandidatesLocally, applyChangedCandidatesLocally, appendUniqueExclusions, isChangedCandidate, removedCandidatesFromSnapshot } from "./model-pending";
import { applyLocalEdit, canonicalGrowthCandidates, changedTargetForValidation, freshGeneratedStrings, invalidateApprovedWord, pendingKeyFor } from "./model-core";
import { findValidation } from "./review-chrome";

export function useQuizReviewActions() {
  const { stories, setStories, level, exclusionsByStory, setExclusionsByStory, setDirtyByStory, setStatusByStory, validationByStory, setValidationByStory, setValidateStatusByStory, pendingApprovalsByKey, setPendingApprovalsByKey, setApproveStatusByStory, editTarget, setEditTarget, editDraft, setEditDraft, setEditStatus, addQuestionTarget, setAddQuestionTarget, addQuestionDraft, setAddQuestionDraft, setAddQuestionStatus, pendingCandidatesByStory, setPendingCandidatesByStory, setRevealedCountByStory, setGenerationGateNoteByStory, setGenerateStatusByStory, importInputRef, importTargetRef, setImportNoteByStory } = useQuizReviewContext();
  const onToggle = (storyId: string, mark: QuizExclusion) => {
    setExclusionsByStory((prev) => ({
      ...prev,
      [storyId]: toggleExclusion(prev[storyId] ?? [], mark),
    }));
    setDirtyByStory((prev) => ({ ...prev, [storyId]: true }));
    setStatusByStory((prev) => ({ ...prev, [storyId]: "idle" }));
  };

  const onSave = async (story: CustomTeacherStory, topic: ReturnType<typeof storyToTopic>) => {
    setStatusByStory((prev) => ({ ...prev, [story.id]: "saving" }));
    try {
      const snapshotMap = withUpdatedSnapshot(story, level, buildMaterialSnapshot(topic));
      await updateQuizExclusions(story.id, exclusionsByStory[story.id] ?? [], snapshotMap);
      setDirtyByStory((prev) => ({ ...prev, [story.id]: false }));
      setStatusByStory((prev) => ({ ...prev, [story.id]: "saved" }));
      setStories((prev) =>
        prev.map((s) => (s.id === story.id ? { ...s, quizMaterialSnapshot: snapshotMap } : s)),
      );
    } catch {
      setStatusByStory((prev) => ({ ...prev, [story.id]: "error" }));
    }
  };

  const onValidate = async (story: CustomTeacherStory, topic: ReturnType<typeof storyToTopic>) => {
    setValidateStatusByStory((prev) => ({ ...prev, [story.id]: "validating" }));
    try {
      // Unfiltered on purpose: buildApprovedMaterial with no exclusions just
      // dedupes by word (first scene occurrence), keeping each pool's
      // original index so a suspicious result maps back onto exactly the
      // item rendered below. Excluded items are skipped server-side via the
      // separate exclusions list, not by removing them from this payload.
      const words = buildApprovedMaterial(topic, []);
      const exclusions = exclusionsByStory[story.id] ?? [];
      const results = await validateQuizMaterial(story.id, words, exclusions);
      setValidationByStory((prev) => ({ ...prev, [story.id]: results }));
      // A later validation failure revokes the old local selection. Without
      // this, a checkbox saved from an earlier clean pass could remain in
      // the publish payload even though the question is now suspicious.
      const approvalKey = pendingKeyFor(story.id, level);
      const currentApprovals = pendingApprovalsByKey[approvalKey] ?? [];
      const cleanApprovals = currentApprovals.filter((approval) =>
        results.some(
          (result) =>
            result.status === "clean" &&
            result.word === approval.word &&
            (result.kind === approval.kind || (approval.kind === "distractors" && result.kind === "translation")) &&
            (result.poolIndex ?? undefined) === (approval.index ?? undefined),
        ),
      );
      if (cleanApprovals.length !== currentApprovals.length) {
        setPendingApprovalsByKey((prev) => ({ ...prev, [approvalKey]: cleanApprovals }));
        saveQuizPendingApprovals(story.id, level, cleanApprovals).catch(() => {});
      }
      setValidateStatusByStory((prev) => ({ ...prev, [story.id]: "idle" }));
    } catch {
      setValidateStatusByStory((prev) => ({ ...prev, [story.id]: "error" }));
    }
  };

  /** Whether this candidate has survived a Validate pass THIS session —
   * checking it on is gated on this; unchecking is always free. */
  const canCheck = (storyId: string, word: string, kind: QuizApprovalKind, poolIndex?: number): boolean =>
    findValidation(
      validationByStory[storyId],
      word,
      kind === "distractors" ? "translation" : kind,
      poolIndex,
    )?.status === "clean";

  const onToggleApproval = async (story: CustomTeacherStory, mark: QuizApprovalMark) => {
    const key = pendingKeyFor(story.id, level);
    const current = pendingApprovalsByKey[key] ?? [];
    const alreadyChecked = isApproved(current, mark.word, mark.kind, mark.index);
    if (!alreadyChecked && !canCheck(story.id, mark.word, mark.kind, mark.index)) return;
    const next = toggleApproval(current, mark);
    setPendingApprovalsByKey((prev) => ({ ...prev, [key]: next }));
    saveQuizPendingApprovals(story.id, level, next).catch(() => {});
  };

  /** Bulk-checks every candidate that came back clean this session —
   * suspicious ones stay individually decided, the whole point of flagging
   * them in the first place. */
  const onApproveAll = async (story: CustomTeacherStory) => {
    const key = pendingKeyFor(story.id, level);
    let next = pendingApprovalsByKey[key] ?? [];
    for (const r of validationByStory[story.id] ?? []) {
      if (r.status !== "clean") continue;
      const approvalKind = r.kind === "translation" ? "distractors" : r.kind;
      if (!isApproved(next, r.word, approvalKind, r.poolIndex)) {
        next = toggleApproval(next, { word: r.word, kind: approvalKind, index: r.poolIndex });
      }
    }
    setPendingApprovalsByKey((prev) => ({ ...prev, [key]: next }));
    saveQuizPendingApprovals(story.id, level, next).catch(() => {});
  };

  const onApprove = async (story: CustomTeacherStory, topic: ReturnType<typeof storyToTopic>) => {
    setApproveStatusByStory((prev) => ({ ...prev, [story.id]: "approving" }));
    try {
      const approvals = pendingApprovalsByKey[pendingKeyFor(story.id, level)] ?? [];
      const exclusions = exclusionsByStory[story.id] ?? [];
      const material = buildApprovedMaterialFromApprovals(topic, approvals, exclusions);
      await approveQuizMaterial(story.id, level, material);
      setApproveStatusByStory((prev) => ({ ...prev, [story.id]: "approved" }));
      setStories((prev) =>
        prev.map((s) =>
          s.id === story.id
            ? { ...s, quizApprovedSnapshot: { ...s.quizApprovedSnapshot, [level]: material } }
            : s,
        ),
      );
    } catch {
      setApproveStatusByStory((prev) => ({ ...prev, [story.id]: "error" }));
    }
  };

  const onStartEdit = (
    target: EditTarget,
    current: { distractors: string[]; sentence?: string; synonym?: string; correctAnswer?: string; pinyin?: string },
  ) => {
    setEditTarget(target);
    setEditStatus("idle");
    if (target.kind === "distractors") {
      setEditDraft({ kind: "distractors", distractors: current.distractors.join(", "), correctAnswer: current.correctAnswer });
    } else if (target.kind === "cloze") {
      setEditDraft({
        kind: "cloze",
        sentence: current.sentence ?? "",
        distractors: current.distractors.join(", "),
      });
    } else if (target.kind === "pinyin") {
      setEditDraft({ kind: "pinyin", pinyin: current.pinyin ?? "" });
    } else {
      setEditDraft({
        kind: "synonym",
        synonym: current.synonym ?? "",
        distractors: current.distractors.join(", "),
      });
    }
  };

  const onStartTranslationEdit = (target: EditTarget, translation: string) => {
    setEditTarget(target);
    setEditDraft({ kind: "translation", translation });
    setEditStatus("idle");
  };

  const onCancelEdit = () => {
    setEditTarget(null);
    setEditDraft(null);
    setEditStatus("idle");
  };

  const addDraftForKind = (kind: AddQuestionKind): AddQuestionDraft =>
    kind === "distractors"
      ? { kind, distractors: "" }
      : kind === "cloze"
      ? { kind, sentence: "", distractors: "" }
      : { kind, synonym: "", distractors: "" };

  const onStartAddQuestion = (target: AddQuestionTarget) => {
    const kind = target.availableKinds[0];
    if (!kind) return;
    setAddQuestionTarget(target);
    setAddQuestionDraft(addDraftForKind(kind));
    setAddQuestionStatus("idle");
  };

  const onCancelAddQuestion = () => {
    setAddQuestionTarget(null);
    setAddQuestionDraft(null);
    setAddQuestionStatus("idle");
  };

  const onSaveAddQuestion = async () => {
    if (!addQuestionTarget || !addQuestionDraft) return;
    setAddQuestionStatus("saving");
    const { storyId, frameIndex, wordIndex, word } = addQuestionTarget;
    const distractors = addQuestionDraft.distractors
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (distractors.length === 0) {
      setAddQuestionStatus("error");
      return;
    }

    let value: ReplaceValue;
    try {
      if (addQuestionDraft.kind === "distractors") {
        value = distractors;
        await updateVocabularyDistractors(storyId, [{ frameIndex, wordIndex, distractors }]);
      } else if (addQuestionDraft.kind === "cloze") {
        const sentence = addQuestionDraft.sentence.trim();
        if (!sentence || sentence.split(word).length !== 2) {
          setAddQuestionStatus("error");
          return;
        }
        const candidate = { sentence, distractors };
        value = candidate;
        await updateVocabularyCloze(storyId, [{ frameIndex, wordIndex, candidates: [candidate] }]);
      } else {
        const synonym = addQuestionDraft.synonym.trim();
        if (!synonym || synonym === word) {
          setAddQuestionStatus("error");
          return;
        }
        const candidate = { synonym, distractors };
        value = candidate;
        await updateVocabularySynonym(storyId, [{ frameIndex, wordIndex, candidates: [candidate] }]);
      }

      setStories((prev) =>
        prev.map((story) =>
          story.id !== storyId
            ? story
            : {
                ...story,
                frames: story.frames.map((frame, index) =>
                  index === frameIndex
                    ? applyLocalEdit(frame, addQuestionDraft.kind, wordIndex, 0, value)
                    : frame,
                ),
              },
        ),
      );
      setValidationByStory((prev) => ({ ...prev, [storyId]: [] }));
      setAddQuestionTarget(null);
      setAddQuestionDraft(null);
      setAddQuestionStatus("idle");
    } catch {
      setAddQuestionStatus("error");
    }
  };

  const onSaveEdit = async () => {
    if (!editTarget || !editDraft) return;
    setEditStatus("saving");
    const distractors = "distractors" in editDraft
      ? editDraft.distractors.split(",").map((d) => d.trim()).filter(Boolean)
      : [];
    const value: ReplaceValue =
      editDraft.kind === "translation"
        ? editDraft.translation.trim()
        : editDraft.kind === "pinyin"
        ? editDraft.pinyin.trim()
        : editDraft.kind === "distractors"
        ? distractors
        : editDraft.kind === "cloze"
          ? { sentence: editDraft.sentence.trim(), distractors }
          : { synonym: editDraft.synonym.trim(), distractors };

    try {
      if (editTarget.kind === "distractors" && editDraft.kind === "distractors" && editDraft.correctAnswer !== undefined) {
        await replaceQuizQuestion(editTarget.storyId, editTarget.frameIndex, editTarget.wordIndex, "translation", undefined, editDraft.correctAnswer.trim(), editTarget.translationField);
      }
      if (editTarget.kind === "translation") {
        await replaceQuizQuestion(
          editTarget.storyId,
          editTarget.frameIndex,
          editTarget.wordIndex,
          editTarget.kind,
          editTarget.poolIndex,
          value,
          editTarget.translationField,
        );
      } else if (editTarget.kind === "pinyin") {
        await replaceQuizQuestion(
          editTarget.storyId,
          editTarget.frameIndex,
          editTarget.wordIndex,
          "pinyin",
          undefined,
          value,
          undefined,
          editTarget.pinyinField,
        );
      } else {
        await replaceQuizQuestion(
          editTarget.storyId,
          editTarget.frameIndex,
          editTarget.wordIndex,
          editTarget.kind,
          editTarget.poolIndex,
          value,
        );
      }
      setStories((prev) =>
        prev.map((s) =>
          s.id === editTarget.storyId
            ? (() => {
                const updated: CustomTeacherStory = {
                ...s,
                frames: s.frames.map((frame, fi) =>
                  fi === editTarget.frameIndex
                    ? (() => {
                        const edited = applyLocalEdit(
                          frame,
                          editTarget.kind,
                          editTarget.wordIndex,
                          editTarget.poolIndex,
                          value,
                          editTarget.translationField,
                          editTarget.pinyinField,
                        );
                        return editTarget.kind === "distractors" && editDraft.kind === "distractors" && editDraft.correctAnswer !== undefined
                          ? applyLocalEdit(edited, "translation", editTarget.wordIndex, undefined, editDraft.correctAnswer.trim(), editTarget.translationField)
                          : edited;
                      })()
                    : frame,
                ),
                };
                return editTarget.kind === "translation"
                  ? invalidateApprovedWord(updated, editTarget.word)
                  : updated;
              })()
            : s,
        ),
      );
      // An edited candidate needs a fresh Validate before it can be checked
      // again — drop any stale result and un-check it if it was checked.
      setValidationByStory((prev) => ({
        ...prev,
        [editTarget.storyId]: (prev[editTarget.storyId] ?? []).filter((r) =>
          editTarget.kind === "translation" || editTarget.kind === "pinyin"
            ? r.word !== editTarget.word
            : !(r.word === editTarget.word && r.kind === editTarget.kind && (r.poolIndex ?? undefined) === editTarget.poolIndex),
        ),
      }));
      const key = pendingKeyFor(editTarget.storyId, level);
      const current = pendingApprovalsByKey[key] ?? [];
      const next = editTarget.kind === "pinyin"
        ? current
        : editTarget.kind === "translation"
        ? current.filter((approval) => approval.word !== editTarget.word)
        : isApproved(current, editTarget.word, editTarget.kind, editTarget.poolIndex)
          ? toggleApproval(current, { word: editTarget.word, kind: editTarget.kind, index: editTarget.poolIndex })
          : current;
      if (next !== current) {
        setPendingApprovalsByKey((prev) => ({ ...prev, [key]: next }));
        saveQuizPendingApprovals(editTarget.storyId, level, next).catch(() => {});
      }
      setEditTarget(null);
      setEditDraft(null);
      setEditStatus("idle");
    } catch {
      setEditStatus("error");
    }
  };

  /** Runs the same growth-planning + generation calls StoryRecorder's
   * background pool growth uses (planXGrowth -> generateVocabX), but stages
   * every result as pending instead of merging it in immediately — nothing
   * is persisted until the teacher accepts it and clicks Apply. Only tops
   * up words under each pool's cap, so an already-covered word costs
   * nothing to re-run; that's what makes this safe to call both the first
   * time (every word is under cap) and after a story edit (only new/thin
   * words still qualify). */
  return { onToggle, onSave, onValidate, canCheck, onToggleApproval, onApproveAll, onApprove, onStartEdit, onStartTranslationEdit, onCancelEdit, addDraftForKind, onStartAddQuestion, onCancelAddQuestion, onSaveAddQuestion, onSaveEdit };
}
