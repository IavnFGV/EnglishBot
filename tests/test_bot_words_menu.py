from types import SimpleNamespace

import pytest
from telegram.error import BadRequest

from englishbot.application.homework_progress_use_cases import AssignmentLaunchView, AssignmentSessionKind
from englishbot.presentation.telegram_menu_access import TelegramMenuAccessPolicy
from englishbot.bot import (
    _assign_menu_keyboard,
    _assignment_round_complete_keyboard,
    _admin_goal_manual_keyboard,
    _admin_goal_recipients_keyboard,
    assign_goal_detail_callback_handler,
    assign_user_detail_callback_handler,
    _goal_setup_keyboard,
    _goal_target_keyboard,
    _goal_source_keyboard,
    _admin_goal_period_keyboard,
    _admin_goal_target_keyboard,
    _admin_goal_source_keyboard,
    _draft_review_markup,
    _draft_review_keyboard,
    _editable_words_keyboard,
    _image_review_markup,
    _image_review_keyboard,
    _published_image_topics_keyboard,
    _mode_keyboard,
    _start_menu_keyboard,
    _topic_keyboard,
    _published_image_items_keyboard,
    _words_menu_keyboard,
    _editable_topics_keyboard,
    game_mode_placeholder_callback_handler,
    start_assignment_round_callback_handler,
    start_assignment_unavailable_callback_handler,
    words_add_words_callback_handler,
    words_goals_callback_handler,
    goal_target_preset_callback_handler,
    goal_text_handler,
    admin_users_progress_callback_handler,
    admin_goal_period_callback_handler,
    assign_menu_callback_handler,
    words_edit_images_callback_handler,
    words_menu_callback_handler,
    words_topics_callback_handler,
)
from englishbot.domain.models import TrainingMode


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
    context.application.bot_data["content_store"] = SimpleNamespace(
        list_vocabulary_by_topic=lambda topic_id: {
            "weather": [object(), object(), object()],
            "school": [object(), object()],
        }[topic_id]
    )

    await words_topics_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True
    assert query.edits[-1][0] == "Choose a topic to start training."
    assert query.edits[-1][1] is not None
    assert query.edits[-1][1].inline_keyboard[0][0].text == "Weather (3)"
    assert query.edits[-1][1].inline_keyboard[1][0].text == "School (2)"


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
                "content_store": SimpleNamespace(
                    list_vocabulary_by_topic=lambda topic_id: {
                        "school-subjects": [object(), object()],
                        "fairy-tales": [object(), object(), object(), object()],
                    }[topic_id]
                ),
            }
        ),
    )

    await words_edit_images_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True
    assert query.edits[-1][0] == "Choose a topic to edit word images."
    assert query.edits[-1][1] is not None
    assert query.edits[-1][1].inline_keyboard[0][0].text == "School Subjects (2)"
    assert query.edits[-1][1].inline_keyboard[1][0].text == "Fairy Tales (4)"


@pytest.mark.anyio
async def test_words_goals_callback_handler_shows_progress_summary() -> None:
    query = _RecordingQuery()
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "homework_progress_use_case": SimpleNamespace(
                    get_summary=lambda user_id: SimpleNamespace(
                        correct_answers=7,
                        incorrect_answers=2,
                        game_streak_days=3,
                        weekly_points=18,
                        active_goals=[],
                    )
                ),
            }
        ),
        user_data={},
    )

    await words_goals_callback_handler(update, context)  # type: ignore[arg-type]

    assert "Correct: 7" in query.edits[-1][0]


@pytest.mark.anyio
async def test_words_goals_callback_handler_ignores_message_not_modified() -> None:
    query = _FakeQuery()
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "homework_progress_use_case": SimpleNamespace(
                    get_summary=lambda user_id: SimpleNamespace(
                        correct_answers=7,
                        incorrect_answers=2,
                        game_streak_days=3,
                        weekly_points=18,
                        active_goals=[],
                    )
                ),
            }
        ),
        user_data={},
    )

    await words_goals_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True


@pytest.mark.anyio
async def test_admin_goal_period_callback_handler_uses_homework_goal_type_for_homework_period() -> None:
    query = _RecordingQuery()
    context = SimpleNamespace(user_data={}, application=SimpleNamespace(bot_data={}))

    await admin_goal_period_callback_handler(
        SimpleNamespace(
            callback_query=SimpleNamespace(
                answer=query.answer,
                edit_message_text=query.edit_message_text,
                data="words:admin_goal_period:homework",
            ),
            effective_user=SimpleNamespace(id=123),
        ),
        context,  # type: ignore[arg-type]
    )

    assert context.user_data["admin_goal_period"] == "homework"
    assert context.user_data["admin_goal_type"] == "word_level_homework"


@pytest.mark.anyio
async def test_goal_target_custom_text_flow_accepts_manual_target() -> None:
    query = _RecordingQuery()
    context = SimpleNamespace(user_data={}, application=SimpleNamespace(bot_data={}))

    await goal_target_preset_callback_handler(
        SimpleNamespace(callback_query=SimpleNamespace(answer=query.answer, edit_message_text=query.edit_message_text, data="words:goal_target:custom"), effective_user=SimpleNamespace(id=123)),
        context,  # type: ignore[arg-type]
    )
    assert context.user_data["words_flow_mode"] == "awaiting_goal_target_text"

    class _Message:
        async def reply_text(self, *args, **kwargs) -> None:  # noqa: ARG002
            return None

    message = SimpleNamespace(
        text="12",
        reply_text=_Message().reply_text,
    )
    await goal_text_handler(
        SimpleNamespace(effective_message=message, effective_user=SimpleNamespace(id=123)),
        context,  # type: ignore[arg-type]
    )
    assert context.user_data["goal_target_count"] == 12


@pytest.mark.anyio
async def test_goal_target_custom_text_flow_edits_existing_prompt_message_when_available() -> None:
    class _Bot:
        def __init__(self) -> None:
            self.edits: list[tuple[int, int, str, object]] = []
            self.deletes: list[tuple[int, int]] = []

        async def edit_message_text(self, *, chat_id, message_id, text, reply_markup=None):  # noqa: ANN001
            self.edits.append((chat_id, message_id, text, reply_markup))

        async def delete_message(self, *, chat_id, message_id):  # noqa: ANN001
            self.deletes.append((chat_id, message_id))

    class _Message:
        def __init__(self) -> None:
            self.reply_calls = 0

        async def reply_text(self, *args, **kwargs) -> None:  # noqa: ARG002
            self.reply_calls += 1

    bot = _Bot()
    message = _Message()
    context = SimpleNamespace(
        user_data={
            "words_flow_mode": "awaiting_goal_target_text",
            "expected_user_input_state": {"chat_id": 77, "message_id": 88},
        },
        application=SimpleNamespace(bot_data={}),
        bot=bot,
    )

    await goal_text_handler(
        SimpleNamespace(
            effective_message=SimpleNamespace(
                text="12",
                reply_text=message.reply_text,
                chat_id=55,
                message_id=66,
            ),
            effective_user=SimpleNamespace(id=123),
        ),
        context,  # type: ignore[arg-type]
    )

    assert context.user_data["goal_target_count"] == 12
    assert bot.edits[-1][0:3] == (77, 88, "Choose a word source:")
    assert bot.deletes == [(55, 66)]
    assert message.reply_calls == 0


def test_topic_keyboards_show_item_counts_when_provided() -> None:
    topics = [
        SimpleNamespace(id="weather", title="Weather"),
        SimpleNamespace(id="school", title="School"),
    ]

    training_keyboard = _topic_keyboard(
        topics,
        topic_item_counts={"weather": 5, "school": 2},
    )
    editable_keyboard = _editable_topics_keyboard(
        topics,
        topic_item_counts={"weather": 5, "school": 2},
    )
    image_keyboard = _published_image_topics_keyboard(
        topics,
        topic_item_counts={"weather": 5, "school": 2},
    )

    assert training_keyboard.inline_keyboard[0][0].text == "Weather (5)"
    assert editable_keyboard.inline_keyboard[1][0].text == "School (2)"
    assert image_keyboard.inline_keyboard[0][0].text == "Weather (5)"


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


def test_published_image_items_keyboard_marks_items_with_attached_image() -> None:
    keyboard = _published_image_items_keyboard(
        topic_id="school-subjects",
        raw_items=[
            {
                "id": "school-subjects-maths",
                "english_word": "Mathematics",
                "translation": "математика",
                "image_ref": "assets/school-subjects/school-subjects-maths.png",
            },
            {
                "id": "school-subjects-science",
                "english_word": "Science",
                "translation": "естественные науки",
            },
        ],
    )

    assert keyboard.inline_keyboard[0][0].text == "* Mathematics — математика"
    assert keyboard.inline_keyboard[1][0].text == "Science — естественные науки"


def test_editable_words_keyboard_marks_items_with_attached_image() -> None:
    keyboard = _editable_words_keyboard(
        topic_id="school-subjects",
        words=[
            SimpleNamespace(
                english_word="Mathematics",
                translation="математика",
                has_image=True,
            ),
            SimpleNamespace(
                english_word="Science",
                translation="естественные науки",
                has_image=False,
            ),
        ],
    )

    assert keyboard.inline_keyboard[0][0].text == "* Mathematics — математика"
    assert keyboard.inline_keyboard[1][0].text == "Science — естественные науки"


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
    keyboard = _words_menu_keyboard(
        can_add_words=True,
        can_edit_words=True,
        can_edit_images=True,
        language="ru",
    )

    assert keyboard.inline_keyboard[0][0].text == "Темы тренировки"
    assert keyboard.inline_keyboard[1][0].text == "Добавить слова"
    assert keyboard.inline_keyboard[2][0].text == "Редактировать слова"
    assert keyboard.inline_keyboard[3][0].text == "Редактировать картинку слова"


def test_words_menu_keyboard_supports_granular_permissions() -> None:
    keyboard = _words_menu_keyboard(
        can_add_words=False,
        can_edit_words=True,
        can_edit_images=False,
    )

    assert [row[0].callback_data for row in keyboard.inline_keyboard] == [
        "words:topics",
        "words:edit_words",
    ]


def test_assign_menu_keyboard_shows_admin_buttons() -> None:
    keyboard = _assign_menu_keyboard(is_admin=True)

    assert [row[0].callback_data for row in keyboard.inline_keyboard] == [
        "assign:admin_assign_goal",
        "assign:goals",
        "assign:progress",
        "assign:users",
    ]


def test_start_menu_keyboard_exposes_personal_launch_actions() -> None:
    keyboard = _start_menu_keyboard(
        summary=[
            AssignmentLaunchView(
                kind=AssignmentSessionKind.DAILY,
                available=True,
                remaining_word_count=4,
                estimated_round_count=1,
            ),
            AssignmentLaunchView(
                kind=AssignmentSessionKind.WEEKLY,
                available=False,
                remaining_word_count=0,
                estimated_round_count=0,
            ),
            AssignmentLaunchView(
                kind=AssignmentSessionKind.HOMEWORK,
                available=True,
                remaining_word_count=6,
                estimated_round_count=2,
            ),
            AssignmentLaunchView(
                kind=AssignmentSessionKind.ALL,
                available=True,
                remaining_word_count=10,
                estimated_round_count=2,
            ),
        ]
    )

    assert [row[0].callback_data for row in keyboard.inline_keyboard] == [
        "start:game",
        "start:launch:daily",
        "start:disabled:weekly",
        "start:launch:homework",
        "start:launch:all",
    ]


def test_goal_flow_keyboards_include_back_navigation() -> None:
    assert _goal_setup_keyboard().inline_keyboard[-1][0].callback_data == "assign:menu"
    assert _goal_target_keyboard().inline_keyboard[-1][0].callback_data == "assign:goal_setup"
    assert _goal_source_keyboard().inline_keyboard[-1][0].callback_data == "assign:goal_target_menu"


def test_admin_goal_flow_keyboards_include_back_navigation() -> None:
    assert _admin_goal_period_keyboard().inline_keyboard[-1][0].callback_data == "assign:menu"
    assert _admin_goal_target_keyboard().inline_keyboard[-1][0].callback_data == "assign:admin_assign_goal"
    assert _admin_goal_source_keyboard().inline_keyboard[-1][0].callback_data == "assign:admin_goal_target_menu"


def test_admin_goal_manual_keyboard_shows_page_range_indicator() -> None:
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "content_store": SimpleNamespace(
                    list_all_vocabulary=lambda: [
                        SimpleNamespace(id=f"w{i}", english_word=f"Word {i}")
                        for i in range(1, 10)
                    ]
                )
            }
        ),
    )

    keyboard = _admin_goal_manual_keyboard(
        context=context,  # type: ignore[arg-type]
        user=SimpleNamespace(id=1),
        page=0,
    )

    assert any(button.text == "1-8 / 9" for row in keyboard.inline_keyboard for button in row)


def test_admin_goal_recipients_keyboard_shows_page_range_indicator() -> None:
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "telegram_menu_access_policy": TelegramMenuAccessPolicy.from_bot_data({"admin_user_ids": {1}}),
                "admin_users_progress_overview_use_case": SimpleNamespace(execute=lambda: []),
                "telegram_user_login_repository": SimpleNamespace(
                    list=lambda: [
                        SimpleNamespace(user_id=i, username=f"user{i}", last_seen_at="2026-03-29T00:00:00+00:00")
                        for i in range(2, 11)
                    ]
                ),
            }
        ),
    )

    keyboard = _admin_goal_recipients_keyboard(
        context=context,  # type: ignore[arg-type]
        user=SimpleNamespace(id=1, username="boss"),
        page=0,
    )

    assert any(button.text == "1-8 / 10" for row in keyboard.inline_keyboard for button in row)


def test_mode_keyboard_no_longer_contains_game_mode_entry() -> None:
    keyboard = _mode_keyboard("animals", None, language="en")

    assert len(keyboard.inline_keyboard) == 1
    assert [button.callback_data for button in keyboard.inline_keyboard[0]] == [
        "mode:animals:all:easy",
        "mode:animals:all:medium",
        "mode:animals:all:hard",
    ]


def test_assignment_round_complete_keyboard_offers_next_round_when_available() -> None:
    keyboard = _assignment_round_complete_keyboard(AssignmentSessionKind.ALL, has_more=True)

    assert [row[0].callback_data for row in keyboard.inline_keyboard] == [
        "start:launch:all",
        "assign:menu",
        "start:menu",
    ]


@pytest.mark.anyio
async def test_assign_menu_callback_handler_ignores_message_not_modified() -> None:
    query = _FakeQuery()
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123),
    )
    context = SimpleNamespace(application=SimpleNamespace(bot_data={}))

    await assign_menu_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True


@pytest.mark.anyio
async def test_admin_users_progress_callback_handler_limits_regular_user_to_self() -> None:
    query = _RecordingQuery()
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, username="me"),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "telegram_menu_access_policy": SimpleNamespace(roles_for_user=lambda user_id: ("user",)),
                "admin_users_progress_overview_use_case": SimpleNamespace(
                    execute=lambda: [
                        SimpleNamespace(
                            user_id=123,
                            active_goals_count=1,
                            completed_goals_count=2,
                            aggregate_percent=40,
                            last_activity_at=None,
                        ),
                        SimpleNamespace(
                            user_id=456,
                            active_goals_count=9,
                            completed_goals_count=9,
                            aggregate_percent=90,
                            last_activity_at=None,
                        ),
                    ]
                ),
                "telegram_user_login_repository": SimpleNamespace(
                    list=lambda: [
                        SimpleNamespace(user_id=123, username="me", last_seen_at="2026-03-29T00:00:00+00:00"),
                        SimpleNamespace(user_id=456, username="other", last_seen_at="2026-03-28T00:00:00+00:00"),
                    ]
                ),
            }
        ),
        user_data={},
    )

    await admin_users_progress_callback_handler(update, context)  # type: ignore[arg-type]

    assert "@me" in query.edits[-1][0]
    assert "@other" not in query.edits[-1][0]


@pytest.mark.anyio
async def test_assign_user_detail_callback_handler_shows_user_goals() -> None:
    query = _RecordingQuery()
    query.data = "assign:user:456"
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, username="boss"),
    )
    target = SimpleNamespace(
        user_id=456,
        username="student",
        roles=("user",),
        active_goals_count=1,
        completed_goals_count=0,
        aggregate_percent=40,
        last_activity_at=None,
        last_seen_at=None,
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "telegram_menu_access_policy": TelegramMenuAccessPolicy.from_bot_data({"admin_user_ids": {123}}),
                "admin_users_progress_overview_use_case": SimpleNamespace(
                    execute=lambda: [
                        SimpleNamespace(
                            user_id=456,
                            active_goals_count=1,
                            completed_goals_count=0,
                            aggregate_percent=40,
                            last_activity_at=None,
                        )
                    ]
                ),
                "telegram_user_login_repository": SimpleNamespace(
                    list=lambda: [SimpleNamespace(user_id=456, username="student", last_seen_at="2026-03-28T00:00:00+00:00")]
                ),
                "admin_user_goals_use_case": SimpleNamespace(
                    execute=lambda user_id, include_history=True: [
                        SimpleNamespace(
                            goal=SimpleNamespace(
                                id="g1",
                                goal_period=SimpleNamespace(value="homework"),
                                goal_type=SimpleNamespace(value="word_level_homework"),
                                progress_count=1,
                                target_count=2,
                                status=SimpleNamespace(value="active"),
                            ),
                            progress_percent=50,
                        )
                    ]
                ),
            }
        ),
        user_data={},
    )

    await assign_user_detail_callback_handler(update, context)  # type: ignore[arg-type]

    assert "student" in query.edits[-1][0]
    assert "Assignments:" in query.edits[-1][0]
    assert query.edits[-1][1].inline_keyboard[0][0].callback_data == "assign:goal:456:g1"


@pytest.mark.anyio
async def test_assign_goal_detail_callback_handler_shows_goal_words() -> None:
    query = _RecordingQuery()
    query.data = "assign:goal:456:g1"
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, username="boss"),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "admin_goal_detail_use_case": SimpleNamespace(
                    execute=lambda user_id, goal_id: SimpleNamespace(
                        goal=SimpleNamespace(
                            goal_period=SimpleNamespace(value="homework"),
                            goal_type=SimpleNamespace(value="word_level_homework"),
                            status=SimpleNamespace(value="active"),
                            progress_count=1,
                            target_count=2,
                        ),
                        progress_percent=50,
                        words=[
                            SimpleNamespace(
                                english_word="Cat",
                                translation="кот",
                                homework_mode=SimpleNamespace(value="easy"),
                                easy_mastered=False,
                                medium_mastered=False,
                                hard_mastered=False,
                                hard_skipped=False,
                            )
                        ],
                    )
                )
            }
        ),
        user_data={},
    )

    await assign_goal_detail_callback_handler(update, context)  # type: ignore[arg-type]

    assert "Words:" in query.edits[-1][0]
    assert "Cat" in query.edits[-1][0]
    assert query.edits[-1][1].inline_keyboard[0][0].callback_data == "assign:user:456"


@pytest.mark.anyio
async def test_start_assignment_round_callback_handler_starts_selected_round() -> None:
    query = _RecordingQuery()
    query.data = "start:launch:homework"
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "start_assignment_round_use_case": SimpleNamespace(
                    execute=lambda user_id, kind: SimpleNamespace(
                        session_id="s1",
                        item_id="cat",
                        mode=TrainingMode.MEDIUM,
                        prompt="Translation: кот",
                        image_ref=None,
                        correct_answer="Cat",
                        options=None,
                        input_hint="Type it",
                        letter_hint="a c t",
                    )
                )
            }
        ),
        user_data={},
    )

    async def _fake_send_question(update, ctx, question):  # noqa: ANN001
        query.edits.append((question.prompt, None))

    import englishbot.bot as bot_module

    original = bot_module._send_question
    bot_module._send_question = _fake_send_question
    try:
        await start_assignment_round_callback_handler(
            SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=123, language_code="en")),
            context,  # type: ignore[arg-type]
        )
    finally:
        bot_module._send_question = original

    assert query.edits[0][0] == "📘 Homework round started."
    assert query.edits[1][0] == "Translation: кот"


@pytest.mark.anyio
async def test_start_assignment_unavailable_callback_handler_shows_empty_message() -> None:
    query = _RecordingQuery()

    await start_assignment_unavailable_callback_handler(
        SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=123, language_code="en")),
        SimpleNamespace(application=SimpleNamespace(bot_data={}), user_data={}),  # type: ignore[arg-type]
    )

    assert query.edits[-1][0] == "No active assignments in this section right now."
    assert query.edits[-1][1].inline_keyboard[0][0].callback_data == "start:menu"


@pytest.mark.anyio
async def test_game_mode_placeholder_callback_handler_shows_stub_message() -> None:
    query = _RecordingQuery()

    await game_mode_placeholder_callback_handler(
        SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=123, language_code="en")),
        SimpleNamespace(application=SimpleNamespace(bot_data={}), user_data={}),  # type: ignore[arg-type]
    )

    assert query.edits[-1][0] == "🎮 Game mode is coming soon."
    assert query.edits[-1][1].inline_keyboard[0][0].callback_data == "start:menu"


def test_start_menu_keyboard_marks_unavailable_assignments() -> None:
    keyboard = _start_menu_keyboard(
        summary=[
            AssignmentLaunchView(AssignmentSessionKind.DAILY, True, 2, 1),
            AssignmentLaunchView(AssignmentSessionKind.WEEKLY, False, 0, 0),
            AssignmentLaunchView(AssignmentSessionKind.HOMEWORK, False, 0, 0),
            AssignmentLaunchView(AssignmentSessionKind.ALL, True, 4, 1),
        ]
    )

    assert keyboard.inline_keyboard[2][0].text.startswith("🚫")
    assert keyboard.inline_keyboard[2][0].callback_data == "start:disabled:weekly"


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
