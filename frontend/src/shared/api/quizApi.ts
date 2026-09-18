/** Quiz API boundary. Keep this adapter thin until quiz review is migrated. */
export {
  approveQuizMaterial,
  replaceQuizQuestion,
  saveQuizPendingApprovals,
  updateQuizExclusions,
  updateVocabularyCloze,
  updateVocabularyDistractors,
  updateVocabularySynonym,
} from "../../services/database";

export type {
  VocabularyClozeCandidate,
  VocabularyClozeUpdate,
  VocabularyDistractorUpdate,
  VocabularySynonymCandidate,
  VocabularySynonymUpdate,
} from "../../services/database";
