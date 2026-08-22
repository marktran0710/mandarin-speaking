/** Quiz API boundary. Keep this adapter thin until quiz review is migrated. */
export {
  approveQuizMaterial,
  generateVocabCloze,
  generateVocabDistractors,
  generateVocabSynonym,
  replaceQuizQuestion,
  saveQuizPendingApprovals,
  updateQuizExclusions,
  updateVocabularyCloze,
  updateVocabularyDistractors,
  updateVocabularySynonym,
  validateQuizMaterial,
} from "../../services/database";

export type {
  VocabularyClozeCandidate,
  VocabularyClozeUpdate,
  VocabularyDistractorUpdate,
  VocabularySynonymCandidate,
  VocabularySynonymUpdate,
} from "../../services/database";
