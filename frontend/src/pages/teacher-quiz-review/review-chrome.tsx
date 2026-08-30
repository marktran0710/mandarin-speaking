// @ts-nocheck
import { BiLabel } from "../../components/BiLabel";
import StudentIcon, { type StudentIconName } from "../../components/StudentIcon";
import { lessonTitle } from "../../utils/lessonGroups";
import { lessonKeyFor, lessonOptionLabel } from "./model-core";
import { PENDING_KIND_LABELS, PENDING_ORIGIN_LABELS } from "./constants";

type ReviewIconName =
  | "accept"
  | "add"
  | "chevron"
  | "edit"
  | "export"
  | "generate"
  | "import"
  | "publish"
  | "reject"
  | "restore"
  | "save"
  | "trash"
  | "validate";

const REVIEW_ICON_MAP: Record<ReviewIconName, StudentIconName> = {
  accept: "check",
  add: "plus",
  chevron: "chevron-down",
  edit: "edit",
  export: "upload",
  generate: "spark",
  import: "download",
  publish: "send",
  reject: "close",
  restore: "refresh",
  save: "file",
  trash: "trash",
  validate: "check-circle",
};

function ReviewIcon({ name, size = 18 }: { name: ReviewIconName; size?: number }) {
  return <StudentIcon name={REVIEW_ICON_MAP[name]} size={size} />;
}
function diffBadge(status: MaterialDiffStatus | undefined) {
  if (!status || status === "kept") return null;
  return (
    <span className={`tqr-diff-badge tqr-diff-${status}`}>
      <BiLabel zh={status === "new" ? "新增" : "已更改"} en={status === "new" ? "New" : "Changed"} />
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
  if (!result) return null;
  if (result.status === "clean") {
    return (
      <span className="tqr-status-badge is-clean">
        <StudentIcon name="check-circle" size={14} aria-hidden="true" />
        <BiLabel zh="乾淨" en="Clean" />
      </span>
    );
  }
  return (
    <span className="tqr-status-badge is-suspicious">
      <StudentIcon name="warning" size={14} aria-hidden="true" />
      <BiLabel zh="可疑" en="Suspicious" />
      <span className="tqr-status-reason">{result.reason}</span>
    </span>
  );
}
function renderPendingValue(candidate: PendingCandidate, value: PendingCandidateValue) {
  if (candidate.kind === "distractors") {
    const items = value as string[];
    return (
      <>
        <BiLabel zh="新增干擾選項：" en="New distractors: " />
        {items.join("、")}
      </>
    );
  }
  if (candidate.kind === "cloze") {
    const cloze = value as { sentence: string; distractors: string[] };
    return (
      <>
        <span lang="zh-Hant">{cloze.sentence.replace(candidate.word, "＿＿＿")}</span>
        <br />
        <span className="tqr-qprompt-en">Which word fills the blank?</span>
        <br />
        <span>
          Options: {[candidate.word, ...cloze.distractors].join("、")}
        </span>
      </>
    );
  }
  const synonym = value as { synonym: string; distractors: string[] };
  return (
    <>
      <span lang="zh-Hant">
        哪一個字跟「{candidate.word}」意思一樣？
      </span>
      <br />
      <span className="tqr-qprompt-en">Which word means the same as "{candidate.word}"?</span>
      <br />
      <span>
        Options: {[synonym.synonym, ...synonym.distractors].join("、")}
      </span>
    </>
  );
}

function renderDiffLine(
  candidate: PendingCandidate,
  value: PendingCandidateValue,
  diffType: "add" | "del",
  actions: ReactNode = null,
) {
  return (
    <div className={`diff-row row-${diffType}`}>
      <span className="gutter" aria-hidden="true">
        {diffType === "add" ? "+" : "-"}
      </span>
      <div className="diff-content">
        <span className="tqr-pending-meta">
          <BiLabel zh={PENDING_KIND_LABELS[candidate.kind].zh} en={PENDING_KIND_LABELS[candidate.kind].en} />
          <span className={`diff-tag is-${candidate.origin}`}>
            <BiLabel zh={PENDING_ORIGIN_LABELS[candidate.origin].zh} en={PENDING_ORIGIN_LABELS[candidate.origin].en} />
          </span>
        </span>
        <span className="tqr-pending-value">{renderPendingValue(candidate, value)}</span>
      </div>
      <div className="diff-actions">{actions}</div>
    </div>
  );
}

function renderPendingDiff(candidate: PendingCandidate, actions: ReactNode = null) {
  if (candidate.origin === "changed") {
    return (
      <>
        {candidate.oldValue ? renderDiffLine(candidate, candidate.oldValue, "del") : null}
        {renderDiffLine(candidate, candidate.value, "add", actions)}
      </>
    );
  }
  if (candidate.origin === "removed") {
    return (
      <>
        {renderDiffLine(candidate, candidate.value, "del", actions)}
        <p className="row-note">
          <BiLabel
            zh="這個詞已不在此場景使用，自上次檢查後已移除。"
            en="Word no longer used in this scene — dropped since the last review."
          />
        </p>
      </>
    );
  }
  return renderDiffLine(candidate, candidate.value, "add", actions);
}

export interface QuizReviewJump {
  lessonNumber: number | null;
  /** Distinguishes repeat jumps to the same lesson — the effect keys off
   * this, not lessonNumber, so a second click still re-triggers it. */
  nonce: number;
}

function ReviewFilterBar({
  lessonGroups,
  lessonKey,
  onLessonChange,
  levels,
  level,
  onLevelChange,
  stories,
  storyFilterId,
  onStoryChange,
}: {
  lessonGroups: LessonReviewGroup[];
  lessonKey: string;
  onLessonChange: (value: string) => void;
  levels: StoryDifficultyLevel[];
  level: StoryDifficultyLevel;
  onLevelChange: (value: StoryDifficultyLevel) => void;
  stories: CustomTeacherStory[];
  storyFilterId: string;
  onStoryChange: (value: string) => void;
}) {
  return (
    <header className="tqr-header" aria-label="Quiz review controls">
      <div className="tqr-header-copy">
        <h1>
          <BiLabel zh="測驗檢查" en="Quiz Review" />
        </h1>
      </div>
      <div className="tqr-controls">
        <label>
          <BiLabel zh="課" en="Lesson" />
          <select value={lessonKey} onChange={(event) => onLessonChange(event.target.value)}>
            {lessonGroups.map((group) => (
              <option key={lessonKeyFor(group.lessonNumber)} value={lessonKeyFor(group.lessonNumber)}>
                {lessonOptionLabel(group.lessonNumber)}
              </option>
            ))}
          </select>
        </label>
        {levels.length > 1 && (
          <label>
            <BiLabel zh="難度" en="Level" />
            <select
              value={level}
              onChange={(event) => onLevelChange(event.target.value as StoryDifficultyLevel)}
            >
              {levels.map((item) => (
                <option key={item} value={item}>
                  {item === "easy" ? "簡單" : item === "medium" ? "中等" : "困難"}
                </option>
              ))}
            </select>
          </label>
        )}
        {stories.length > 1 && (
          <label>
            <BiLabel zh="故事" en="Story" />
            <select value={storyFilterId} onChange={(event) => onStoryChange(event.target.value)}>
              <option value="all">全部故事（批次檢查）</option>
              {stories.map((story) => (
                <option key={story.id} value={story.id}>{story.title}</option>
              ))}
            </select>
          </label>
        )}
      </div>
    </header>
  );
}

function ReviewActionRail({
  storyTitle,
  checkedCount,
  markedCount,
  changeCount,
  children,
}: {
  storyTitle: string;
  checkedCount: number;
  markedCount: number;
  changeCount: number;
  children: ReactNode;
}) {
  return (
    <aside className="tqr-action-rail" aria-label={`${storyTitle} review actions`}>
      <p className="tqr-rail-summary" aria-live="polite">
        {checkedCount === 0 && markedCount === 0 && changeCount === 0 ? (
          <BiLabel zh="準備檢查" en="Ready to review" />
        ) : (
          <>
            {checkedCount > 0 && <span><strong>{checkedCount}</strong> <BiLabel zh="已勾選" en="checked" /></span>}
            {markedCount > 0 && <span><strong>{markedCount}</strong> <BiLabel zh="已標記" en="marked" /></span>}
            {changeCount > 0 && <span><strong>{changeCount}</strong> <BiLabel zh="待決定" en="to decide" /></span>}
          </>
        )}
      </p>
      <div className="tqr-rail-actions">{children}</div>
    </aside>
  );
}


export { ReviewIcon, diffBadge, findValidation, questionStatusBadge, renderPendingValue, renderDiffLine, renderPendingDiff, ReviewFilterBar, ReviewActionRail };
