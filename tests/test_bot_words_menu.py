from types import SimpleNamespace

import pytest
from telegram.error import BadRequest

from englishbot.bot import (
    _draft_review_markup,
    _draft_review_keyboard,
    _image_review_markup,
    _image_review_keyboard,
    _published_image_items_keyboard,
    _words_menu_keyboard,
    words_add_words_callback_handler,
    words_edit_images_callback_handler,
    words_menu_callback_handler,
    words_topics_callback_handler,
)


class _FakeQuery:
    def __init__(self) -> None:
        self.answered = False
        self.edits: list[tuple[str, object]] = []

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, reply_markup=None) -> None:  # noqa: ARG002
        self.edits.append((text, reply_markup))
        raise BadRequest("Message is not modified")


@pytest.mark.anyio
async def test_words_menu_callback_handler_ignores_message_not_modified() -> None:
    query = _FakeQuery()
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "editor_user_ids": {123},
            }
        )
    )

    await words_menu_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True


class _RecordingQuery:
    def __init__(self) -> None:
        self.answered = False
        self.edits: list[tuple[str, object]] = []

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, reply_markup=None) -> None:  # noqa: ARG002
        self.edits.append((text, reply_markup))


@pytest.mark.anyio
async def test_words_topics_callback_handler_opens_topic_list() -> None:
    query = _RecordingQuery()
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={}),
    )
    context.application.bot_data["training_service"] = SimpleNamespace(
        list_topics=lambda: [
            SimpleNamespace(id="weather", title="Weather"),
            SimpleNamespace(id="school", title="School"),
        ]
    )

    await words_topics_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True
    assert query.edits[-1][0] == "Choose a topic to start training."
    assert query.edits[-1][1] is not None


@pytest.mark.anyio
async def test_words_add_words_callback_handler_enters_editor_flow() -> None:
    query = _RecordingQuery()
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(bot_data={"editor_user_ids": {123}}),
    )

    await words_add_words_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True
    assert context.user_data["words_flow_mode"] == "awaiting_raw_text"
    assert query.edits[-1][0].startswith("Send the raw lesson text in one message.")


@pytest.mark.anyio
async def test_words_edit_images_callback_handler_opens_topic_list() -> None:
    query = _RecordingQuery()
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "editor_user_ids": {123},
                "list_editable_topics_use_case": SimpleNamespace(
                    execute=lambda: [
                        SimpleNamespace(id="school-subjects", title="School Subjects"),
                        SimpleNamespace(id="fairy-tales", title="Fairy Tales"),
                    ]
                ),
            }
        ),
    )

    await words_edit_images_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True
    assert query.edits[-1][0] == "Choose a topic to edit word images."
    assert query.edits[-1][1] is not None


def test_published_image_items_keyboard_uses_short_index_based_callback_data() -> None:
    keyboard = _published_image_items_keyboard(
        topic_id="school-subjects",
        raw_items=[
            {
                "id": "school-subjects-physical-education",
                "english_word": "Physical Education",
                "translation": "физкультура",
            }
        ],
    )

    button = keyboard.inline_keyboard[0][0]
    assert button.callback_data == "words:edit_published_image:school-subjects:0"
    assert len(button.callback_data) < 64


def test_image_review_keyboard_uses_short_callback_data_for_long_item_id() -> None:
    current_item = SimpleNamespace(
        candidates=[object(), object(), object()],
        search_query="Dragon",
        search_page=1,
    )
    keyboard = _image_review_keyboard(
        flow_id="review123",
        current_item=current_item,
    )

    assert keyboard.inline_keyboard[0][0].callback_data == "words:image_pick:review123:0"


def test_words_menu_keyboard_uses_russian_labels_when_requested() -> None:
    keyboard = _words_menu_keyboard(is_editor=True, language="ru")

    assert keyboard.inline_keyboard[0][0].text == "Темы тренировки"
    assert keyboard.inline_keyboard[1][0].text == "Добавить слова"
    assert keyboard.inline_keyboard[2][0].text == "Редактировать слова"


def test_image_review_keyboard_uses_russian_labels_when_requested() -> None:
    current_item = SimpleNamespace(
        candidates=[object(), object()],
        search_query="Dragon",
        search_page=2,
    )
    keyboard = _image_review_keyboard(
        flow_id="review123",
        current_item=current_item,
        language="ru",
    )

    assert keyboard.inline_keyboard[0][0].text == "Выбрать 1"
    assert keyboard.inline_keyboard[0][1].text == "Выбрать 2"
    assert keyboard.inline_keyboard[1][0].text == "Искать картинки"
    assert keyboard.inline_keyboard[2][0].text == "Предыдущие 6"
    assert keyboard.inline_keyboard[2][1].text == "Следующие 6"
    assert keyboard.inline_keyboard[0][1].callback_data == "words:image_pick:review123:1"
    assert keyboard.inline_keyboard[2][0].callback_data == "words:image_previous:review123"
    assert keyboard.inline_keyboard[2][1].callback_data == "words:image_next:review123"
    assert keyboard.inline_keyboard[3][0].callback_data == "words:image_edit_search_query:review123"
    assert keyboard.inline_keyboard[4][1].callback_data == "words:image_attach_photo:review123"
    assert keyboard.inline_keyboard[5][0].callback_data == "words:image_show_json:review123"
    assert keyboard.inline_keyboard[6][0].callback_data == "words:image_skip:review123"
    assert all(
        len(button.callback_data) < 64
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data is not None
    )


def test_image_review_keyboard_includes_show_json_button() -> None:
    current_item = SimpleNamespace(
        candidates=[object()],
        search_query=None,
        search_page=1,
    )

    keyboard = _image_review_keyboard(
        flow_id="review123",
        current_item=current_item,
    )

    assert keyboard.inline_keyboard[4][0].callback_data == "words:image_show_json:review123"


def test_image_review_keyboard_lays_out_six_pick_buttons_in_two_rows() -> None:
    current_item = SimpleNamespace(
        candidates=[object(), object(), object(), object(), object(), object()],
        search_query="Dragon",
        search_page=1,
    )

    keyboard = _image_review_keyboard(
        flow_id="review123",
        current_item=current_item,
    )

    assert [button.text for button in keyboard.inline_keyboard[0]] == ["Use 1", "Use 2", "Use 3"]
    assert [button.text for button in keyboard.inline_keyboard[1]] == ["Use 4", "Use 5", "Use 6"]


def test_image_review_keyboard_shows_previous_and_next_on_later_pages() -> None:
    current_item = SimpleNamespace(
        candidates=[object()],
        search_query="Dragon",
        search_page=2,
    )

    keyboard = _image_review_keyboard(
        flow_id="review123",
        current_item=current_item,
    )

    assert [button.text for button in keyboard.inline_keyboard[2]] == ["Previous 6", "Next 6"]


def test_draft_review_keyboard_hides_auto_images_button_when_generation_is_unavailable() -> None:
    keyboard = _draft_review_keyboard(
        flow_id="flow123",
        is_valid=True,
        show_auto_image_button=False,
    )

    assert [button.text for button in keyboard.inline_keyboard[0]] == ["Manual Image Review"]


def test_draft_review_keyboard_hides_regenerate_button_when_smart_parsing_is_unavailable() -> None:
    keyboard = _draft_review_keyboard(
        flow_id="flow123",
        is_valid=True,
        show_regenerate_button=False,
    )

    assert [button.text for button in keyboard.inline_keyboard[2]] == ["Edit Text"]


def test_draft_review_markup_centralizes_ai_button_visibility_from_context() -> None:
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "smart_parsing_available": False,
                "local_image_generation_available": False,
                "telegram_ui_language": "en",
            }
        )
    )

    keyboard = _draft_review_markup(
        flow_id="flow123",
        is_valid=True,
        context=context,
        user=SimpleNamespace(language_code="en"),
    )

    assert [button.text for button in keyboard.inline_keyboard[0]] == ["Manual Image Review"]
    assert [button.text for button in keyboard.inline_keyboard[2]] == ["Edit Text"]


def test_image_review_keyboard_hides_generate_button_when_generation_is_unavailable() -> None:
    current_item = SimpleNamespace(
        candidates=[object()],
        search_query=None,
        search_page=1,
    )

    keyboard = _image_review_keyboard(
        flow_id="review123",
        current_item=current_item,
        show_generate_image_button=False,
    )

    assert [button.text for button in keyboard.inline_keyboard[1]] == ["Search Images"]


def test_image_review_markup_centralizes_generate_button_visibility_from_context() -> None:
    current_item = SimpleNamespace(
        candidates=[object()],
        search_query=None,
        search_page=1,
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "smart_parsing_available": True,
                "local_image_generation_available": False,
                "telegram_ui_language": "en",
            }
        )
    )

    keyboard = _image_review_markup(
        flow_id="review123",
        current_item=current_item,
        context=context,
        user=SimpleNamespace(language_code="en"),
    )

    assert [button.text for button in keyboard.inline_keyboard[1]] == ["Search Images"]
