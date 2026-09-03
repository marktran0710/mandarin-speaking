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

export function useQuizGenerationActions() {
  const { stories, setStories, level, exclusionsByStory, setExclusionsByStory, setDirtyByStory, setStatusByStory, validationByStory, setValidationByStory, setValidateStatusByStory, pendingApprovalsByKey, setPendingApprovalsByKey, setApproveStatusByStory, editTarget, setEditTarget, editDraft, setEditDraft, setEditStatus, addQuestionTarget, setAddQuestionTarget, addQuestionDraft, setAddQuestionDraft, setAddQuestionStatus, pendingCandidatesByStory, setPendingCandidatesByStory, setRevealedCountByStory, setGenerationGateNoteByStory, setGenerateStatusByStory, importInputRef, importTargetRef, setImportNoteByStory } = useQuizReviewContext();
  const onGenerate = async (story: CustomTeacherStory, topic: ReturnType<typeof storyToTopic>) => {
    const storyId = story.id;
    setGenerationGateNoteByStory((prev) => ({ ...prev, [storyId]: "" }));
    setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "generating" }));
    try {
      const plannedDistractorCandidates = planDistractorGrowth(topic);
      const plannedClozeCandidates = planClozeGrowth(topic);
      const plannedSynonymCandidates = planSynonymGrowth(topic);
      const changedTargets = (validationByStory[storyId] ?? [])
        .map((result) => changedTargetForValidation(topic, result))
        .filter((target): target is ChangedCandidateTarget => target !== null);
      const changedDistractorTargets = changedTargets.filter((target) => target.kind === "distractors");
      const changedClozeTargets = changedTargets.filter((target) => target.kind === "cloze");
      const changedSynonymTargets = changedTargets.filter((target) => target.kind === "synonym");
      const distractorCandidates = canonicalGrowthCandidates(
        plannedDistractorCandidates,
        new Set(changedDistractorTargets.map((target) => target.word)),
      );
      const clozeCandidates = canonicalGrowthCandidates(
        plannedClozeCandidates,
        new Set(changedClozeTargets.map((target) => target.word)),
      );
      const synonymCandidates = canonicalGrowthCandidates(
        plannedSynonymCandidates,
        new Set(changedSynonymTargets.map((target) => target.word)),
      );
      const toWords = (list: Array<{ word: string; translation: string; context?: string; existing: string[] }>): VocabGrowthWord[] =>
        list.map((c) => ({ word: c.word, translation: c.translation, context: c.context, avoid: c.existing }));

      const [
        rawDistractorResults,
        rawClozeResults,
        rawSynonymResults,
        changedDistractorResults,
        changedClozeResults,
        changedSynonymResults,
      ] = await Promise.all([
        distractorCandidates.length ? generateVocabDistractors(toWords(distractorCandidates)) : Promise.resolve([]),
        clozeCandidates.length ? generateVocabCloze(toWords(clozeCandidates)) : Promise.resolve([]),
        synonymCandidates.length ? generateVocabSynonym(toWords(synonymCandidates)) : Promise.resolve([]),
        Promise.all(
          changedDistractorTargets.map(async (target) => {
            const results = await generateVocabDistractors([target.growthWord]);
            const result = results.find((r) => r.word === target.word) ?? results[0];
            return result && result.distractors.length > 0 ? { target, value: result.distractors } : null;
          }),
        ),
        Promise.all(
          changedClozeTargets.map(async (target) => {
            const results = await generateVocabCloze([target.growthWord]);
            const result = results.find((r) => r.word === target.word) ?? results[0];
            return result
              ? { target, value: { sentence: result.sentence, distractors: result.distractors } }
              : null;
          }),
        ),
        Promise.all(
          changedSynonymTargets.map(async (target) => {
            const results = await generateVocabSynonym([target.growthWord]);
            const result = results.find((r) => r.word === target.word) ?? results[0];
            return result
              ? { target, value: { synonym: result.synonym, distractors: result.distractors } }
              : null;
          }),
        ),
      ]);

      const vocabulary = topic.images.flatMap((_, frameIndex) =>
        (topic.vocabulary[frameIndex] ?? []).map((word, wordIndex) => ({
          word,
          translation: topic.vocabularyTranslation?.[frameIndex]?.[wordIndex] ?? "",
        })),
      );
      const protectedMaterial = protectGeneratedQuizMaterial(vocabulary, {
        distractors: rawDistractorResults,
        cloze: rawClozeResults,
        synonym: rawSynonymResults,
      });
      const {
        distractors: distractorResults,
        cloze: clozeResults,
        synonym: synonymResults,
      } = protectedMaterial;
      if (protectedMaterial.removedCount > 0) {
        setGenerationGateNoteByStory((prev) => ({
          ...prev,
          [storyId]: `${protectedMaterial.removedCount} duplicate or answer-leaking generated value${protectedMaterial.removedCount === 1 ? " was" : "s were"} removed before review.`,
        }));
      }

      const pending: PendingCandidate[] = [];
      for (const u of buildDistractorPatchUpdates(distractorCandidates, distractorResults)) {
        const c = distractorCandidates.find((x) => x.frameIndex === u.frameIndex && x.wordIndex === u.wordIndex)!;
        const fresh = freshGeneratedStrings(u.distractors, c.existing, true);
        if (fresh.length > 0) {
          pending.push({ frameIndex: u.frameIndex, wordIndex: u.wordIndex, word: c.word, kind: "distractors", origin: "new", value: fresh, decision: "pending" });
        }
      }
      for (const u of buildClozePatchUpdates(clozeCandidates, clozeResults)) {
        const c = clozeCandidates.find((x) => x.frameIndex === u.frameIndex && x.wordIndex === u.wordIndex)!;
        const value = u.candidates[0];
        if (value && !c.existing.some((existing) => existing.trim() === value.sentence.trim())) {
          pending.push({ frameIndex: u.frameIndex, wordIndex: u.wordIndex, word: c.word, kind: "cloze", origin: "new", value, decision: "pending" });
        }
      }
      for (const u of buildSynonymPatchUpdates(synonymCandidates, synonymResults)) {
        const c = synonymCandidates.find((x) => x.frameIndex === u.frameIndex && x.wordIndex === u.wordIndex)!;
        const value = u.candidates[0];
        if (value && !c.existing.some((existing) => existing.trim() === value.synonym.trim())) {
          pending.push({ frameIndex: u.frameIndex, wordIndex: u.wordIndex, word: c.word, kind: "synonym", origin: "new", value, decision: "pending" });
        }
      }
      changedDistractorResults.forEach((item) => {
        if (!item) return;
        const fresh = freshGeneratedStrings(item.value, item.target.growthWord.avoid, true);
        if (fresh.length === 0) return;
        pending.push({
          frameIndex: item.target.frameIndex,
          wordIndex: item.target.wordIndex,
          word: item.target.word,
          kind: "distractors",
          origin: "changed",
          value: fresh,
          oldValue: item.target.currentValue,
          decision: "pending",
        });
      });
      changedClozeResults.forEach((item) => {
        if (!item) return;
        if (item.target.growthWord.avoid.some((value) => value.trim() === item.value.sentence.trim())) return;
        pending.push({
          frameIndex: item.target.frameIndex,
          wordIndex: item.target.wordIndex,
          word: item.target.word,
          kind: "cloze",
          origin: "changed",
          value: item.value,
          oldValue: item.target.currentValue,
          poolIndex: item.target.poolIndex,
          decision: "pending",
        });
      });
      changedSynonymResults.forEach((item) => {
        if (!item) return;
        if (item.target.growthWord.avoid.some((value) => value.trim() === item.value.synonym.trim())) return;
        pending.push({
          frameIndex: item.target.frameIndex,
          wordIndex: item.target.wordIndex,
          word: item.target.word,
          kind: "synonym",
          origin: "changed",
          value: item.value,
          oldValue: item.target.currentValue,
          poolIndex: item.target.poolIndex,
          decision: "pending",
        });
      });
      pending.push(...removedCandidatesFromSnapshot(storyMaterialSnapshot(story, level), topic));

      if (pending.length === 0) {
        setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "idle" }));
        return;
      }

      setPendingCandidatesByStory((prev) => ({ ...prev, [storyId]: pending }));
      setRevealedCountByStory((prev) => ({ ...prev, [storyId]: 0 }));
      setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "revealing" }));

      pending.forEach((_, i) => {
        setTimeout(() => {
          setRevealedCountByStory((prev) => ({ ...prev, [storyId]: i + 1 }));
          if (i === pending.length - 1) {
            setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "idle" }));
          }
        }, i * 260);
      });
    } catch {
      setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "error" }));
    }
  };

  const onDecideCandidate = (storyId: string, index: number, decision: "accept" | "reject") => {
    setPendingCandidatesByStory((prev) => ({
      ...prev,
      [storyId]: (prev[storyId] ?? []).map((c, i) => (i === index ? { ...c, decision } : c)),
    }));
  };

  const onUndoDecision = (storyId: string, index: number) => {
    setPendingCandidatesByStory((prev) => ({
      ...prev,
      [storyId]: (prev[storyId] ?? []).map((c, i) => (i === index ? { ...c, decision: "pending" } : c)),
    }));
  };

  const onAcceptAllPending = (storyId: string) => {
    setPendingCandidatesByStory((prev) => ({
      ...prev,
      [storyId]: (prev[storyId] ?? []).map((c) => (c.decision === "pending" ? { ...c, decision: "accept" } : c)),
    }));
  };

  const onApplyPendingCandidates = async (story: CustomTeacherStory) => {
    const storyId = story.id;
    const pending = pendingCandidatesByStory[storyId] ?? [];
    const accepted = pending.filter((c) => c.decision === "accept");
    const acceptedNew = accepted.filter((c) => c.origin === "new");
    const acceptedChanged = accepted.filter(isChangedCandidate);
    const removedExclusionAdditions: QuizExclusion[] = accepted
      .filter((c) => c.origin === "removed")
      .map((c) => ({
        word: c.word,
        kind: c.kind as QuizExclusionKind,
        index: c.poolIndex,
      }));
    const nextExclusions =
      removedExclusionAdditions.length > 0
        ? appendUniqueExclusions(exclusionsByStory[storyId] ?? [], removedExclusionAdditions)
        : exclusionsByStory[storyId] ?? [];
    setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "applying" }));
    try {
      const distractorUpdates = acceptedNew
        .filter((c) => c.kind === "distractors")
        .map((c) => ({ frameIndex: c.frameIndex, wordIndex: c.wordIndex, distractors: c.value as string[] }));
      const clozeUpdates = acceptedNew
        .filter((c) => c.kind === "cloze")
        .map((c) => ({ frameIndex: c.frameIndex, wordIndex: c.wordIndex, candidates: [c.value as { sentence: string; distractors: string[] }] }));
      const synonymUpdates = acceptedNew
        .filter((c) => c.kind === "synonym")
        .map((c) => ({ frameIndex: c.frameIndex, wordIndex: c.wordIndex, candidates: [c.value as { synonym: string; distractors: string[] }] }));

      await Promise.all([
        Promise.all([
          distractorUpdates.length ? updateVocabularyDistractors(storyId, distractorUpdates) : Promise.resolve(),
          clozeUpdates.length ? updateVocabularyCloze(storyId, clozeUpdates) : Promise.resolve(),
          synonymUpdates.length ? updateVocabularySynonym(storyId, synonymUpdates) : Promise.resolve(),
        ]),
        Promise.all(
          acceptedChanged.map((candidate) =>
            replaceQuizQuestion(
              storyId,
              candidate.frameIndex,
              candidate.wordIndex,
              candidate.kind,
              candidate.poolIndex,
              candidate.value,
            ),
          ),
        ),
        removedExclusionAdditions.length
          ? updateQuizExclusions(storyId, nextExclusions)
          : Promise.resolve(),
      ]);

      setStories((prev) =>
        prev.map((s) =>
          s.id === storyId
            ? applyChangedCandidatesLocally(applyAcceptedCandidatesLocally(s, acceptedNew), acceptedChanged)
            : s,
        ),
      );
      if (removedExclusionAdditions.length > 0) {
        setExclusionsByStory((prev) => ({ ...prev, [storyId]: nextExclusions }));
        setDirtyByStory((prev) => ({ ...prev, [storyId]: false }));
        setStatusByStory((prev) => ({ ...prev, [storyId]: "saved" }));
      }
      setPendingCandidatesByStory((prev) => ({ ...prev, [storyId]: [] }));
      setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "idle" }));
    } catch {
      setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "error" }));
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
  return { onGenerate, onDecideCandidate, onUndoDecision, onAcceptAllPending, onApplyPendingCandidates, triggerImport, onImportChange, onExport };
}
