// @ts-nocheck
import { useQuizReviewContext } from "./context";
import { approveQuizMaterial, listCustomStories, replaceQuizQuestion, saveQuizPendingApprovals, updateQuizExclusions, updateVocabularyCloze, updateVocabularyDistractors, updateVocabularySynonym } from "../../services/database";
import { buildMaterialSnapshot, withUpdatedSnapshot } from "../../utils/quizMaterialDiff";
import { buildApprovedMaterial, buildApprovedMaterialFromApprovals } from "../../utils/quizApprovedMaterial";
import { exportQuizMarksFile, readQuizMarksImportFile, toggleExclusion } from "../../utils/quizExclusions";
import { isApproved, toggleApproval } from "../../utils/quizPendingApprovals";
import { storyToTopic } from "../../utils/teacherStories";
import { applyLocalEdit, invalidateApprovedWord, pendingKeyFor } from "./model-core";
import { fewerThanAttempted, parseQuizMaterialCsv } from "./material-upload";

export function useQuizReviewActions() {
  const { stories, setStories, level, exclusionsByStory, setExclusionsByStory, setDirtyByStory, setStatusByStory, pendingApprovalsByKey, setPendingApprovalsByKey, setApproveStatusByStory, editTarget, setEditTarget, editDraft, setEditDraft, setEditStatus, addQuestionTarget, setAddQuestionTarget, addQuestionDraft, setAddQuestionDraft, setAddQuestionStatus, importInputRef, importTargetRef, setImportNoteByStory, uploadInputRef, uploadTargetRef, setUploadNoteByStory } = useQuizReviewContext();
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

  const onToggleApproval = async (story: CustomTeacherStory, mark: QuizApprovalMark) => {
    const key = pendingKeyFor(story.id, level);
    const current = pendingApprovalsByKey[key] ?? [];
    const next = toggleApproval(current, mark);
    setPendingApprovalsByKey((prev) => ({ ...prev, [key]: next }));
    saveQuizPendingApprovals(story.id, level, next).catch(() => {});
  };

  /** Checks every question currently in the story's material — there's no
   * AI validation pass to gate on anymore, so "approve all" just means all
   * of the teacher's own typed/uploaded content for this word. */
  const onApproveAll = async (story: CustomTeacherStory, topic: ReturnType<typeof storyToTopic>) => {
    const key = pendingKeyFor(story.id, level);
    const exclusions = exclusionsByStory[story.id] ?? [];
    let next = pendingApprovalsByKey[key] ?? [];
    for (const entry of buildApprovedMaterial(topic, exclusions)) {
      if (entry.distractors.length > 0 && !isApproved(next, entry.word, "distractors")) {
        next = toggleApproval(next, { word: entry.word, kind: "distractors" });
      }
      entry.cloze.forEach((_candidate, index) => {
        if (!isApproved(next, entry.word, "cloze", index)) {
          next = toggleApproval(next, { word: entry.word, kind: "cloze", index });
        }
      });
      entry.synonym.forEach((_candidate, index) => {
        if (!isApproved(next, entry.word, "synonym", index)) {
          next = toggleApproval(next, { word: entry.word, kind: "synonym", index });
        }
      });
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
      const key = pendingKeyFor(editTarget.storyId, level);
      const current = pendingApprovalsByKey[key] ?? [];
      const next = editTarget.kind === "pinyin"
        ? current
        : editTarget.kind === "translation"
        ? current.filter((approval) => approval.word !== editTarget.word)
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

  const triggerImport = (storyId: string) => {
    importTargetRef.current = storyId;
    importInputRef.current?.click();
  };

  const onImportChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const storyId = importTargetRef.current;
    e.target.value = "";
    if (!file || !storyId) return;
    try {
      const parsed = await readQuizMarksImportFile(file);
      setExclusionsByStory((prev) => ({ ...prev, [storyId]: parsed.exclusions }));
      setDirtyByStory((prev) => ({ ...prev, [storyId]: true }));
      setStatusByStory((prev) => ({ ...prev, [storyId]: "idle" }));
      setImportNoteByStory((prev) => ({
        ...prev,
        [storyId]:
          parsed.storyId && parsed.storyId !== storyId
            ? `File exported from a different story (${parsed.storyId})`
            : `Imported ${parsed.exclusions.length} marks — Save to apply`,
      }));
    } catch (err) {
      setImportNoteByStory((prev) => ({
        ...prev,
        [storyId]: err instanceof Error ? err.message : "Invalid marks file",
      }));
    }
  };

  const onExport = (story: CustomTeacherStory) => {
    exportQuizMarksFile(story, exclusionsByStory[story.id] ?? []);
  };

  const triggerMaterialUpload = (storyId: string) => {
    uploadTargetRef.current = storyId;
    uploadInputRef.current?.click();
  };

  /** Bulk version of "Add question": parses a teacher-prepared CSV and tops
   * up the same per-word pools the manual add form writes to, via the same
   * PATCH endpoints — no AI, no new backend path. */
  const onMaterialUploadChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const storyId = uploadTargetRef.current;
    e.target.value = "";
    if (!file || !storyId) return;
    const story = stories.find((s) => s.id === storyId);
    if (!story) return;
    let result: ReturnType<typeof parseQuizMaterialCsv>;
    let beforeTopic: ReturnType<typeof storyToTopic>;
    try {
      const text = await file.text();
      beforeTopic = storyToTopic(story, level);
      result = parseQuizMaterialCsv(text, beforeTopic);
      await Promise.all([
        result.distractorUpdates.length ? updateVocabularyDistractors(storyId, result.distractorUpdates) : Promise.resolve(),
        result.clozeUpdates.length ? updateVocabularyCloze(storyId, result.clozeUpdates) : Promise.resolve(),
        result.synonymUpdates.length ? updateVocabularySynonym(storyId, result.synonymUpdates) : Promise.resolve(),
      ]);
    } catch (err) {
      setUploadNoteByStory((prev) => ({ ...prev, [storyId]: err instanceof Error ? err.message : "Could not read that file." }));
      return;
    }

    // The upload itself already succeeded above — a failure past this point
    // must not be reported as an upload failure. Pool merges happen
    // server-side (top-up + dedupe + cap), so refetch rather than
    // re-deriving that logic locally; if the refetch itself fails, the
    // teacher still gets the real success note and sees the new material
    // on their next reload instead of a misleading error.
    let underfilledWords: string[] = [];
    try {
      const refreshed = await listCustomStories();
      const updatedStory = (refreshed as CustomTeacherStory[]).find((s) => s.id === storyId);
      if (updatedStory) {
        setStories((prev) => prev.map((s) => (s.id === storyId ? updatedStory : s)));
        underfilledWords = fewerThanAttempted(beforeTopic, storyToTopic(updatedStory, level), result);
      }
    } catch (err) {
      console.warn("Could not refresh story after quiz material upload:", err);
    }

    const parts = [
      result.addedCounts.distractors ? `${result.addedCounts.distractors} distractor set${result.addedCounts.distractors === 1 ? "" : "s"}` : "",
      result.addedCounts.cloze ? `${result.addedCounts.cloze} cloze` : "",
      result.addedCounts.synonym ? `${result.addedCounts.synonym} synonym` : "",
    ].filter(Boolean);
    const added = parts.length ? `Added ${parts.join(", ")}.` : "Nothing to add.";
    const notFound = result.notFoundWords.length ? ` Not found in this story: ${result.notFoundWords.join("、")}.` : "";
    const skippedDetail = result.skipped.length
      ? ` Skipped ${result.skipped.length} row${result.skipped.length === 1 ? "" : "s"}: ${result.skipped
          .slice(0, 5)
          .map((row) => `row ${row.row} (${row.word || "?"}/${row.kind || "?"}): ${row.reason}`)
          .join("; ")}${result.skipped.length > 5 ? `; +${result.skipped.length - 5} more` : ""}.`
      : "";
    const underfilledNote = underfilledWords.length
      ? ` Note: not everything uploaded for ${underfilledWords.join("、")} may have been added — duplicates or a per-word pool limit.`
      : "";
    setUploadNoteByStory((prev) => ({ ...prev, [storyId]: `${added}${notFound}${skippedDetail}${underfilledNote}` }));
  };

  return { onToggle, onSave, onToggleApproval, onApproveAll, onApprove, onStartEdit, onStartTranslationEdit, onCancelEdit, addDraftForKind, onStartAddQuestion, onCancelAddQuestion, onSaveAddQuestion, onSaveEdit, triggerImport, onImportChange, onExport, triggerMaterialUpload, onMaterialUploadChange };
}
