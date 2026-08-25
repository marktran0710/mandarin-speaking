/** Centralized flags for staged frontend migrations. */
const nextFlag = typeof process !== "undefined" ? process.env.NEXT_PUBLIC_STUDENT_WORKSPACE_SHELL : undefined;
const viteFlag = typeof import.meta.env.VITE_STUDENT_WORKSPACE_SHELL === "string"
  ? import.meta.env.VITE_STUDENT_WORKSPACE_SHELL
  : undefined;

export const studentWorkspaceShellEnabled = (nextFlag || viteFlag) !== "legacy";
