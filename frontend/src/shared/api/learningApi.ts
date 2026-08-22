/**
 * Student-facing API boundary for the staged frontend migration.
 *
 * The implementation still lives in services/database.ts so endpoint behavior
 * and local fallback behavior remain unchanged. New student features should
 * import this module instead of reaching into the legacy service directly.
 */
export {
  canUseDatabase,
  createAudioRecord,
  createHelpRequest,
  listAudioRecords,
  listCustomStories,
  listHelpRequests,
  logoutStudent,
} from "../../services/database";

export type {
  HelpRequest,
  StoredAudioRecord,
  StoredCustomStory,
} from "../../services/database";
