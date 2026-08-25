// Shared across the student app (App.tsx) and the teacher app (TeacherApp.tsx),
// which are now two separate Vite entry points (index.html / teacher.html) —
// this lives outside either app file so Navigation/HomePage don't import
// from one app and get pulled into that app's bundle.
export type Page =
  | "home"
  | "student-login"
  | "teacher-login"
  | "student-workspace"
  | "student-practice"
  | "student-stories"
  | "voice-test";
