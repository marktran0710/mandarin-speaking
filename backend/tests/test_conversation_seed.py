from scripts.import_lesson_5_8_stories import (
    STORIES,
    build_conversation_turns,
    git_show,
    parse_dialogue,
)


def _turns_for(spec):
    story_id = f"lesson-{spec.lesson}-{spec.slug}"
    dialogue = parse_dialogue(
        git_show(
            spec.commit,
            f"stories/lesson-{spec.lesson:02d}/{spec.slug}.txt",
        ).decode("utf-8")
    )
    return build_conversation_turns(story_id, dialogue)


def test_lesson_5_to_8_conversation_seed_is_a_valid_alternating_contract():
    for spec in STORIES:
        turns = _turns_for(spec)

        assert len(turns) >= 4
        assert len(turns) % 2 == 0
        assert [turn["speaker"] for turn in turns] == [
            "system",
            "student",
        ] * (len(turns) // 2)
        assert all(turn["text"].strip() for turn in turns)
        assert all(turn["targetText"] == turn["text"] for turn in turns[1::2])


def test_book_import_payload_includes_conversation_turns():
    spec = next(item for item in STORIES if item.slug == "looking-for-my-wallet")
    dialogue = parse_dialogue(
        git_show(
            spec.commit,
            f"stories/lesson-{spec.lesson:02d}/{spec.slug}.txt",
        ).decode("utf-8")
    )
    turns = build_conversation_turns(
        f"lesson-{spec.lesson}-{spec.slug}", dialogue,
    )

    assert turns[0]["text"].startswith("媽，我跟友美")
    assert turns[1]["targetText"].startswith("客廳的桌子")
