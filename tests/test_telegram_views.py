from pathlib import Path
from types import SimpleNamespace

import pytest

from englishbot.domain.models import TrainingMode
from englishbot.importing.models import (
    ExtractedVocabularyItemDraft,
    ImportLessonResult,
    LessonExtractionDraft,
    ValidationResult,
)
from englishbot.presentation.telegram_views import (
    TelegramPhotoView,
    TelegramTextView,
    build_active_session_exists_view,
    build_answer_feedback_view,
    build_current_image_preview_view,
    build_draft_preview_view,
    build_editable_topics_view,
    build_editable_words_view,
    build_help_view,
    build_image_review_attach_photo_view,
    build_image_review_prompt_edit_view,
    build_image_review_search_query_edit_view,
    build_image_review_step_view,
    build_lesson_selection_view,
    build_mode_selection_view,
    build_published_word_edit_prompt_view,
    build_quick_actions_view,
    build_status_view,
    build_topic_selection_view,
    build_training_question_view,
    build_words_menu_view,
    edit_telegram_text_view,
    send_telegram_view,
)


class _FakeMessage:
    def __init__(self) -> None:
        self.sent_text: list[tuple[str, object, object]] = []
        self.sent_photo: list[tuple[str, str, object, object]] = []

    async def reply_text(self, text: str, reply_markup=None, parse_mode=None):
        self.sent_text.append((text, reply_markup, parse_mode))
        return SimpleNamespace(message_id=len(self.sent_text))

    async def reply_photo(self, photo, caption=None, reply_markup=None, parse_mode=None):
        payload = photo.read()
        self.sent_photo.append((payload.decode("utf-8"), caption or "", reply_markup, parse_mode))
        return SimpleNamespace(message_id=100 + len(self.sent_photo))


class _FakeEditableTarget:
    def __init__(self) -> None:
        self.edits: list[tuple[str, object, object]] = []

    async def edit_message_text(self, text: str, reply_markup=None, parse_mode=None):
        self.edits.append((text, reply_markup, parse_mode))
        return SimpleNamespace(ok=True)


def test_build_training_question_view_renders_text_question_with_html_hint() -> None:
    question = SimpleNamespace(
        prompt="Translation: apple",
        mode=TrainingMode.MEDIUM,
        letter_hint="a _ _ l e",
    )

    view = build_training_question_view(question, image_path=None)

    assert isinstance(view, TelegramTextView)
    assert view.text == "<b>apple</b>\n\n<b>a _ _ l e</b>"
    assert view.parse_mode == "HTML"


def test_build_training_question_view_uses_photo_view_when_image_exists(tmp_path: Path) -> None:
    image_path = tmp_path / "question.txt"
    image_path.write_text("fake-image", encoding="utf-8")
    question = SimpleNamespace(
        prompt="Translation: dragon",
        mode=TrainingMode.EASY,
        letter_hint=None,
    )

    view = build_training_question_view(question, image_path=image_path)

    assert isinstance(view, TelegramPhotoView)
    assert view.photo_path == image_path
    assert view.caption == "<b>dragon</b>"


def test_build_answer_feedback_view_renders_incorrect_answer_with_summary() -> None:
    outcome = SimpleNamespace(
        result=SimpleNamespace(is_correct=False, expected_answer="dragon"),
        summary=SimpleNamespace(correct_answers=3, total_questions=5),
    )

    view = build_answer_feedback_view(
        outcome,
        translate=lambda key, **kwargs: (
            f"Wrong: {kwargs['expected_answer']}."
            if key == "not_quite"
            else (
                f" Done {kwargs['correct_answers']}/{kwargs['total_questions']}."
                if key == "session_complete"
                else "Correct."
            )
        ),
    )

    assert view.text == "Wrong: dragon. Done 3/5."


def test_build_draft_preview_view_formats_user_visible_preview() -> None:
    result = ImportLessonResult(
        draft=LessonExtractionDraft(
            topic_title="Fairy Tales",
            lesson_title=None,
            vocabulary_items=[
                ExtractedVocabularyItemDraft(
                    item_id="fairy-tales-dragon",
                    english_word="Dragon",
                    translation="дракон",
                    source_fragment="Dragon - дракон",
                )
            ],
        ),
        validation=ValidationResult(errors=[]),
    )

    view = build_draft_preview_view(result)

    assert "Draft preview" in view.text
    assert "Topic: Fairy Tales" in view.text
    assert "Dragon" in view.text


def test_menu_and_selection_builders_keep_user_visible_text_and_markup() -> None:
    markup = object()

    active_session = build_active_session_exists_view(text="Active session", reply_markup=markup)
    topic_view = build_topic_selection_view(text="Choose topic", reply_markup=markup)
    lesson_view = build_lesson_selection_view(text="Choose lesson", reply_markup=markup)
    mode_view = build_mode_selection_view(text="Choose mode", reply_markup=markup)
    words_menu = build_words_menu_view(text="Words menu", reply_markup=markup)
    quick_actions = build_quick_actions_view(text="Quick actions", reply_markup=markup)
    help_view = build_help_view(text="Help", reply_markup=markup)
    editable_topics = build_editable_topics_view(text="Edit topics", reply_markup=markup)
    editable_words = build_editable_words_view(text="Edit words", reply_markup=markup)
    status_view = build_status_view(text="Working", reply_markup=markup)

    assert active_session.text == "Active session"
    assert topic_view.reply_markup is markup
    assert lesson_view.text == "Choose lesson"
    assert mode_view.reply_markup is markup
    assert words_menu.text == "Words menu"
    assert quick_actions.reply_markup is markup
    assert help_view.text == "Help"
    assert editable_topics.reply_markup is markup
    assert editable_words.text == "Edit words"
    assert status_view.text == "Working"


def test_build_published_word_edit_prompt_view_returns_instruction_and_current_value_views() -> None:
    instruction_markup = object()
    current_value_markup = object()

    instruction_view, current_value_view = build_published_word_edit_prompt_view(
        instruction_text="Send updated word",
        current_value_text="Current value: Dragon: дракон",
        instruction_markup=instruction_markup,
        current_value_markup=current_value_markup,
    )

    assert instruction_view.text == "Send updated word"
    assert instruction_view.reply_markup is instruction_markup
    assert current_value_view.text == "Current value: Dragon: дракон"
    assert current_value_view.reply_markup is current_value_markup


def test_build_image_review_edit_instruction_views() -> None:
    markup = object()

    prompt_instruction, prompt_current = build_image_review_prompt_edit_view(
        instruction_text="Send new prompt",
        current_prompt_text="Current prompt:\ndragon",
        instruction_markup=markup,
    )
    query_instruction, query_current = build_image_review_search_query_edit_view(
        instruction_text="Send new query",
        current_query_text="Current query:\ndragon",
        instruction_markup=markup,
    )
    photo_instruction = build_image_review_attach_photo_view(
        instruction_text="Attach one photo",
        instruction_markup=markup,
    )

    assert prompt_instruction.text == "Send new prompt"
    assert prompt_instruction.reply_markup is markup
    assert prompt_current.text == "Current prompt:\ndragon"
    assert query_instruction.text == "Send new query"
    assert query_current.text == "Current query:\ndragon"
    assert photo_instruction.text == "Attach one photo"


def test_build_current_image_preview_view_returns_text_when_image_missing() -> None:
    view = build_current_image_preview_view(
        image_path=None,
        current_image_intro="Current image.",
        no_current_image_intro="No current image.",
    )

    assert isinstance(view, TelegramTextView)
    assert view.text == "No current image."


def test_build_image_review_step_view_includes_source_and_generation_messages() -> None:
    translations = {
        "pixabay_search_query": "Pixabay search query: {query}",
        "image_review_no_candidates_loaded": "No candidates loaded yet.",
        "pixabay_candidates_page": "Pixabay candidates page {page}",
        "image_review_local_ai_candidates": "Local AI candidates.",
        "image_review_progress": "Reviewing images {current}/{total}",
        "image_review_prompt_line": "Prompt: {prompt}",
        "image_review_prompt_usage_note": "Prompt is used for local AI generation.",
    }
    view = build_image_review_step_view(
        current_position=2,
        total_items=5,
        english_word="Dragon",
        translation="дракон",
        prompt="storybook dragon",
        candidate_source_type="pixabay",
        search_query="dragon toy",
        search_page=3,
        generation_status_messages=["Fallback images used."],
        translate=lambda key, **kwargs: translations[key].format(**kwargs),
    )

    assert "Reviewing images 2/5" in view.text
    assert "Pixabay search query: dragon toy" in view.text
    assert "Pixabay candidates page 3" in view.text
    assert "Fallback images used." in view.text


def test_build_image_review_step_view_uses_english_word_as_default_pixabay_query() -> None:
    translations = {
        "pixabay_search_query": "Pixabay search query: {query}",
        "image_review_no_candidates_loaded": "No candidates loaded yet.",
        "pixabay_candidates_page": "Pixabay candidates page {page}",
        "image_review_local_ai_candidates": "Local AI candidates.",
        "image_review_progress": "Reviewing images {current}/{total}",
        "image_review_prompt_line": "Prompt: {prompt}",
        "image_review_prompt_usage_note": "Prompt is used for local AI generation.",
    }
    view = build_image_review_step_view(
        current_position=1,
        total_items=1,
        english_word="Presents",
        translation="подарки",
        prompt="presents, cartoon style, simple, centered, white background",
        candidate_source_type="generated",
        search_query=None,
        search_page=1,
        generation_status_messages=None,
        translate=lambda key, **kwargs: translations[key].format(**kwargs),
    )

    assert "Pixabay search query: Presents" in view.text


@pytest.mark.anyio
async def test_send_telegram_view_sends_photo_view(tmp_path: Path) -> None:
    image_path = tmp_path / "preview.txt"
    image_path.write_text("photo-body", encoding="utf-8")
    message = _FakeMessage()
    view = TelegramPhotoView(photo_path=image_path, caption="Preview", parse_mode="HTML")

    result = await send_telegram_view(message, view)

    assert result.message_id == 101
    assert message.sent_photo == [("photo-body", "Preview", None, "HTML")]


@pytest.mark.anyio
async def test_edit_telegram_text_view_edits_message_with_optional_parse_mode() -> None:
    target = _FakeEditableTarget()
    view = TelegramTextView(text="Updated", reply_markup="markup", parse_mode="HTML")

    result = await edit_telegram_text_view(target, view)

    assert result.ok is True
    assert target.edits == [("Updated", "markup", "HTML")]
