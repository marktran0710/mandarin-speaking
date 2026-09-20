/** Centralized flags for staged frontend migrations. */
const viteFlag = typeof import.meta.env.VITE_STUDENT_WORKSPACE_SHELL === "string"
  ? import.meta.env.VITE_STUDENT_WORKSPACE_SHELL
  : undefined;

export const studentWorkspaceShellEnabled = viteFlag !== "legacy";
