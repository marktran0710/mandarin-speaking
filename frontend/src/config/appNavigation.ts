import { currentRole } from "../utils/session";
import {
  getLastPracticeTarget as readTarget,
  getLastVisitedPage as readLastPage,
} from "../utils/studentSession";
import type { Topic } from "../components/TopicSelector";
import type { Page } from "../types/page";
import type { StudentAppBootstrapState } from "../app/appTypes";

const RESTORABLE_STUDENT_PAGES: readonly Page[] = [
  "student-workspace",
  "student-practice",
  "student-stories",
  "voice-test",
  "image-narration",
];

function isRestorableStudentPage(page: string | null): page is Page {
  return RESTORABLE_STUDENT_PAGES.includes(page as Page);
}

export function getStudentAppBootstrapState(): StudentAppBootstrapState {
  const defaultState: StudentAppBootstrapState = {
    activeRole: null,
    currentPage: "home",
    studentWorkspaceView: "practice",
    practiceTarget: null,
  };

  if (currentRole("student") !== "student") return defaultState;

  if (["/analyze", "/voice-test"].includes(window.location.pathname)) {
    return { ...defaultState, activeRole: "student", currentPage: "voice-test" };
  }

  const lastPage = readLastPage();
  const restoredPage = isRestorableStudentPage(lastPage) ? lastPage : "student-practice";
  const studentWorkspaceView =
    restoredPage === "student-stories"
      ? "progress"
      : restoredPage === "image-narration"
        ? "picture-talk"
        : "practice";
  const lastTarget = studentWorkspaceView === "practice" ? readTarget() : null;

  return {
    activeRole: "student",
    currentPage: restoredPage === "voice-test" ? "voice-test" : "student-workspace",
    studentWorkspaceView,
    practiceTarget: lastTarget
      ? { topicId: lastTarget.topicId, imageIndex: lastTarget.imageIndex }
      : null,
  };
}

export function collectPinyinTexts(topics: readonly Topic[]): string[] {
  const texts: string[] = [];
  for (const topic of topics) {
    texts.push(...(topic.prompts ?? []));
    for (const scene of Object.values(topic.vocabulary)) texts.push(...scene);
    for (const scene of Object.values(topic.phrases ?? {})) texts.push(...scene);
    for (const group of Object.values(topic.vocabularyGroups ?? {})) {
      for (const vocabGroup of group) texts.push(...vocabGroup.words);
    }
    texts.push(...Object.values(topic.suggestedAnswers ?? {}));
    texts.push(...Object.values(topic.listenScripts ?? {}));
  }
  return texts;
}
