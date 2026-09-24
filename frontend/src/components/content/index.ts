export { default as ContentDiffDisplay } from "./ContentDiffDisplay";
// TopicSelector (the old student lesson picker) was replaced by
// src/student/study/StudyPage.tsx. Its domain types live on — they are the
// canonical Topic shape for the whole app.
export type { Topic, TopicStartOptions, VocabGroup } from "./topic-selector/types";
