import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";
import "./TeacherQuizReviewPage.css";
import {
  approveQuizMaterial,
  canUseDatabase,
  generateVocabCloze,
  generateVocabDistractors,
  generateVocabLookalike,
  generateVocabSynonym,
  listCustomStories,
  replaceQuizQuestion,
  saveQuizPendingApprovals,
  updateQuizExclusions,
  updateVocabularyCloze,
  updateVocabularyDistractors,
  updateVocabularyLookalike,
  updateVocabularySynonym,
  validateQuizMaterial,
  type VocabGrowthWord,
  type QuizValidateResultItem,
} from "../services/database";
import {
  buildClozePatchUpdates,
  buildDistractorPatchUpdates,
  buildLookalikePatchUpdates,
  buildSynonymPatchUpdates,
  planClozeGrowth,
  planDistractorGrowth,
  planLookalikeGrowth,
  planSynonymGrowth,
} from "../components/StoryRecorder";
import {
  loadCustomStories,
  storyHasTierContent,
  storyToTopic,
  type CustomStoryFrame,
  type CustomTeacherStory,
  type StoryDifficultyLevel,
} from "../utils/teacherStories";
import {
  exportQuizMarksFile,
  isExcluded,
  readQuizMarksImportFile,
  storyQuizExclusions,
  toggleExclusion,
  type QuizExclusion,
  type QuizExclusionKind,
} from "../utils/quizExclusions";
import {
  buildMaterialSnapshot,
  diffWord,
  storyMaterialSnapshot,
  withUpdatedSnapshot,
  type MaterialDiffStatus,
} from "../utils/quizMaterialDiff";
import { buildApprovedMaterial, buildApprovedMaterialFromApprovals } from "../utils/quizApprovedMaterial";
import {
  isApproved,
  storyPendingApprovals,
  toggleApproval,
  type QuizApprovalKind,
  type QuizApprovalMark,
} from "../utils/quizPendingApprovals";
import { lessonTitle } from "../utils/lessonGroups";

/** Teacher quiz review: every piece of material the vocab quiz can build
 * questions from, per lesson and difficulty tier, with a 🗑 toggle to mark
 * bad items. Marks persist per story (custom_stories.quiz_exclusions) and
 * the quiz never builds questions from marked material. Also diffs live
 * material against the snapshot from each story's last save, so a teacher
 * revisiting a lesson can see what's 🆕 new or ✎ changed since they last
 * reviewed it, and export/import a story's marks as a JSON file.
 *
 * Reached from the teacher shell: Materials → Quiz Review. */

interface LessonReviewGroup {
  lessonNumber: number | null;
  stories: CustomTeacherStory[];
}

function lessonKeyFor(lessonNumber: number | null): string {
  return lessonNumber === null ? "other" : String(lessonNumber);
}

function lessonOptionLabel(lessonNumber: number | null): string {
  if (lessonNumber === null) return "其他";
  return `第${lessonNumber}課 ${lessonTitle(lessonNumber).zh}`;
}

/** Groups published stories into lesson rows: numbered lessons ascending,
 * then one 其他 row for stories without a lesson (omitted when empty).
 * Mirrors lessonGroups.ts's groupTopicsByLesson, but over raw stories
 * (this page reviews every tier of a story, not one picked Topic). */
function groupStoriesByLesson(stories: CustomTeacherStory[]): LessonReviewGroup[] {
  const numbered = new Map<number, CustomTeacherStory[]>();
  const unassigned: CustomTeacherStory[] = [];
  for (const story of stories) {
    if (story.lessonNumber != null) {
      const list = numbered.get(story.lessonNumber) ?? [];
      list.push(story);
      numbered.set(story.lessonNumber, list);
    } else {
      unassigned.push(story);
    }
  }
  const groups: LessonReviewGroup[] = [...numbered.entries()]
    .sort(([a], [b]) => a - b)
    .map(([lessonNumber, groupStories]) => ({ lessonNumber, stories: groupStories }));
  if (unassigned.length > 0) {
    groups.push({ lessonNumber: null, stories: unassigned });
  }
  return groups;
}

function diffBadge(status: MaterialDiffStatus | undefined) {
  if (!status || status === "kept") return null;
  return (
    <span className={`tqr-diff-badge tqr-diff-${status}`}>
      {status === "new" ? "🆕" : "✎"}
    </span>
  );
}

/** Looks up a word/kind/poolIndex in the last Validate pass — undefined
 * means "not checked yet", not "clean". Duplicate words across scenes share
 * one lookup key (matches /quiz/validate's response shape, which doesn't
 * carry scene position), the same inertness a duplicate word already has
 * for the live quiz (collectQuizEntries keeps only the first occurrence). */
function findValidation(
  results: QuizValidateResultItem[] | undefined,
  word: string,
  kind: QuizValidateResultItem["kind"],
  poolIndex?: number,
): QuizValidateResultItem | undefined {
  return results?.find(
    (r) => r.word === word && r.kind === kind && (r.poolIndex ?? undefined) === poolIndex,
  );
}

/** Three-state status badge for one question: not checked yet (no result),
 * clean, or suspicious with the judge's reason. */
function questionStatusBadge(result: QuizValidateResultItem | undefined) {
  if (!result) {
    return (
      <span className="tqr-status-badge is-unchecked">
        <BiLabel zh="尚未檢查" en="Not checked" />
      </span>
    );
  }
  if (result.status === "clean") {
    return (
      <span className="tqr-status-badge is-clean">
        <BiLabel zh="✓ 乾淨" en="✓ Clean" />
      </span>
    );
  }
  return (
    <span className="tqr-status-badge is-suspicious">
      <BiLabel zh="⚠ 可疑" en="⚠ Suspicious" />
      <span className="tqr-status-reason">{result.reason}</span>
    </span>
  );
}

type SaveStatus = "idle" | "saving" | "saved" | "error";
type ValidateStatus = "idle" | "validating" | "error";
type ApproveStatus = "idle" | "approving" | "approved" | "error";

/** Which candidate an open inline-edit form is editing. Only one at a time
 * across the whole page — keeps the state simple and matches how a teacher
 * actually works (fix one thing, then the next). */
interface EditTarget {
  storyId: string;
  frameIndex: number;
  wordIndex: number;
  word: string;
  kind: QuizApprovalKind;
  poolIndex?: number;
}

type EditDraft =
  | { kind: "distractors"; distractors: string }
  | { kind: "cloze"; sentence: string; distractors: string }
  | { kind: "synonym"; synonym: string; distractors: string };

function pendingKeyFor(storyId: string, level: StoryDifficultyLevel): string {
  return `${storyId}:${level}`;
}

type ReplaceValue =
  | string[]
  | { sentence: string; distractors: string[] }
  | { synonym: string; distractors: string[] };

const POOL_FIELD: Record<QuizApprovalKind, keyof CustomStoryFrame> = {
  distractors: "vocabularyDistractors",
  cloze: "vocabularyCloze",
  synonym: "vocabularySynonym",
};

/** Applies a replace-in-place edit to a frame's local copy, mirroring what
 * routers/stories.py's replace_quiz_question just wrote to the database —
 * so storyToTopic recomputes with the new content without waiting on a
 * refetch. Pure: returns a new frame, doesn't mutate the one passed in. */
function applyLocalEdit(
  frame: CustomStoryFrame,
  kind: QuizApprovalKind,
  wordIndex: number,
  poolIndex: number | undefined,
  value: ReplaceValue,
): CustomStoryFrame {
  const field = POOL_FIELD[kind];
  const pool: unknown[] = JSON.parse((frame[field] as string | undefined) || "[]");
  while (pool.length <= wordIndex) pool.push([]);
  if (kind === "distractors") {
    pool[wordIndex] = value;
  } else {
    const candidates = Array.isArray(pool[wordIndex]) ? [...(pool[wordIndex] as unknown[])] : [];
    candidates[poolIndex ?? 0] = value;
    pool[wordIndex] = candidates;
  }
  return { ...frame, [field]: JSON.stringify(pool) };
}

/** Kind of a freshly-generated candidate awaiting accept/reject — a
 * superset of QuizApprovalKind since lookalike has no approve-checkbox of
 * its own but is still something Generate/Update Questions can produce. */
type GeneratedKind = "distractors" | "cloze" | "synonym" | "lookalike";

const GENERATED_POOL_FIELD: Record<GeneratedKind, keyof CustomStoryFrame> = {
  distractors: "vocabularyDistractors",
  cloze: "vocabularyCloze",
  synonym: "vocabularySynonym",
  lookalike: "vocabularyLookalike",
};

interface PendingCandidate {
  frameIndex: number;
  wordIndex: number;
  word: string;
  kind: GeneratedKind;
  // distractors/lookalike: the whole new batch to append (matches how the
  // merge endpoints below already top up a pool). cloze/synonym: one new
  // candidate (the generation endpoint only ever returns one at a time).
  value: string[] | { sentence: string; distractors: string[] } | { synonym: string; distractors: string[] };
  decision: "pending" | "accept" | "reject";
}

/** Appends every accepted candidate into a local copy of the story's
 * frames, mirroring what the merge PATCH endpoints do server-side — so
 * storyToTopic recomputes with the new material without waiting on a
 * refetch. Pure: returns a new story, doesn't mutate the one passed in. */
function applyAcceptedCandidatesLocally(story: CustomTeacherStory, accepted: PendingCandidate[]): CustomTeacherStory {
  let frames = story.frames;
  for (const candidate of accepted) {
    frames = frames.map((frame, fi) => {
      if (fi !== candidate.frameIndex) return frame;
      const field = GENERATED_POOL_FIELD[candidate.kind];
      const pool: unknown[] = JSON.parse((frame[field] as string | undefined) || "[]");
      while (pool.length <= candidate.wordIndex) pool.push([]);
      if (candidate.kind === "distractors" || candidate.kind === "lookalike") {
        const existing = Array.isArray(pool[candidate.wordIndex]) ? (pool[candidate.wordIndex] as string[]) : [];
        pool[candidate.wordIndex] = [...existing, ...(candidate.value as string[])];
      } else {
        const existing = Array.isArray(pool[candidate.wordIndex]) ? (pool[candidate.wordIndex] as unknown[]) : [];
        pool[candidate.wordIndex] = [...existing, candidate.value];
      }
      return { ...frame, [field]: JSON.stringify(pool) };
    });
  }
  return { ...story, frames };
}

/** Renders one pending candidate's content — a coherent prompt+options for
 * cloze/synonym (mirrors questionRow's already-persisted version), or a
 * plain new-items list for distractors/lookalike, which aren't single
 * questions so much as pool top-ups. */
function renderPendingPrompt(candidate: PendingCandidate) {
  if (candidate.kind === "distractors" || candidate.kind === "lookalike") {
    const items = candidate.value as string[];
    return (
      <p className="tqr-qprompt" lang="zh-Hant">
        {candidate.kind === "distractors" ? (
          <BiLabel zh="新增干擾選項：" en="New distractors: " />
        ) : (
          <BiLabel zh="新增形近字：" en="New look-alikes: " />
        )}
        {items.join("、")}
      </p>
    );
  }
  if (candidate.kind === "cloze") {
    const value = candidate.value as { sentence: string; distractors: string[] };
    return (
      <>
        <p className="tqr-qprompt" lang="zh-Hant">
          {value.sentence.replace(candidate.word, "＿＿＿")}
          <br />
          <span className="tqr-qprompt-en">Which word fills the blank?</span>
        </p>
        <div className="tqr-qoptions">
          <span className="tqr-opt is-correct">{candidate.word}</span>
          {value.distractors.map((d, i) => (
            <span className="tqr-opt" key={i}>{d}</span>
          ))}
        </div>
      </>
    );
  }
  const value = candidate.value as { synonym: string; distractors: string[] };
  return (
    <>
      <p className="tqr-qprompt" lang="zh-Hant">
        哪一個字跟「{candidate.word}」意思一樣？
        <br />
        <span className="tqr-qprompt-en">Which word means the same as "{candidate.word}"?</span>
      </p>
      <div className="tqr-qoptions">
        <span className="tqr-opt is-correct">{value.synonym}</span>
        {value.distractors.map((d, i) => (
          <span className="tqr-opt" key={i}>{d}</span>
        ))}
      </div>
    </>
  );
}

export interface QuizReviewJump {
  lessonNumber: number | null;
  /** Distinguishes repeat jumps to the same lesson — the effect keys off
   * this, not lessonNumber, so a second click still re-triggers it. */
  nonce: number;
}

export default function TeacherQuizReviewPage({
  jumpToLesson,
}: {
  jumpToLesson?: QuizReviewJump | null;
} = {}) {
  const [stories, setStories] = useState<CustomTeacherStory[]>([]);
  const [lessonKey, setLessonKey] = useState<string>("");
  const [level, setLevel] = useState<StoryDifficultyLevel>("easy");
  const [onlyChanges, setOnlyChanges] = useState(false);
  const [exclusionsByStory, setExclusionsByStory] = useState<Record<string, QuizExclusion[]>>({});
  const [dirtyByStory, setDirtyByStory] = useState<Record<string, boolean>>({});
  const [statusByStory, setStatusByStory] = useState<Record<string, SaveStatus>>({});
  const [importNoteByStory, setImportNoteByStory] = useState<Record<string, string>>({});
  const [validationByStory, setValidationByStory] = useState<Record<string, QuizValidateResultItem[]>>({});
  const [validateStatusByStory, setValidateStatusByStory] = useState<Record<string, ValidateStatus>>({});
  const [approveStatusByStory, setApproveStatusByStory] = useState<Record<string, ApproveStatus>>({});
  // Keyed by `${storyId}:${level}` (see pendingKeyFor) — approvals are
  // tier-specific, unlike exclusions above.
  const [pendingApprovalsByKey, setPendingApprovalsByKey] = useState<Record<string, QuizApprovalMark[]>>({});
  const [editTarget, setEditTarget] = useState<EditTarget | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [editStatus, setEditStatus] = useState<"idle" | "saving" | "error">("idle");
  const [pendingCandidatesByStory, setPendingCandidatesByStory] = useState<Record<string, PendingCandidate[]>>({});
  const [revealedCountByStory, setRevealedCountByStory] = useState<Record<string, number>>({});
  const [generateStatusByStory, setGenerateStatusByStory] = useState<
    Record<string, "idle" | "generating" | "revealing" | "applying" | "error">
  >({});
  const importInputRef = useRef<HTMLInputElement>(null);
  const importTargetRef = useRef<string | null>(null);

  useEffect(() => {
    const local = loadCustomStories();
    const apply = (list: CustomTeacherStory[]) => {
      setStories(list.filter((s) => s.published));
    };
    apply(local);
    if (canUseDatabase()) {
      listCustomStories().then((db) => apply(db as CustomTeacherStory[])).catch(() => {});
    }
  }, []);

  // Seed per-story review state for any story we haven't seen yet, without
  // clobbering marks the teacher is already mid-editing in another story's
  // section on this same page.
  useEffect(() => {
    setExclusionsByStory((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const story of stories) {
        if (!(story.id in next)) {
          next[story.id] = storyQuizExclusions(story);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [stories]);

  // Same seed-once pattern, but keyed by story+tier since approvals are
  // tier-specific — visiting a new tier for the first time seeds it from
  // the server; a later `stories` refresh (e.g. after Approve & Publish)
  // must not clobber approvals already toggled this session.
  useEffect(() => {
    setPendingApprovalsByKey((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const story of stories) {
        const key = pendingKeyFor(story.id, level);
        if (!(key in next)) {
          next[key] = storyPendingApprovals(story, level);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [stories, level]);

  const lessonGroups = useMemo(() => groupStoriesByLesson(stories), [stories]);

  useEffect(() => {
    if (lessonGroups.length === 0) return;
    setLessonKey((current) =>
      current && lessonGroups.some((g) => lessonKeyFor(g.lessonNumber) === current)
        ? current
        : lessonKeyFor(lessonGroups[0].lessonNumber),
    );
  }, [lessonGroups]);

  const currentGroup = lessonGroups.find((g) => lessonKeyFor(g.lessonNumber) === lessonKey);

  // Reset back to Easy whenever the lesson changes — a level the new
  // lesson doesn't support would otherwise leave the page looking empty.
  useEffect(() => {
    setLevel("easy");
  }, [lessonKey]);

  // Deep-link from StoryBuilderSection's post-save "Go to Quiz Review"
  // banner — jumps straight to the lesson the just-saved story belongs to,
  // instead of leaving the teacher to find it in the dropdown again. Keyed
  // on the nonce so clicking the banner twice for the same lesson still works.
  useEffect(() => {
    if (!jumpToLesson) return;
    setLessonKey(lessonKeyFor(jumpToLesson.lessonNumber));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpToLesson?.nonce]);

  // A validate pass is tier-specific (it checks that tier's material) — a
  // leftover result from Easy would otherwise mislabel Medium's pools after
  // switching, since both share the same word/kind/poolIndex lookup keys.
  useEffect(() => {
    setValidationByStory({});
    setEditTarget(null);
    setEditDraft(null);
  }, [level]);

  const levels: StoryDifficultyLevel[] = useMemo(() => {
    if (!currentGroup) return ["easy"];
    const out: StoryDifficultyLevel[] = ["easy"];
    if (currentGroup.stories.some((s) => storyHasTierContent(s, "medium"))) out.push("medium");
    if (currentGroup.stories.some((s) => storyHasTierContent(s, "hard"))) out.push("hard");
    return out;
  }, [currentGroup]);

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
      setValidateStatusByStory((prev) => ({ ...prev, [story.id]: "idle" }));
    } catch {
      setValidateStatusByStory((prev) => ({ ...prev, [story.id]: "error" }));
    }
  };

  /** Whether this candidate has survived a Validate pass THIS session —
   * checking it on is gated on this; unchecking is always free. */
  const canCheck = (storyId: string, word: string, kind: QuizApprovalKind, poolIndex?: number): boolean =>
    findValidation(validationByStory[storyId], word, kind, poolIndex) !== undefined;

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
      if (!isApproved(next, r.word, r.kind, r.poolIndex)) {
        next = toggleApproval(next, { word: r.word, kind: r.kind, index: r.poolIndex });
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
    current: { distractors: string[]; sentence?: string; synonym?: string },
  ) => {
    setEditTarget(target);
    setEditStatus("idle");
    if (target.kind === "distractors") {
      setEditDraft({ kind: "distractors", distractors: current.distractors.join(", ") });
    } else if (target.kind === "cloze") {
      setEditDraft({
        kind: "cloze",
        sentence: current.sentence ?? "",
        distractors: current.distractors.join(", "),
      });
    } else {
      setEditDraft({
        kind: "synonym",
        synonym: current.synonym ?? "",
        distractors: current.distractors.join(", "),
      });
    }
  };

  const onCancelEdit = () => {
    setEditTarget(null);
    setEditDraft(null);
    setEditStatus("idle");
  };

  const onSaveEdit = async () => {
    if (!editTarget || !editDraft) return;
    setEditStatus("saving");
    const distractors = editDraft.distractors.split(",").map((d) => d.trim()).filter(Boolean);
    const value: ReplaceValue =
      editDraft.kind === "distractors"
        ? distractors
        : editDraft.kind === "cloze"
          ? { sentence: editDraft.sentence.trim(), distractors }
          : { synonym: editDraft.synonym.trim(), distractors };

    try {
      await replaceQuizQuestion(
        editTarget.storyId,
        editTarget.frameIndex,
        editTarget.wordIndex,
        editTarget.kind,
        editTarget.poolIndex,
        value,
      );
      setStories((prev) =>
        prev.map((s) =>
          s.id === editTarget.storyId
            ? {
                ...s,
                frames: s.frames.map((frame, fi) =>
                  fi === editTarget.frameIndex
                    ? applyLocalEdit(frame, editTarget.kind, editTarget.wordIndex, editTarget.poolIndex, value)
                    : frame,
                ),
              }
            : s,
        ),
      );
      // An edited candidate needs a fresh Validate before it can be checked
      // again — drop any stale result and un-check it if it was checked.
      setValidationByStory((prev) => ({
        ...prev,
        [editTarget.storyId]: (prev[editTarget.storyId] ?? []).filter(
          (r) =>
            !(
              r.word === editTarget.word &&
              r.kind === editTarget.kind &&
              (r.poolIndex ?? undefined) === editTarget.poolIndex
            ),
        ),
      }));
      const key = pendingKeyFor(editTarget.storyId, level);
      const current = pendingApprovalsByKey[key] ?? [];
      if (isApproved(current, editTarget.word, editTarget.kind, editTarget.poolIndex)) {
        const next = toggleApproval(current, {
          word: editTarget.word,
          kind: editTarget.kind,
          index: editTarget.poolIndex,
        });
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
  const onGenerate = async (story: CustomTeacherStory, topic: ReturnType<typeof storyToTopic>) => {
    const storyId = story.id;
    setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "generating" }));
    try {
      const lookalikeTopic = topic as unknown as Parameters<typeof planLookalikeGrowth>[0];
      const distractorCandidates = planDistractorGrowth(topic);
      const clozeCandidates = planClozeGrowth(topic);
      const synonymCandidates = planSynonymGrowth(topic);
      const lookalikeCandidates = planLookalikeGrowth(lookalikeTopic);

      const toWords = (list: Array<{ word: string; translation: string; context?: string; existing: string[] }>): VocabGrowthWord[] =>
        list.map((c) => ({ word: c.word, translation: c.translation, context: c.context, avoid: c.existing }));

      const [distractorResults, clozeResults, synonymResults, lookalikeResults] = await Promise.all([
        distractorCandidates.length ? generateVocabDistractors(toWords(distractorCandidates)) : Promise.resolve([]),
        clozeCandidates.length ? generateVocabCloze(toWords(clozeCandidates)) : Promise.resolve([]),
        synonymCandidates.length ? generateVocabSynonym(toWords(synonymCandidates)) : Promise.resolve([]),
        lookalikeCandidates.length ? generateVocabLookalike(toWords(lookalikeCandidates)) : Promise.resolve([]),
      ]);

      const pending: PendingCandidate[] = [];
      for (const u of buildDistractorPatchUpdates(distractorCandidates, distractorResults)) {
        const c = distractorCandidates.find((x) => x.frameIndex === u.frameIndex && x.wordIndex === u.wordIndex)!;
        pending.push({ frameIndex: u.frameIndex, wordIndex: u.wordIndex, word: c.word, kind: "distractors", value: u.distractors, decision: "pending" });
      }
      for (const u of buildClozePatchUpdates(clozeCandidates, clozeResults)) {
        const c = clozeCandidates.find((x) => x.frameIndex === u.frameIndex && x.wordIndex === u.wordIndex)!;
        pending.push({ frameIndex: u.frameIndex, wordIndex: u.wordIndex, word: c.word, kind: "cloze", value: u.candidates[0], decision: "pending" });
      }
      for (const u of buildSynonymPatchUpdates(synonymCandidates, synonymResults)) {
        const c = synonymCandidates.find((x) => x.frameIndex === u.frameIndex && x.wordIndex === u.wordIndex)!;
        pending.push({ frameIndex: u.frameIndex, wordIndex: u.wordIndex, word: c.word, kind: "synonym", value: u.candidates[0], decision: "pending" });
      }
      for (const u of buildLookalikePatchUpdates(lookalikeCandidates, lookalikeResults)) {
        const c = lookalikeCandidates.find((x) => x.frameIndex === u.frameIndex && x.wordIndex === u.wordIndex)!;
        pending.push({ frameIndex: u.frameIndex, wordIndex: u.wordIndex, word: c.word, kind: "lookalike", value: u.lookalikes, decision: "pending" });
      }

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
    setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "applying" }));
    try {
      const distractorUpdates = accepted
        .filter((c) => c.kind === "distractors")
        .map((c) => ({ frameIndex: c.frameIndex, wordIndex: c.wordIndex, distractors: c.value as string[] }));
      const clozeUpdates = accepted
        .filter((c) => c.kind === "cloze")
        .map((c) => ({ frameIndex: c.frameIndex, wordIndex: c.wordIndex, candidates: [c.value as { sentence: string; distractors: string[] }] }));
      const synonymUpdates = accepted
        .filter((c) => c.kind === "synonym")
        .map((c) => ({ frameIndex: c.frameIndex, wordIndex: c.wordIndex, candidates: [c.value as { synonym: string; distractors: string[] }] }));
      const lookalikeUpdates = accepted
        .filter((c) => c.kind === "lookalike")
        .map((c) => ({ frameIndex: c.frameIndex, wordIndex: c.wordIndex, lookalikes: c.value as string[] }));

      await Promise.all([
        distractorUpdates.length ? updateVocabularyDistractors(storyId, distractorUpdates) : Promise.resolve(),
        clozeUpdates.length ? updateVocabularyCloze(storyId, clozeUpdates) : Promise.resolve(),
        synonymUpdates.length ? updateVocabularySynonym(storyId, synonymUpdates) : Promise.resolve(),
        lookalikeUpdates.length ? updateVocabularyLookalike(storyId, lookalikeUpdates) : Promise.resolve(),
      ]);

      setStories((prev) => prev.map((s) => (s.id === storyId ? applyAcceptedCandidatesLocally(s, accepted) : s)));
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
            ? `⚠ File exported from a different story (${parsed.storyId})`
            : `✓ Imported ${parsed.exclusions.length} marks — Save to apply`,
      }));
    } catch (err) {
      setImportNoteByStory((prev) => ({
        ...prev,
        [storyId]: `⚠ ${err instanceof Error ? err.message : "Invalid marks file"}`,
      }));
    }
  };

  const onExport = (story: CustomTeacherStory) => {
    exportQuizMarksFile(story, exclusionsByStory[story.id] ?? []);
  };

  const trashButton = (
    storyId: string,
    word: string,
    kind: QuizExclusionKind,
    index?: number,
  ) => {
    const exclusions = exclusionsByStory[storyId] ?? [];
    const marked = isExcluded(exclusions, word, kind, index);
    return (
      <button
        type="button"
        className={`tqr-trash${marked ? " is-marked" : ""}`}
        aria-pressed={marked}
        aria-label={`${marked ? "Restore" : "Exclude"} ${kind} for ${word}`}
        onClick={() => onToggle(storyId, index === undefined ? { word, kind } : { word, kind, index })}
      >
        {marked ? "↩" : "🗑"}
      </button>
    );
  };

  const approvalCheckbox = (storyId: string, word: string, kind: QuizApprovalKind, poolIndex?: number) => {
    const approvals = pendingApprovalsByKey[pendingKeyFor(storyId, level)] ?? [];
    const checked = isApproved(approvals, word, kind, poolIndex);
    const checkable = checked || canCheck(storyId, word, kind, poolIndex);
    return (
      <input
        type="checkbox"
        className="tqr-approve-checkbox"
        checked={checked}
        disabled={!checkable}
        title={checkable ? undefined : "Validate first"}
        aria-label={`Approve ${kind} for ${word}`}
        onChange={() => {
          const story = stories.find((s) => s.id === storyId);
          if (story) onToggleApproval(story, { word, kind, index: poolIndex });
        }}
      />
    );
  };

  const editButton = (target: EditTarget, current: { distractors: string[]; sentence?: string; synonym?: string }) => (
    <button type="button" className="tqr-edit" onClick={() => onStartEdit(target, current)}>
      <BiLabel zh="編輯" en="Edit" />
    </button>
  );

  const editForm = () => {
    if (!editDraft) return null;
    return (
      <div className="tqr-edit-form">
        {editDraft.kind === "cloze" && (
          <label>
            <BiLabel zh="句子" en="Sentence" />
            <input
              type="text"
              lang="zh-Hant"
              value={editDraft.sentence}
              onChange={(e) => setEditDraft({ ...editDraft, sentence: e.target.value })}
            />
          </label>
        )}
        {editDraft.kind === "synonym" && (
          <label>
            <BiLabel zh="同義詞" en="Synonym" />
            <input
              type="text"
              lang="zh-Hant"
              value={editDraft.synonym}
              onChange={(e) => setEditDraft({ ...editDraft, synonym: e.target.value })}
            />
          </label>
        )}
        <label>
          <BiLabel zh="錯誤選項（逗號分隔）" en="Wrong options (comma-separated)" />
          <input
            type="text"
            value={editDraft.distractors}
            onChange={(e) => setEditDraft({ ...editDraft, distractors: e.target.value })}
          />
        </label>
        <div className="tqr-edit-actions">
          <button type="button" className="tqr-io" onClick={onCancelEdit}>
            <BiLabel zh="取消" en="Cancel" />
          </button>
          <button type="button" className="tqr-save" disabled={editStatus === "saving"} onClick={onSaveEdit}>
            {editStatus === "saving" ? (
              <BiLabel zh="儲存中…" en="Saving…" />
            ) : (
              <BiLabel zh="儲存並重新檢查" en="Save (needs re-validate)" />
            )}
          </button>
        </div>
        {editStatus === "error" && (
          <span className="tqr-status-error" role="alert">
            <BiLabel zh="儲存失敗" en="Save failed" />
          </span>
        )}
      </div>
    );
  };

  const isEditing = (target: Omit<EditTarget, "storyId" | "frameIndex" | "wordIndex">, storyId: string) =>
    editTarget?.storyId === storyId &&
    editTarget.word === target.word &&
    editTarget.kind === target.kind &&
    (editTarget.poolIndex ?? undefined) === (target.poolIndex ?? undefined);

  /** Renders one assembled question — prompt, options with the correct
   * answer highlighted, status badge, checkbox, and Edit — instead of the
   * raw pool text a teacher would otherwise have to parse themselves. The
   * first entry in `options` is always the correct answer. */
  const questionRow = (spec: {
    storyId: string;
    frameIndex: number;
    wordIndex: number;
    word: string;
    kind: QuizApprovalKind;
    poolIndex?: number;
    kindLabel: { zh: string; en: string };
    promptZh: string;
    promptEn: string;
    options: string[];
    editValue: { distractors: string[]; sentence?: string; synonym?: string };
    diffStatus: MaterialDiffStatus | undefined;
  }) => {
    const result = findValidation(validationByStory[spec.storyId], spec.word, spec.kind, spec.poolIndex);
    return (
      <div className="tqr-qrow" key={`${spec.kind}-${spec.poolIndex ?? 0}`}>
        {approvalCheckbox(spec.storyId, spec.word, spec.kind, spec.poolIndex)}
        <div className="tqr-qbody">
          <span className="tqr-qkind">
            {diffBadge(spec.diffStatus)}
            <BiLabel zh={spec.kindLabel.zh} en={spec.kindLabel.en} />
            {spec.poolIndex !== undefined && ` #${spec.poolIndex + 1}`}
          </span>
          {questionStatusBadge(result)}
          <p className="tqr-qprompt" lang="zh-Hant">
            {spec.promptZh}
            <br />
            <span className="tqr-qprompt-en">{spec.promptEn}</span>
          </p>
          <div className="tqr-qoptions">
            {spec.options.map((opt, i) => (
              <span key={i} className={`tqr-opt${i === 0 ? " is-correct" : ""}`}>
                {opt}
              </span>
            ))}
          </div>
        </div>
        {editButton(
          {
            storyId: spec.storyId,
            frameIndex: spec.frameIndex,
            wordIndex: spec.wordIndex,
            word: spec.word,
            kind: spec.kind,
            poolIndex: spec.poolIndex,
          },
          spec.editValue,
        )}
        {isEditing({ word: spec.word, kind: spec.kind, poolIndex: spec.poolIndex }, spec.storyId) && editForm()}
      </div>
    );
  };

  return (
    <main className="teacher-quiz-review">
      <input
        type="file"
        accept="application/json"
        ref={importInputRef}
        onChange={onImportChange}
        className="tqr-file-input"
        data-testid="tqr-import-input"
      />
      <header className="tqr-header">
        <div>
          <p className="tqr-kicker">
            <BiLabel zh="測驗檢查" pinyin="Cèyàn jiǎnchá" en="Quiz review" />
          </p>
          <h1>
            <BiLabel
              zh="檢查測驗題目和答案"
              pinyin="Jiǎnchá cèyàn tímù hé dá'àn"
              en="Verify quiz questions and answers"
            />
          </h1>
          <p className="tqr-lede">
            <BiText
              zh="標記不好的題目材料，學生的測驗就不會再出這些題。"
              pinyin="Biāojì bù hǎo de tímù cáiliào, xuéshēng de cèyàn jiù bú huì zài chū zhèxiē tí."
              en="Mark bad material and the student quiz will never build questions from it."
            />
          </p>
        </div>
        <div className="tqr-controls">
          <label>
            <BiLabel zh="課" pinyin="Kè" en="Lesson" />
            <select value={lessonKey} onChange={(e) => setLessonKey(e.target.value)}>
              {lessonGroups.map((g) => (
                <option key={lessonKeyFor(g.lessonNumber)} value={lessonKeyFor(g.lessonNumber)}>
                  {lessonOptionLabel(g.lessonNumber)}
                </option>
              ))}
            </select>
          </label>
          {levels.length > 1 && (
            <label>
              <BiLabel zh="難度" pinyin="Nándù" en="Level" />
              <select
                value={level}
                onChange={(e) => setLevel(e.target.value as StoryDifficultyLevel)}
              >
                {levels.map((l) => (
                  <option key={l} value={l}>
                    {l === "easy" ? "簡單" : l === "medium" ? "中等" : "困難"}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="tqr-only-changes">
            <input
              type="checkbox"
              checked={onlyChanges}
              onChange={(e) => setOnlyChanges(e.target.checked)}
            />
            <BiLabel zh="只顯示新增/已改" en="Only new/changed" />
          </label>
        </div>
      </header>

      {!currentGroup && (
        <p className="tqr-empty">
          <BiText
            zh="還沒有已發佈的故事。"
            pinyin="Hái méiyǒu yǐ fābù de gùshì."
            en="No published stories yet."
          />
        </p>
      )}

      {currentGroup &&
        currentGroup.stories.map((story) => {
          if (level !== "easy" && !storyHasTierContent(story, level)) return null;
          const topic = storyToTopic(story, level);
          const exclusions = exclusionsByStory[story.id] ?? [];
          const dirty = dirtyByStory[story.id] ?? false;
          const status = statusByStory[story.id] ?? "idle";
          const snapshot = storyMaterialSnapshot(story, level);
          const importNote = importNoteByStory[story.id];
          const validateStatus = validateStatusByStory[story.id] ?? "idle";
          const approveStatus = approveStatusByStory[story.id] ?? "idle";
          const validation = validationByStory[story.id];
          const approvals = pendingApprovalsByKey[pendingKeyFor(story.id, level)] ?? [];
          const approvedCount = approvals.length;
          const generateStatus = generateStatusByStory[story.id] ?? "idle";
          const pendingCandidates = pendingCandidatesByStory[story.id] ?? [];
          const revealedCount = revealedCountByStory[story.id] ?? 0;
          const hasAnyMaterial = buildApprovedMaterial(topic, []).some(
            (e) => e.distractors.length || e.cloze.length || e.synonym.length || e.lookalike.length,
          );
          const pendingDecidedCount = pendingCandidates.filter((c) => c.decision !== "pending").length;
          const pendingAcceptedCount = pendingCandidates.filter((c) => c.decision === "accept").length;

          return (
            <section className="tqr-story" key={story.id}>
              <header className="tqr-story-head">
                <h2 className="tqr-story-title">{story.title}</h2>
                <div className="tqr-story-actions">
                  <button
                    type="button"
                    className="tqr-generate"
                    disabled={generateStatus === "generating" || generateStatus === "revealing"}
                    onClick={() => onGenerate(story, topic)}
                  >
                    {generateStatus === "generating" ? (
                      <BiLabel zh="生成中…" en="Generating…" />
                    ) : hasAnyMaterial ? (
                      <BiLabel zh="🔄 更新題目" en="🔄 Update Questions" />
                    ) : (
                      <BiLabel zh="✨ 生成題目" en="✨ Generate Questions" />
                    )}
                  </button>
                  <button type="button" className="tqr-io" onClick={() => onExport(story)}>
                    <BiLabel zh="匯出" en="Export" />
                  </button>
                  <button type="button" className="tqr-io" onClick={() => triggerImport(story.id)}>
                    <BiLabel zh="匯入" en="Import" />
                  </button>
                  <button
                    type="button"
                    className="tqr-save"
                    disabled={!dirty || status === "saving"}
                    onClick={() => onSave(story, topic)}
                  >
                    {status === "saving" ? (
                      <BiLabel zh="儲存中…" pinyin="Chǔcún zhōng…" en="Saving…" />
                    ) : (
                      <BiLabel zh="儲存標記" pinyin="Chǔcún biāojì" en="Save marks" />
                    )}
                  </button>
                  {status === "saved" && !dirty && (
                    <span className="tqr-status-ok">✓ <BiLabel zh="已儲存" en="Saved" /></span>
                  )}
                  {status === "error" && (
                    <span className="tqr-status-error" role="alert">
                      <BiLabel zh="儲存失敗" en="Save failed" />
                    </span>
                  )}
                  <button
                    type="button"
                    className="tqr-validate"
                    disabled={validateStatus === "validating"}
                    onClick={() => onValidate(story, topic)}
                  >
                    {validateStatus === "validating" ? (
                      <BiLabel zh="檢查中…" pinyin="Jiǎnchá zhōng…" en="Checking…" />
                    ) : (
                      <BiLabel zh="檢查題目" pinyin="Jiǎnchá tímù" en="Check Questions" />
                    )}
                  </button>
                  {validateStatus === "error" && (
                    <span className="tqr-status-error" role="alert">
                      <BiLabel zh="檢查失敗" en="Validate failed" />
                    </span>
                  )}
                  <button
                    type="button"
                    className="tqr-io"
                    disabled={!validation || validation.length === 0}
                    onClick={() => onApproveAll(story)}
                  >
                    <BiLabel zh="核准全部（乾淨）" pinyin="Hézhǔn quánbù" en="Approve all clean" />
                  </button>
                  <button
                    type="button"
                    className="tqr-approve"
                    disabled={approveStatus === "approving" || approvedCount === 0}
                    onClick={() => onApprove(story, topic)}
                  >
                    {approveStatus === "approving" ? (
                      <BiLabel zh="發佈中…" pinyin="Fābù zhōng…" en="Publishing…" />
                    ) : (
                      <BiLabel zh="核准並發佈" pinyin="Hézhǔn bìng fābù" en="Approve & Publish" />
                    )}
                  </button>
                  {approveStatus === "approved" && (
                    <span className="tqr-status-ok">✓ <BiLabel zh="已發佈" en="Published" /></span>
                  )}
                  {approveStatus === "error" && (
                    <span className="tqr-status-error" role="alert">
                      <BiLabel zh="發佈失敗" en="Publish failed" />
                    </span>
                  )}
                  <span className="tqr-count">
                    <BiLabel zh={`已勾選 ${approvedCount} 題`} en={`${approvedCount} checked`} />
                  </span>
                  <span className="tqr-count">
                    <BiLabel zh={`已標記 ${exclusions.length} 項`} en={`${exclusions.length} marked`} />
                  </span>
                </div>
              </header>
              {importNote && <p className="tqr-import-note">{importNote}</p>}

              {generateStatus === "generating" && (
                <div className="tqr-generate-spinner">
                  <span className="tqr-spinner" aria-hidden="true" />
                  <BiLabel zh="正在生成題目…" en="Generating questions…" />
                </div>
              )}

              {pendingCandidates.length > 0 && (
                <section className="tqr-pending-panel">
                  <div className="tqr-pending-summary">
                    <span>
                      {pendingDecidedCount === pendingCandidates.length ? (
                        <BiLabel zh={`✓ 已決定全部 ${pendingCandidates.length} 項`} en={`✓ All ${pendingCandidates.length} changes decided`} />
                      ) : (
                        <BiLabel
                          zh={`已決定 ${pendingDecidedCount} / ${pendingCandidates.length} 項`}
                          en={`${pendingDecidedCount} of ${pendingCandidates.length} changes decided`}
                        />
                      )}
                    </span>
                    <span className="tqr-pending-summary-actions">
                      <button type="button" className="tqr-io" onClick={() => onAcceptAllPending(story.id)}>
                        <BiLabel zh="✓ 全部接受" en="✓ Accept All" />
                      </button>
                      <button
                        type="button"
                        className="tqr-approve"
                        disabled={pendingDecidedCount !== pendingCandidates.length || generateStatus === "applying"}
                        onClick={() => onApplyPendingCandidates(story)}
                      >
                        {generateStatus === "applying" ? (
                          <BiLabel zh="套用中…" en="Applying…" />
                        ) : (
                          <BiLabel zh={`套用變更（${pendingAcceptedCount}）`} en={`Apply Changes (${pendingAcceptedCount})`} />
                        )}
                      </button>
                    </span>
                  </div>

                  {pendingCandidates.slice(0, revealedCount).map((candidate, index) => (
                    <div
                      className={`tqr-pending-row${candidate.decision === "pending" ? " is-pending" : ""}${candidate.decision === "reject" ? " is-rejected" : ""}`}
                      key={`${candidate.word}-${candidate.kind}-${index}`}
                    >
                      <div className="tqr-pending-body">
                        <span className="tqr-qkind">
                          {candidate.word} · {candidate.kind}
                          <span className="diff-tag is-new">🆕 New</span>
                        </span>
                        {renderPendingPrompt(candidate)}
                      </div>
                      {candidate.decision === "pending" ? (
                        <div className="tqr-pending-decide">
                          <button type="button" className="decide-btn accept" onClick={() => onDecideCandidate(story.id, index, "accept")}>
                            ✓ <BiLabel zh="接受" en="Accept" />
                          </button>
                          <button type="button" className="decide-btn reject" onClick={() => onDecideCandidate(story.id, index, "reject")}>
                            ✕ <BiLabel zh="拒絕" en="Reject" />
                          </button>
                        </div>
                      ) : (
                        <div className="tqr-pending-decided">
                          <span className={`tqr-status-badge ${candidate.decision === "accept" ? "is-clean" : "is-suspicious"}`}>
                            {candidate.decision === "accept" ? "✓ Accepted" : "✕ Rejected"}
                          </span>
                          <button type="button" className="undo-link" onClick={() => onUndoDecision(story.id, index)}>
                            <BiLabel zh="復原" en="Undo" />
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </section>
              )}

              {topic.images.map((_, si) => {
                const words = topic.vocabulary[si] || [];
                if (words.length === 0) return null;
                return (
                  <section className="tqr-scene" key={si}>
                    <h3 className="tqr-scene-title">
                      <BiLabel zh={`部分 ${si + 1}`} en={`Scene ${si + 1}`} />
                    </h3>
                    {words.map((word, wi) => {
                      const wordGone = isExcluded(exclusions, word, "word");
                      const pinyin = topic.vocabularyPinyin?.[si]?.[wi];
                      const pos = topic.vocabularyPos?.[si]?.[wi];
                      const translation = topic.vocabularyTranslation?.[si]?.[wi];
                      const distractors = topic.vocabularyDistractors?.[si]?.[wi] ?? [];
                      const cloze = topic.vocabularyCloze?.[si]?.[wi] ?? [];
                      const synonyms = topic.vocabularySynonym?.[si]?.[wi] ?? [];
                      // Topic (from TopicSelector.tsx) doesn't declare vocabularyLookalike —
                      // only StoryRecorder.tsx's own Topic type does (a known drift, see
                      // topicQuiz.ts) — but storyToTopic always sets it at runtime.
                      const lookalikes =
                        (topic as unknown as { vocabularyLookalike?: Record<number, string[][]> })
                          .vocabularyLookalike?.[si]?.[wi] ?? [];
                      const diff = diffWord(word, { distractors, cloze, synonym: synonyms }, snapshot);

                      if (onlyChanges && diff && diff.status === "kept") return null;

                      return (
                        <article
                          className={`tqr-word${wordGone ? " is-word-gone" : ""}`}
                          key={`${word}-${wi}`}
                        >
                          <header className="tqr-word-head">
                            {diffBadge(diff?.status)}
                            <strong lang="zh-Hant">{word}</strong>
                            {pinyin && <span className="tqr-pinyin">{pinyin}</span>}
                            {pos && <span className="tqr-pos">{pos}</span>}
                            {translation ? (
                              <span className="tqr-translation">→ {translation}</span>
                            ) : (
                              <span className="tqr-no-quiz">
                                <BiLabel zh="沒有翻譯，不會出題" en="No translation — never quizzed" />
                              </span>
                            )}
                            {translation && trashButton(story.id, word, "word")}
                          </header>
                          {!wordGone && translation && (
                            <div className="tqr-pools">
                              {distractors.length > 0 &&
                                questionRow({
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "distractors",
                                  kindLabel: { zh: "翻譯", en: "Translation" },
                                  promptZh: `「${word}」是什麼意思？`,
                                  promptEn: `What does "${word}" mean?`,
                                  options: [translation, ...distractors],
                                  editValue: { distractors },
                                  diffStatus: diff?.distractorsStatus,
                                })}
                              {cloze.map((c, ci) =>
                                questionRow({
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "cloze",
                                  poolIndex: ci,
                                  kindLabel: { zh: "填空", en: "Cloze" },
                                  promptZh: c.sentence.replace(word, "＿＿＿"),
                                  promptEn: "Which word fills the blank?",
                                  options: [word, ...c.distractors],
                                  editValue: { sentence: c.sentence, distractors: c.distractors },
                                  diffStatus: diff?.clozeStatus[ci],
                                }),
                              )}
                              {synonyms.map((s, syi) =>
                                questionRow({
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "synonym",
                                  poolIndex: syi,
                                  kindLabel: { zh: "同義詞", en: "Synonym" },
                                  promptZh: `哪一個字跟「${word}」意思一樣？`,
                                  promptEn: `Which word means the same as "${word}"?`,
                                  options: [s.synonym, ...s.distractors],
                                  editValue: { synonym: s.synonym, distractors: s.distractors },
                                  diffStatus: diff?.synonymStatus[syi],
                                }),
                              )}
                              {lookalikes.length > 0 && (
                                <div className="tqr-pool">
                                  <span className="tqr-pool-label">
                                    <BiLabel zh="形近字誘答" en="Look-alike traps" />
                                    {trashButton(story.id, word, "lookalike")}
                                  </span>
                                  <span className="tqr-pool-items" lang="zh-Hant">
                                    {lookalikes.join(" · ")}
                                  </span>
                                </div>
                              )}
                            </div>
                          )}
                        </article>
                      );
                    })}
                  </section>
                );
              })}
            </section>
          );
        })}
    </main>
  );
}
