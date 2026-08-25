import type { Topic } from "../components/TopicSelector";

export type WorkspaceView = "practice" | "progress";

export type QuizGateState =
  | { status: "completed"; score?: number }
  | { status: "required"; quizId: string; reason: string }
  | { status: "unavailable"; reason: string };

export interface ContinuePracticeTarget {
  lessonId?: string;
  storyId?: string;
  sceneId?: string;
  label: string;
  progress: number;
}

export interface LearningSummary {
  lessonProgress: number;
  wordsToPractice: number;
  todayGoal: {
    completed: number;
    total: number;
  };
  continueTarget?: ContinuePracticeTarget;
  quizGate?: QuizGateState;
}

export interface SessionIdentity {
  userId: string;
  username: string;
  role: "student" | "teacher" | "admin";
}

export interface WorkspaceTopicSummary {
  topic: Topic;
  quizGate: QuizGateState;
}
