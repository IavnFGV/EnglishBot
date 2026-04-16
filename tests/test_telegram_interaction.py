from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from telegram.error import BadRequest

from englishbot.telegram.interaction import (
    ADD_WORDS_AWAITING_EDIT_TEXT_MODE,
    ADD_WORDS_AWAITING_TEXT_MODE,
    ADMIN_GOAL_STATE_KEYS,
    ASSIGNMENT_PROGRESS_TAG,
    AdminGoalCreationState,
    CHAT_MENU_TAG,
    IMAGE_REVIEW_CONTEXT_TAG,
    IMAGE_REVIEW_STEP_TAG,
    AddWordsDraftEditInteraction,
    ImageReviewPhotoAttachInteraction,
    PUBLISHED_WORD_EDIT_TAG,
    PUBLISHED_WORD_AWAITING_EDIT_TEXT_MODE,
    PublishedWordEditPromptInteraction,
    TRAINING_FEEDBACK_TAG,
    TRAINING_QUESTION_TAG,
    TelegramExpectedInputPrompt,
    TTS_VOICE_TAG,
    assignment_progress_interaction_id,
    chat_menu_interaction_id,
    clear_admin_goal_creation_state,
    clear_admin_goal_prompt_interaction,
    clear_add_words_draft_edit_interaction,
    clear_add_words_text_interaction,
    clear_expected_user_input,
    clear_image_review_photo_attach_interaction,
    clear_image_review_text_edit_interaction,
    clear_published_word_edit_prompt_interaction,
    edit_expected_user_input_prompt,
    finish_interaction,
    finish_image_review_interaction,
    finish_lesson_interaction,
    finish_published_word_edit_interaction,
    get_admin_goal_creation_state,
    get_admin_goal_prompt_mode,
    get_image_review_photo_attach_interaction,
    get_image_review_text_edit_interaction,
    get_expected_user_input_prompt,
    get_add_words_draft_edit_interaction,
    get_published_word_edit_prompt_interaction,
    has_active_interaction_mode,
    is_add_words_text_interaction,
    lesson_interaction_id,
    published_word_edit_interaction_id,
    replace_chat_menu_message,
    replace_image_review_context_message,
    replace_image_review_step_messages,
    replace_lesson_feedback_message,
    replace_lesson_question_message,
    replace_tts_voice_message,
    remember_expected_user_input,
    replace_flow_message,
    start_admin_goal_creation_state,
    start_admin_goal_prompt_interaction,
    start_add_words_draft_edit_interaction,
    start_add_words_text_interaction,
    start_image_review_photo_attach_interaction,
    start_image_review_text_edit_interaction,
    start_published_word_edit_prompt_interaction,
    start_published_word_edit_interaction,
    tts_voice_interaction_id,
    update_admin_goal_creation_state,
)


def test_remember_and_get_expected_user_input_prompt() -> None:
    context = SimpleNamespace(user_data={})

    remember_expected_user_input(context, chat_id=101, message_id=202)

    assert get_expected_user_input_prompt(context) == TelegramExpectedInputPrompt(
        chat_id=101,
        message_id=202,
    )


def test_named_interaction_ids_are_stable() -> None:
    assert lesson_interaction_id(session_id="lesson-1") == "lesson-1"
    assert chat_menu_interaction_id(user_id=7) == "chat-menu:7"
    assert published_word_edit_interaction_id(user_id=7) == "published-word-edit:7"
    assert tts_voice_interaction_id(user_id=7) == "tts-voice:7"
    assert (
        assignment_progress_interaction_id(user_id=7, kind_value="homework", goal_id="goal-1")
        == "assignment-progress:7:homework:goal-1"
    )


def test_named_interaction_tags_are_stable() -> None:
    assert IMAGE_REVIEW_STEP_TAG == "image_review_step"
    assert IMAGE_REVIEW_CONTEXT_TAG == "image_review_context"
    assert PUBLISHED_WORD_EDIT_TAG == "published_word_edit"
    assert TRAINING_QUESTION_TAG == "training_question"
    assert TRAINING_FEEDBACK_TAG == "training_feedback"
    assert TTS_VOICE_TAG == "tts_voice"
    assert ASSIGNMENT_PROGRESS_TAG == "assignment_progress"
    assert CHAT_MENU_TAG == "chat_menu"


def test_named_editor_interaction_modes_are_stable() -> None:
    assert ADD_WORDS_AWAITING_TEXT_MODE == "awaiting_raw_text"
    assert ADD_WORDS_AWAITING_EDIT_TEXT_MODE == "awaiting_edit_text"
    assert PUBLISHED_WORD_AWAITING_EDIT_TEXT_MODE == "awaiting_published_word_edit_text"


def test_admin_goal_state_keys_are_stable() -> None:
    assert ADMIN_GOAL_STATE_KEYS == (
        "admin_goal_period",
        "admin_goal_type",
        "admin_goal_target_count",
        "admin_goal_source",
        "admin_goal_deadline_date",
        "admin_goal_manual_topic_id",
        "admin_goal_manual_word_ids",
        "admin_goal_recipient_user_ids",
        "admin_goal_recipients_page",
    )


def test_clear_expected_user_input_prompt() -> None:
    context = SimpleNamespace(
        user_data={"expected_user_input_state": {"chat_id": 1, "message_id": 2}}
    )

    clear_expected_user_input(context)

    assert get_expected_user_input_prompt(context) is None


def test_start_and_clear_image_review_text_edit_interaction() -> None:
    context = SimpleNamespace(user_data={})

    start_image_review_text_edit_interaction(
        context,
        mode="awaiting_image_review_prompt_text",
        flow_id="review-1",
        item_id="dragon",
        chat_id=5,
        message_id=6,
    )

    assert context.user_data["words_flow_mode"] == "awaiting_image_review_prompt_text"
    assert context.user_data["image_review_flow_id"] == "review-1"
    assert context.user_data["image_review_item_id"] == "dragon"
    assert get_expected_user_input_prompt(context) == TelegramExpectedInputPrompt(
        chat_id=5,
        message_id=6,
    )

    clear_image_review_text_edit_interaction(context)

    assert context.user_data.get("words_flow_mode") is None
    assert context.user_data.get("image_review_flow_id") is None
    assert context.user_data.get("image_review_item_id") is None
    assert get_expected_user_input_prompt(context) is None


def test_get_image_review_text_edit_interaction_returns_structured_state() -> None:
    context = SimpleNamespace(user_data={})

    start_image_review_text_edit_interaction(
        context,
        mode="awaiting_image_review_prompt_text",
        flow_id="review-1",
        item_id="dragon",
        chat_id=5,
        message_id=6,
    )

    interaction = get_image_review_text_edit_interaction(context)

    assert interaction is not None
    assert interaction.mode == "awaiting_image_review_prompt_text"
    assert interaction.flow_id == "review-1"
    assert interaction.item_id == "dragon"


def test_start_get_and_clear_image_review_photo_attach_interaction() -> None:
    context = SimpleNamespace(user_data={})

    start_image_review_photo_attach_interaction(
        context,
        flow_id="review-1",
        item_id="dragon",
    )

    assert get_image_review_photo_attach_interaction(context) == ImageReviewPhotoAttachInteraction(
        flow_id="review-1",
        item_id="dragon",
    )

    clear_image_review_photo_attach_interaction(context)

    assert get_image_review_photo_attach_interaction(context) is None


def test_start_and_clear_add_words_text_interaction() -> None:
    context = SimpleNamespace(user_data={})

    start_add_words_text_interaction(context)
    assert is_add_words_text_interaction(context) is True

    clear_add_words_text_interaction(context)
    assert is_add_words_text_interaction(context) is False


def test_has_active_interaction_mode_reflects_words_flow_mode_state() -> None:
    context = SimpleNamespace(user_data={})

    assert has_active_interaction_mode(context) is False

    start_add_words_text_interaction(context)

    assert has_active_interaction_mode(context) is True


def test_start_get_and_clear_add_words_draft_edit_interaction() -> None:
    context = SimpleNamespace(user_data={})

    start_add_words_draft_edit_interaction(context, flow_id="flow-1")

    assert get_add_words_draft_edit_interaction(context) == AddWordsDraftEditInteraction(
        flow_id="flow-1"
    )

    clear_add_words_draft_edit_interaction(context)

    assert get_add_words_draft_edit_interaction(context) is None


def test_start_get_and_clear_published_word_edit_prompt_interaction() -> None:
    context = SimpleNamespace(user_data={})

    start_published_word_edit_prompt_interaction(
        context,
        topic_id="weather",
        item_id="cloud",
        chat_id=10,
        message_id=11,
    )

    assert get_published_word_edit_prompt_interaction(context) == PublishedWordEditPromptInteraction(
        topic_id="weather",
        item_id="cloud",
    )
    assert get_expected_user_input_prompt(context) == TelegramExpectedInputPrompt(
        chat_id=10,
        message_id=11,
    )

    clear_published_word_edit_prompt_interaction(context)

    assert get_published_word_edit_prompt_interaction(context) is None
    assert get_expected_user_input_prompt(context) is None


def test_start_and_clear_admin_goal_prompt_interaction() -> None:
    context = SimpleNamespace(user_data={})

    start_admin_goal_prompt_interaction(
        context,
        mode="awaiting_admin_goal_deadline_text",
        chat_id=7,
        message_id=8,
    )

    assert context.user_data["words_flow_mode"] == "awaiting_admin_goal_deadline_text"
    assert get_expected_user_input_prompt(context) == TelegramExpectedInputPrompt(
        chat_id=7,
        message_id=8,
    )

    clear_admin_goal_prompt_interaction(context)

    assert context.user_data.get("words_flow_mode") is None
    assert get_expected_user_input_prompt(context) is None


def test_get_admin_goal_prompt_mode_returns_named_mode() -> None:
    context = SimpleNamespace(user_data={})

    start_admin_goal_prompt_interaction(
        context,
        mode="awaiting_admin_goal_deadline_text",
        chat_id=7,
        message_id=8,
    )

    assert get_admin_goal_prompt_mode(context) == "awaiting_admin_goal_deadline_text"


def test_start_update_get_and_clear_admin_goal_creation_state() -> None:
    context = SimpleNamespace(user_data={})

    start_admin_goal_creation_state(context)
    assert get_admin_goal_creation_state(context) == AdminGoalCreationState(
        recipient_user_ids=frozenset()
    )

    update_admin_goal_creation_state(
        context,
        goal_period="homework",
        goal_type="word_level_homework",
        target_count=7,
        source="recent",
        deadline_date="2026-04-07",
        manual_topic_id="animals",
        manual_word_ids={"cloud", "sun"},
        recipient_user_ids={77, 88},
        recipients_page=2,
    )

    assert get_admin_goal_creation_state(context) == AdminGoalCreationState(
        goal_period="homework",
        goal_type="word_level_homework",
        target_count=7,
        source="recent",
        deadline_date="2026-04-07",
        manual_topic_id="animals",
        manual_word_ids=frozenset({"cloud", "sun"}),
        recipient_user_ids=frozenset({77, 88}),
        recipients_page=2,
    )

    clear_admin_goal_creation_state(context)

    assert get_admin_goal_creation_state(context) == AdminGoalCreationState()


def test_edit_expected_user_input_prompt_returns_false_without_prompt() -> None:
    context = SimpleNamespace(user_data={}, bot=SimpleNamespace())

    edited = asyncio.run(
        edit_expected_user_input_prompt(
            context,
            text="hello",
            reply_markup=None,
        )
    )

    assert edited is False


def test_edit_expected_user_input_prompt_edits_stored_prompt() -> None:
    calls: list[dict[str, object]] = []

    async def fake_edit_message_text(**kwargs):
        calls.append(kwargs)

    context = SimpleNamespace(
        user_data={"expected_user_input_state": {"chat_id": 11, "message_id": 22}},
        bot=SimpleNamespace(edit_message_text=fake_edit_message_text),
    )

    edited = asyncio.run(
        edit_expected_user_input_prompt(
            context,
            text="updated",
            reply_markup="markup",
        )
    )

    assert edited is True
    assert calls == [
        {
            "chat_id": 11,
            "message_id": 22,
            "text": "updated",
            "reply_markup": "markup",
        }
    ]


def test_edit_expected_user_input_prompt_treats_not_modified_as_success() -> None:
    async def fake_edit_message_text(**kwargs):  # noqa: ARG001
        raise BadRequest("Message is not modified")

    context = SimpleNamespace(
        user_data={"expected_user_input_state": {"chat_id": 11, "message_id": 22}},
        bot=SimpleNamespace(edit_message_text=fake_edit_message_text),
    )

    edited = asyncio.run(
        edit_expected_user_input_prompt(
            context,
            text="updated",
            reply_markup=None,
        )
    )

    assert edited is True


class _FakeTracked:
    def __init__(self, *, flow_id: str, chat_id: int, message_id: int, tag: str) -> None:
        self.flow_id = flow_id
        self.chat_id = chat_id
        self.message_id = message_id
        self.tag = tag


class _FakeRegistry:
    def __init__(self) -> None:
        self.items: list[_FakeTracked] = []

    def list(self, *, flow_id: str, tag: str | None = None):
        return [
            item
            for item in self.items
            if item.flow_id == flow_id and (tag is None or item.tag == tag)
        ]

    def track(self, *, flow_id: str, chat_id: int, message_id: int, tag: str) -> None:
        self.items.append(
            _FakeTracked(flow_id=flow_id, chat_id=chat_id, message_id=message_id, tag=tag)
        )

    def remove(self, *, flow_id: str, chat_id: int, message_id: int) -> None:
        self.items = [
            item
            for item in self.items
            if not (
                item.flow_id == flow_id
                and item.chat_id == chat_id
                and item.message_id == message_id
            )
        ]

    def clear(self, *, flow_id: str, tag: str | None = None) -> None:
        self.items = [
            item
            for item in self.items
            if not (item.flow_id == flow_id and (tag is None or item.tag == tag))
        ]


@pytest.mark.anyio
async def test_replace_flow_message_replaces_previous_tracked_message() -> None:
    registry = _FakeRegistry()
    registry.track(flow_id="lesson-1", chat_id=10, message_id=20, tag="question")
    deleted: list[tuple[int, int]] = []

    async def fake_delete_message(*, chat_id: int, message_id: int) -> None:
        deleted.append((chat_id, message_id))

    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(bot_data={"telegram_flow_message_repository": registry}),
        bot=SimpleNamespace(delete_message=fake_delete_message),
    )
    message = SimpleNamespace(chat_id=10, message_id=30)

    await replace_flow_message(
        context,
        flow_id="lesson-1",
        tag="question",
        message=message,
        fallback_chat_id=10,
    )

    assert deleted == [(10, 20)]
    tracked = registry.list(flow_id="lesson-1", tag="question")
    assert [(item.chat_id, item.message_id) for item in tracked] == [(10, 30)]


@pytest.mark.anyio
async def test_finish_interaction_clears_tags_and_prompt_state() -> None:
    registry = _FakeRegistry()
    registry.track(flow_id="lesson-1", chat_id=10, message_id=20, tag="question")
    registry.track(flow_id="lesson-1", chat_id=10, message_id=21, tag="feedback")
    deleted: list[tuple[int, int]] = []

    async def fake_delete_message(*, chat_id: int, message_id: int) -> None:
        deleted.append((chat_id, message_id))

    context = SimpleNamespace(
        user_data={"expected_user_input_state": {"chat_id": 10, "message_id": 99}},
        application=SimpleNamespace(bot_data={"telegram_flow_message_repository": registry}),
        bot=SimpleNamespace(delete_message=fake_delete_message),
    )

    await finish_interaction(
        context,
        flow_id="lesson-1",
        tags=("question", "feedback"),
        clear_expected_input_prompt=True,
    )

    assert deleted == [(10, 20), (10, 21)]
    assert registry.list(flow_id="lesson-1", tag="question") == []
    assert registry.list(flow_id="lesson-1", tag="feedback") == []
    assert get_expected_user_input_prompt(context) is None


@pytest.mark.anyio
async def test_lesson_interaction_helpers_use_named_lesson_tags() -> None:
    registry = _FakeRegistry()
    deleted: list[tuple[int, int]] = []

    async def fake_delete_message(*, chat_id: int, message_id: int) -> None:
        deleted.append((chat_id, message_id))

    context = SimpleNamespace(
        user_data={"expected_user_input_state": {"chat_id": 10, "message_id": 99}},
        application=SimpleNamespace(bot_data={"telegram_flow_message_repository": registry}),
        bot=SimpleNamespace(delete_message=fake_delete_message),
    )

    await replace_lesson_question_message(
        context,
        session_id="lesson-1",
        message=SimpleNamespace(chat_id=10, message_id=20),
        fallback_chat_id=10,
    )
    await replace_lesson_feedback_message(
        context,
        session_id="lesson-1",
        message=SimpleNamespace(chat_id=10, message_id=21),
        fallback_chat_id=10,
    )

    assert [(item.tag, item.message_id) for item in registry.items] == [
        ("training_question", 20),
        ("training_feedback", 21),
    ]

    await finish_lesson_interaction(
        context,
        session_id="lesson-1",
        clear_expected_input_prompt=True,
    )

    assert deleted == [(10, 20), (10, 21)]
    assert registry.items == []
    assert get_expected_user_input_prompt(context) is None


@pytest.mark.anyio
async def test_replace_chat_menu_message_uses_named_chat_menu_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _FakeRegistry()
    registry.track(flow_id="chat-menu:7", chat_id=10, message_id=19, tag="chat_menu")
    deleted: list[tuple[int, int]] = []
    sent_views: list[object] = []

    async def fake_delete_message(*, chat_id: int, message_id: int) -> None:
        deleted.append((chat_id, message_id))

    async def fake_send_telegram_view(message, view):
        sent_views.append(view)
        assert getattr(message, "chat_id", None) == 10
        return SimpleNamespace(chat_id=10, message_id=20)

    monkeypatch.setattr("englishbot.bot.send_telegram_view", fake_send_telegram_view)
    monkeypatch.setattr(
        "englishbot.telegram.interaction.quick_actions_view",
        lambda **kwargs: {"kind": "quick-actions", "user_id": kwargs["user"].id},
    )
    monkeypatch.setattr(
        "englishbot.bot._visible_command_rows",
        lambda context, user_id=None: [["/start"]],  # noqa: ARG005
    )
    monkeypatch.setattr(
        "englishbot.bot.menu_chat_menu_keyboard",
        lambda *, command_rows: {"kind": "chat-menu-markup", "rows": command_rows},
    )

    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(bot_data={"telegram_flow_message_repository": registry}),
        bot=SimpleNamespace(delete_message=fake_delete_message),
    )

    await replace_chat_menu_message(
        context,
        message=SimpleNamespace(chat_id=10, message_id=5),
        user=SimpleNamespace(id=7),
    )

    assert sent_views == [{"kind": "quick-actions", "user_id": 7}]
    assert deleted == [(10, 19)]
    assert [(item.flow_id, item.tag, item.message_id) for item in registry.items] == [
        ("chat-menu:7", "chat_menu", 20)
    ]


@pytest.mark.anyio
async def test_replace_tts_voice_message_uses_named_tts_flow() -> None:
    registry = _FakeRegistry()
    registry.track(flow_id="tts-voice:7", chat_id=10, message_id=19, tag="tts_voice")
    deleted: list[tuple[int, int]] = []
    reply_calls: list[object] = []

    async def fake_delete_message(*, chat_id: int, message_id: int) -> None:
        deleted.append((chat_id, message_id))

    async def fake_reply_voice(*, voice):
        reply_calls.append(voice)
        return SimpleNamespace(chat_id=10, message_id=20)

    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(bot_data={"telegram_flow_message_repository": registry}),
        bot=SimpleNamespace(delete_message=fake_delete_message),
    )

    sent_message = await replace_tts_voice_message(
        context,
        user_id=7,
        message=SimpleNamespace(chat_id=10, message_id=5, reply_voice=fake_reply_voice),
        voice="voice-file-id",
    )

    assert sent_message.message_id == 20
    assert reply_calls == ["voice-file-id"]
    assert deleted == [(10, 19)]
    assert [(item.flow_id, item.tag, item.message_id) for item in registry.items] == [
        ("tts-voice:7", "tts_voice", 20)
    ]


@pytest.mark.anyio
async def test_image_review_interaction_helpers_replace_and_finish_tracked_messages() -> None:
    registry = _FakeRegistry()
    registry.track(flow_id="review-1", chat_id=10, message_id=19, tag="image_review_context")
    registry.track(flow_id="review-1", chat_id=10, message_id=30, tag="image_review_step")
    registry.track(flow_id="review-1", chat_id=10, message_id=31, tag="image_review_step")
    deleted: list[tuple[int, int]] = []

    async def fake_delete_message(*, chat_id: int, message_id: int) -> None:
        deleted.append((chat_id, message_id))

    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(bot_data={"telegram_flow_message_repository": registry}),
        bot=SimpleNamespace(delete_message=fake_delete_message),
    )

    await replace_image_review_context_message(
        context,
        flow_id="review-1",
        message=SimpleNamespace(chat_id=10, message_id=20),
        fallback_chat_id=10,
    )
    await replace_image_review_step_messages(
        context,
        flow_id="review-1",
        messages=[
            SimpleNamespace(chat_id=10, message_id=40),
            SimpleNamespace(chat_id=10, message_id=41),
        ],
        fallback_chat_id=10,
    )

    assert deleted == [(10, 19), (10, 30), (10, 31)]
    assert [(item.tag, item.message_id) for item in registry.items] == [
        ("image_review_context", 20),
        ("image_review_step", 40),
        ("image_review_step", 41),
    ]

    await finish_image_review_interaction(context, flow_id="review-1")

    assert deleted == [(10, 19), (10, 30), (10, 31), (10, 20), (10, 40), (10, 41)]
    assert registry.items == []


@pytest.mark.anyio
async def test_published_word_edit_interaction_tracks_and_finishes() -> None:
    registry = _FakeRegistry()
    deleted: list[tuple[int, int]] = []

    async def fake_delete_message(*, chat_id: int, message_id: int) -> None:
        deleted.append((chat_id, message_id))

    source_message = SimpleNamespace(chat_id=10, message_id=20)
    helper_message = SimpleNamespace(chat_id=10, message_id=21)
    context = SimpleNamespace(
        user_data={"expected_user_input_state": {"chat_id": 10, "message_id": 99}},
        application=SimpleNamespace(bot_data={"telegram_flow_message_repository": registry}),
        bot=SimpleNamespace(delete_message=fake_delete_message),
    )

    await start_published_word_edit_interaction(
        context,
        user_id=7,
        source_message=source_message,
        helper_message=helper_message,
        fallback_chat_id=10,
    )

    assert [(item.tag, item.message_id) for item in registry.items] == [
        ("published_word_edit", 20),
        ("published_word_edit", 21),
    ]

    await finish_published_word_edit_interaction(
        context,
        user_id=7,
        keep_source_message=True,
        source_message=source_message,
    )

    assert deleted == [(10, 21)]
    assert registry.items == []
    assert get_expected_user_input_prompt(context) is None
