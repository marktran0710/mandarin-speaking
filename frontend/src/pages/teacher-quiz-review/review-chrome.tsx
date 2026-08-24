// @ts-nocheck
import type { ReactNode } from "react";
import { BiLabel } from "../../components/BiLabel";
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

function ReviewIcon({ name, size = 18 }: { name: ReviewIconName; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  const paths: Record<ReviewIconName, ReactNode> = {
    accept: <path d="m5 12 4 4L19 6" />,
    add: <path d="M12 5v14M5 12h14" />,
    chevron: <path d="m8 10 4 4 4-4" />,
    edit: (
      <>
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" />
      </>
    ),
    export: (
      <>
        <path d="M12 3v12" />
        <path d="m7 8 5-5 5 5" />
        <path d="M5 14v5h14v-5" />
      </>
    ),
    generate: (
      <>
        <path d="M12 3v4M12 17v4M3 12h4M17 12h4" />
        <path d="m5.6 5.6 2.8 2.8m7.2 7.2 2.8 2.8m0-12.8-2.8 2.8m-7.2 7.2-2.8 2.8" />
      </>
    ),
    import: (
      <>
        <path d="M12 15V3" />
        <path d="m7 10 5 5 5-5" />
        <path d="M5 14v5h14v-5" />
      </>
    ),
    publish: (
      <>
        <path d="m22 2-7 20-4-9-9-4Z" />
        <path d="M22 2 11 13" />
      </>
    ),
    reject: <path d="m6 6 12 12M18 6 6 18" />,
    restore: (
      <>
        <path d="M3 12a9 9 0 1 0 3-6.7" />
        <path d="M3 4v6h6" />
      </>
    ),
    save: (
      <>
        <path d="M5 3h12l2 2v16H5Z" />
        <path d="M8 3v6h8V3M8 21v-7h8v7" />
      </>
    ),
    trash: (
      <>
        <path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14" />
        <path d="M10 11v6M14 11v6" />
      </>
    ),
    validate: (
      <>
        <path d="M9 3h6l1 2h3v16H5V5h3Z" />
        <path d="m8 13 2.5 2.5L16 10" />
      </>
    ),
  };
  return <svg {...common}>{paths[name]}</svg>;
}
function diffBadge(status: MaterialDiffStatus | undefined) {
  if (!status || status === "kept") return null;
  return (
    <span className={`tqr-diff-badge tqr-diff-${status}`}>
      <span className="tqr-visually-hidden">{status === "new" ? "🆕" : "✎"}</span>
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
            {candidate.origin === "new" && <span className="tqr-visually-hidden">🆕 New</span>}
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
