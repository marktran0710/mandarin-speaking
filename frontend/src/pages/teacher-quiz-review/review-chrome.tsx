// @ts-nocheck
import { BiLabel } from "../../components/ui/BiLabel";
import StudentIcon, { type StudentIconName } from "../../components/navigation/StudentIcon";
import { lessonTitle } from "../../utils/lessonGroups";
import { lessonKeyFor, lessonOptionLabel } from "./model-core";

type ReviewIconName =
  | "accept"
  | "add"
  | "chevron"
  | "edit"
  | "export"
  | "import"
  | "publish"
  | "reject"
  | "restore"
  | "save"
  | "trash"
  | "upload";

const REVIEW_ICON_MAP: Record<ReviewIconName, StudentIconName> = {
  accept: "check",
  add: "plus",
  chevron: "chevron-down",
  edit: "edit",
  export: "upload",
  import: "download",
  publish: "send",
  reject: "close",
  restore: "refresh",
  save: "file",
  trash: "trash",
  upload: "upload",
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
                  {item === "easy" ? "簡單" : item}
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
  children,
}: {
  storyTitle: string;
  checkedCount: number;
  markedCount: number;
  children: ReactNode;
}) {
  return (
    <aside className="tqr-action-rail" aria-label={`${storyTitle} review actions`}>
      <p className="tqr-rail-summary" aria-live="polite">
        {checkedCount === 0 && markedCount === 0 ? (
          <BiLabel zh="準備檢查" en="Ready to review" />
        ) : (
          <>
            {checkedCount > 0 && <span><strong>{checkedCount}</strong> <BiLabel zh="已勾選" en="checked" /></span>}
            {markedCount > 0 && <span><strong>{markedCount}</strong> <BiLabel zh="已標記" en="marked" /></span>}
          </>
        )}
      </p>
      <div className="tqr-rail-actions">{children}</div>
    </aside>
  );
}


export { ReviewIcon, diffBadge, ReviewFilterBar, ReviewActionRail };
