from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.presentation.add_words_text import parse_edited_draft_text


def _draft() -> LessonExtractionDraft:
    return LessonExtractionDraft(
        topic_title="Fairy Tales",
        lesson_title=None,
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                item_id="princess",
                english_word="Princess",
                translation="принцесса",
                source_fragment="Princess — принцесса",
            ),
            ExtractedVocabularyItemDraft(
                item_id="prince",
                english_word="Prince",
                translation="принц",
                source_fragment="Prince — принц",
            ),
        ],
    )


def test_parse_edited_draft_text_accepts_colon_format() -> None:
    parsed = parse_edited_draft_text(
        "Topic: Fairy Tales\nLesson: -\n\nPrincess: принцесса\nPrince: принц",
        previous_draft=_draft(),
    )

    assert parsed.topic_title == "Fairy Tales"
    assert parsed.lesson_title is None
    assert [item.english_word for item in parsed.vocabulary_items] == ["Princess", "Prince"]
    assert [item.translation for item in parsed.vocabulary_items] == ["принцесса", "принц"]


def test_parse_edited_draft_text_still_accepts_pipe_format() -> None:
    parsed = parse_edited_draft_text(
        "Topic: Fairy Tales\nLesson: -\n\nPrincess | принцесса\nPrince | принц",
        previous_draft=_draft(),
    )

    assert [item.english_word for item in parsed.vocabulary_items] == ["Princess", "Prince"]
    assert [item.translation for item in parsed.vocabulary_items] == ["принцесса", "принц"]


def test_parse_edited_draft_text_accepts_preview_style_lines() -> None:
    parsed = parse_edited_draft_text(
        "Topic: Fairy Tales\nLesson: -\n\n1. Princess — принцесса\n2. Prince — принц",
        previous_draft=_draft(),
    )

    assert [item.english_word for item in parsed.vocabulary_items] == ["Princess", "Prince"]
    assert [item.translation for item in parsed.vocabulary_items] == ["принцесса", "принц"]
    assert [item.source_fragment for item in parsed.vocabulary_items] == [
        "Princess — принцесса",
        "Prince — принц",
    ]


def test_parse_edited_draft_text_strips_leading_number_from_new_items_source_fragment() -> None:
    parsed = parse_edited_draft_text(
        "Topic: Birthday\nLesson: -\n\n1. Birthday boy — именинник",
        previous_draft=LessonExtractionDraft(
            topic_title="Birthday",
            lesson_title=None,
            vocabulary_items=[],
        ),
    )

    assert [item.english_word for item in parsed.vocabulary_items] == ["Birthday boy"]
    assert [item.translation for item in parsed.vocabulary_items] == ["именинник"]
    assert [item.source_fragment for item in parsed.vocabulary_items] == [
        "Birthday boy — именинник"
    ]


def test_parse_edited_draft_text_ignores_preview_metadata_lines() -> None:
    parsed = parse_edited_draft_text(
        (
            "Draft preview\n"
            "Topic: Fairy Tales\n"
            "Lesson: -\n"
            "Items: 2\n"
            "Validation errors: 1\n"
            "- Duplicate English word inside the same lesson draft.\n"
            "\n"
            "1. Princess: принцесса\n"
            "2. Prince: принц\n"
        ),
        previous_draft=_draft(),
    )

    assert parsed.topic_title == "Fairy Tales"
    assert parsed.lesson_title is None
    assert [item.english_word for item in parsed.vocabulary_items] == ["Princess", "Prince"]
    assert [item.translation for item in parsed.vocabulary_items] == ["принцесса", "принц"]
