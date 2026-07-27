"""candidates_for_review: turns a story's live per-word quiz material into
Candidates for the adversarial pipeline, mirroring collectQuizEntries'
validity rules and respecting teacher exclusions — the same contract
scripts/dump-quiz-questions.py's word_questions() already dumps to JSON."""
from quiz_bank import candidates_for_review


def word(**over):
    base = {
        "word": "知道",
        "translation": "to know",
        "distractors": ["to see", "to hear"],
        "cloze": [{"sentence": "我知道了。", "distractors": ["不知道"]}],
        "synonym": [{"synonym": "曉得", "distractors": ["不懂"]}],
    }
    base.update(over)
    return base


class TestCandidatesForReview:
    def test_builds_one_candidate_per_pool_item(self):
        candidates = candidates_for_review([word()], [])
        kinds = sorted(c.kind for c in candidates)
        assert kinds == ["cloze", "synonym", "translation"]

    def test_word_level_exclusion_still_only_affects_marked_pools(self):
        # candidates_for_review only takes per-pool exclusions the caller
        # already resolved by kind; a whole-word "word" exclusion is the
        # frontend's job to drop the entry before calling this at all.
        candidates = candidates_for_review(
            [word()], [{"word": "知道", "kind": "cloze", "index": 0}]
        )
        kinds = sorted(c.kind for c in candidates)
        assert kinds == ["synonym", "translation"]

    def test_distractors_excluded_drops_translation_candidate(self):
        candidates = candidates_for_review(
            [word()], [{"word": "知道", "kind": "distractors"}]
        )
        assert all(c.kind != "translation" for c in candidates)

    def test_cloze_sentence_must_contain_word_exactly_once(self):
        bad = word(cloze=[{"sentence": "這是一句話。", "distractors": ["不知道"]}])
        candidates = candidates_for_review([bad], [])
        assert all(c.kind != "cloze" for c in candidates)

    def test_synonym_equal_to_word_is_dropped(self):
        bad = word(synonym=[{"synonym": "知道", "distractors": ["不懂"]}])
        candidates = candidates_for_review([bad], [])
        assert all(c.kind != "synonym" for c in candidates)

    def test_no_translation_skips_translation_candidate(self):
        bad = word(translation="")
        candidates = candidates_for_review([bad], [])
        assert all(c.kind != "translation" for c in candidates)

    def test_pool_index_encoded_in_key(self):
        two_cloze = word(
            cloze=[
                {"sentence": "我知道了。", "distractors": ["不知道"]},
                {"sentence": "他不知道這件事。", "distractors": ["認識"]},
            ]
        )
        candidates = candidates_for_review([two_cloze], [])
        cloze_keys = sorted(c.key for c in candidates if c.kind == "cloze")
        assert cloze_keys == ["知道:cloze:0", "知道:cloze:1"]
