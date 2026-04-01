from types import SimpleNamespace

import pytest
from telegram.error import BadRequest

from englishbot.application.homework_progress_use_cases import (
    AssignmentLaunchView,
    AssignmentSessionKind,
    GoalProgressView,
)
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
    _goal_list_keyboard,
    _image_review_markup,
    _image_review_keyboard,
    _published_image_topics_keyboard,
    _mode_keyboard,
    _start_menu_keyboard,
    _topic_keyboard,
    _published_image_items_keyboard,
    _words_menu_keyboard,
    _editable_topics_keyboard,
    _render_start_menu_text,
    game_mode_placeholder_callback_handler,
    mode_selected_handler,
    continue_session_handler,
    start_assignment_round_callback_handler,
    start_assignment_unavailable_callback_handler,
    words_add_words_callback_handler,
    words_goals_callback_handler,
    words_menu_handler,
    goal_setup_disabled_callback_handler,
    goal_text_handler,
    admin_users_progress_callback_handler,
    admin_goal_period_callback_handler,
    assign_menu_callback_handler,
    words_edit_images_callback_handler,
    words_menu_callback_handler,
    words_topics_callback_handler,
)
from englishbot.domain.models import Goal, GoalPeriod, GoalStatus, GoalType, TrainingMode


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
        self.message = SimpleNamespace(chat_id=1, message_id=10)

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, reply_markup=None) -> None:  # noqa: ARG002
        self.edits.append((text, reply_markup))


class _ModeSelectionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def start_session(
        self,
        *,
        user_id: int,
        topic_id: str,
        lesson_id: str | None,
        mode: TrainingMode,
        adaptive_per_word: bool = False,
    ):
        self.calls.append(
            {
                "user_id": user_id,
                "topic_id": topic_id,
                "lesson_id": lesson_id,
                "mode": mode,
                "adaptive_per_word": adaptive_per_word,
            }
        )
        return SimpleNamespace(
            session_id="session-1",
            item_id="word-1",
            mode=mode,
            prompt="Translation: cat",
            image_ref=None,
            correct_answer="cat",
            options=["cat", "dog", "sun"] if mode is TrainingMode.EASY else None,
            letter_hint=None,
        )


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
async def test_mode_selected_handler_keeps_explicit_selected_difficulty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_questions: list[object] = []

    async def _fake_send_question(update, context, question) -> None:  # noqa: ARG001
        sent_questions.append(question)

    monkeypatch.setattr("englishbot.bot._send_question", _fake_send_question)

    service = _ModeSelectionService()
    query = _RecordingQuery()
    query.data = "mode:weather:all:medium"
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, language_code="en"),
    )
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "training_service": service,
                "telegram_ui_language": "en",
            }
        ),
    )

    await mode_selected_handler(update, context)  # type: ignore[arg-type]

    assert service.calls == [
        {
            "user_id": 123,
            "topic_id": "weather",
            "lesson_id": None,
            "mode": TrainingMode.MEDIUM,
            "adaptive_per_word": False,
        }
    ]
    assert context.user_data["awaiting_text_answer"] is False
    assert query.edits[-1][0] == "Session started."
    assert len(sent_questions) == 1


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
async def test_words_menu_handler_sends_words_menu_and_chat_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_views: list[object] = []

    async def _fake_send_telegram_view(message, view):  # noqa: ARG001
        sent_views.append(view)

    monkeypatch.setattr("englishbot.bot.send_telegram_view", _fake_send_telegram_view)

    update = SimpleNamespace(
        effective_message=SimpleNamespace(),
        effective_user=SimpleNamespace(id=123, language_code="en"),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"editor_user_ids": set(), "admin_user_ids": set()}),
    )

    await words_menu_handler(update, context)  # type: ignore[arg-type]

    assert len(sent_views) == 2
    assert sent_views[0].text == "Words menu."
    assert sent_views[1].text == "Quick actions:"


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
                "learner_assignment_launch_summary_use_case": SimpleNamespace(
                    execute=lambda user_id: [
                        AssignmentLaunchView(
                            AssignmentSessionKind.HOMEWORK,
                            True,
                            4,
                            1,
                            total_word_count=10,
                            deadline_date="2026-04-07",
                        ),
                    ]
                ),
            }
        ),
        user_data={},
    )

    await words_goals_callback_handler(update, context)  # type: ignore[arg-type]

    assert "Correct: 7" in query.edits[-1][0]
    assert "What is left in your assignments now:" in query.edits[-1][0]
    assert "📘 Homework: 4/10 words left" in query.edits[-1][0]


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
                "learner_assignment_launch_summary_use_case": SimpleNamespace(execute=lambda user_id: []),
            }
        ),
        user_data={},
    )

    await words_goals_callback_handler(update, context)  # type: ignore[arg-type]

    assert query.answered is True


@pytest.mark.anyio
async def test_words_goals_callback_handler_shows_goal_rules_and_recently_completed() -> None:
    query = _RecordingQuery()
    active_goal = GoalProgressView(
        goal=Goal(
            id="g-active",
            user_id=123,
            goal_period=GoalPeriod.HOMEWORK,
            goal_type=GoalType.WORD_LEVEL_HOMEWORK,
            target_count=10,
            progress_count=3,
            status=GoalStatus.ACTIVE,
        ),
        progress_percent=30,
    )
    completed_goal = GoalProgressView(
        goal=Goal(
            id="g-done",
            user_id=123,
            goal_period=GoalPeriod.HOMEWORK,
            goal_type=GoalType.NEW_WORDS,
            target_count=10,
            progress_count=10,
            status=GoalStatus.COMPLETED,
        ),
        progress_percent=100,
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=123, language_code="en"),
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
                        active_goals=[active_goal],
                    )
                ),
                "list_user_goals_use_case": SimpleNamespace(
                    execute=lambda user_id, include_history=True: [completed_goal]
                ),
                "learner_assignment_launch_summary_use_case": SimpleNamespace(
                    execute=lambda user_id: [
                        AssignmentLaunchView(
                            AssignmentSessionKind.HOMEWORK,
                            True,
                            7,
                            2,
                            total_word_count=10,
                        )
                    ]
                ),
                "telegram_ui_language": "en",
            }
        ),
        user_data={},
    )

    await words_goals_callback_handler(update, context)  # type: ignore[arg-type]

    text = query.edits[-1][0]
    assert "Points are added on correct answers" in text
    assert "What is left in your assignments now:" in text
    assert "📘 Homework: 7/10 words left" in text
    assert "Counts when an assigned word reaches the homework target level." not in text
    assert "Recently completed:" not in text
    assert "• Homework/Words: 10/10 (100%)" not in text
    assert "Weekly/Words: 10/10 (100%)" not in text
    assert query.edits[-1][1].inline_keyboard[2][0].callback_data == "start:launch:homework"
    assert query.edits[-1][1].inline_keyboard[2][1].callback_data == "words:goal_reset:g-active"


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
async def test_goal_setup_disabled_callback_handler_returns_to_assignments_menu() -> None:
    query = _RecordingQuery()
    context = SimpleNamespace(user_data={"goal_period": "daily"}, application=SimpleNamespace(bot_data={}))

    await goal_setup_disabled_callback_handler(
        SimpleNamespace(
            callback_query=SimpleNamespace(
                answer=query.answer,
                edit_message_text=query.edit_message_text,
                data="words:goal_target:custom",
            ),
            effective_user=SimpleNamespace(id=123, language_code="en"),
        ),
        context,  # type: ignore[arg-type]
    )

    assert query.edits[-1][0] == "Self-managed goals are disabled. Ask an admin to assign work."
    assert "goal_period" not in context.user_data
    assert context.user_data["telegram_ui_language"] == "en"


@pytest.mark.anyio
async def test_goal_text_handler_disables_legacy_self_goal_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_views: list[object] = []

    async def _fake_send_telegram_view(message, view):  # noqa: ARG001
        sent_views.append(view)

    monkeypatch.setattr("englishbot.bot.send_telegram_view", _fake_send_telegram_view)

    context = SimpleNamespace(
        user_data={
            "words_flow_mode": "awaiting_goal_target_text",
            "expected_user_input_state": {"chat_id": 77, "message_id": 88},
        },
        application=SimpleNamespace(bot_data={}),
    )

    await goal_text_handler(
        SimpleNamespace(
            effective_message=SimpleNamespace(
                text="12",
                reply_text=lambda *args, **kwargs: None,
                chat_id=55,
                message_id=66,
            ),
            effective_user=SimpleNamespace(id=123, language_code="en"),
        ),
        context,  # type: ignore[arg-type]
    )

    assert len(sent_views) == 1
    assert sent_views[0].text == "Self-managed goals are disabled. Ask an admin to assign work."
    assert "words_flow_mode" not in context.user_data


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


def test_assign_menu_keyboard_exposes_assignment_guide_web_app() -> None:
    keyboard = _assign_menu_keyboard(
        is_admin=False,
        guide_web_app_url="https://admin.example.com/webapp/help?lang=en",
    )

    assert keyboard.inline_keyboard[-1][0].text == "📚 How it works"
    assert keyboard.inline_keyboard[-1][0].url == "https://admin.example.com/webapp/help?lang=en"


def test_start_menu_keyboard_exposes_personal_launch_actions() -> None:
    keyboard = _start_menu_keyboard(
        summary=[
            AssignmentLaunchView(
                kind=AssignmentSessionKind.HOMEWORK,
                available=True,
                remaining_word_count=6,
                estimated_round_count=2,
            ),
        ]
    )

    assert [row[0].callback_data for row in keyboard.inline_keyboard] == [
        "start:game",
        "start:launch:homework",
    ]


def test_start_menu_keyboard_exposes_assignment_guide_web_app() -> None:
    keyboard = _start_menu_keyboard(
        summary=[
            AssignmentLaunchView(AssignmentSessionKind.HOMEWORK, True, 6, 2),
        ],
        guide_web_app_url="https://admin.example.com/webapp/help?lang=en",
    )

    assert keyboard.inline_keyboard[-1][0].text == "📚 How it works"
    assert keyboard.inline_keyboard[-1][0].url == "https://admin.example.com/webapp/help?lang=en"


def test_render_start_menu_text_uses_assigned_status_for_available_assignments() -> None:
    text = _render_start_menu_text(
        context=SimpleNamespace(application=SimpleNamespace(bot_data={"telegram_ui_language": "en"})),
        user=SimpleNamespace(id=123, language_code="en"),
        summary=[
            AssignmentLaunchView(
                AssignmentSessionKind.HOMEWORK,
                True,
                6,
                2,
                deadline_date="2026-04-07",
            ),
        ],
    )

    assert "📘 Homework: assigned • 6 words • due 2026-04-07" in text


def test_goal_flow_keyboards_include_back_navigation() -> None:
    assert _goal_setup_keyboard().inline_keyboard[-1][0].callback_data == "assign:menu"
    assert _goal_target_keyboard().inline_keyboard[-1][0].callback_data == "assign:goal_setup"
    assert _goal_source_keyboard().inline_keyboard[-1][0].callback_data == "assign:goal_target_menu"


def test_admin_goal_flow_keyboards_include_back_navigation() -> None:
    assert _admin_goal_period_keyboard().inline_keyboard[-1][0].callback_data == "assign:menu"
    assert len(_admin_goal_period_keyboard().inline_keyboard) == 2
    assert _admin_goal_target_keyboard().inline_keyboard[-1][0].callback_data == "assign:admin_assign_goal"
    assert _admin_goal_source_keyboard().inline_keyboard[-1][0].callback_data == "assign:admin_assign_goal"


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


def test_assignment_round_complete_keyboard_can_hide_continue_button() -> None:
    keyboard = _assignment_round_complete_keyboard(
        AssignmentSessionKind.HOMEWORK,
        has_more=False,
        remaining_word_count=None,
        round_batch_size=None,
    )

    assert [row[0].callback_data for row in keyboard.inline_keyboard] == ["assign:menu", "start:menu"]


def test_goal_list_keyboard_shows_start_and_reset_per_goal() -> None:
    active_homework = GoalProgressView(
        goal=Goal(
            id="goal-homework",
            user_id=1,
            goal_period=GoalPeriod.HOMEWORK,
            goal_type=GoalType.WORD_LEVEL_HOMEWORK,
            target_count=10,
            progress_count=0,
            status=GoalStatus.ACTIVE,
        ),
        progress_percent=0,
    )

    keyboard = _goal_list_keyboard(goals=[active_homework], language="en")

    assert keyboard.inline_keyboard[0][0].callback_data == "assign:progress"
    assert keyboard.inline_keyboard[1][0].callback_data == "assign:menu"
    assert keyboard.inline_keyboard[2][0].text == "▶️ 1. Start"
    assert keyboard.inline_keyboard[2][0].callback_data == "start:launch:homework"
    assert keyboard.inline_keyboard[2][1].callback_data == "words:goal_reset:goal-homework"


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

    assert query.edits == [("Translation: кот", None)]


@pytest.mark.anyio
async def test_start_assignment_round_callback_handler_shows_empty_state_when_no_homework_words() -> None:
    query = _RecordingQuery()
    query.data = "start:launch:homework"

    await start_assignment_round_callback_handler(
        SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=123, language_code="en")),
        SimpleNamespace(
            application=SimpleNamespace(
                bot_data={
                    "start_assignment_round_use_case": SimpleNamespace(
                        execute=lambda user_id, kind: (_ for _ in ()).throw(ValueError("empty"))
                    )
                }
            ),
            user_data={},
        ),  # type: ignore[arg-type]
    )

    assert query.edits[-1][0] == "No active assignments in this section right now."


@pytest.mark.anyio
async def test_continue_session_handler_resends_assignment_progress_for_homework_session() -> None:
    query = _RecordingQuery()
    sent_progress: list[str] = []
    sent_questions: list[str] = []

    async def _fake_send_progress(context, *, message, user, kind, active_session=None):  # noqa: ANN001
        sent_progress.append(kind.value)

    async def _fake_send_question(update, context, question):  # noqa: ANN001
        sent_questions.append(question.prompt)

    import englishbot.bot as bot_module

    original_send_progress = bot_module._send_or_update_assignment_progress_message
    original_send_question = bot_module._send_question
    bot_module._send_or_update_assignment_progress_message = _fake_send_progress
    bot_module._send_question = _fake_send_question
    try:
        await continue_session_handler(
            SimpleNamespace(
                callback_query=query,
                effective_user=SimpleNamespace(id=123, language_code="en"),
            ),
            SimpleNamespace(
                application=SimpleNamespace(
                    bot_data={
                        "training_service": SimpleNamespace(
                            get_current_question=lambda user_id: SimpleNamespace(  # noqa: ARG005
                                session_id="s1",
                                item_id="cat",
                                mode=TrainingMode.MEDIUM,
                                prompt="Translation: кот",
                                image_ref=None,
                                correct_answer="Cat",
                                options=None,
                                input_hint=None,
                                letter_hint="a c t",
                            ),
                            get_active_session=lambda user_id: SimpleNamespace(  # noqa: ARG005
                                session_id="s1",
                                source_tag="assignment:homework:goal-1",
                                mode=TrainingMode.MEDIUM,
                                current_position=1,
                                total_items=5,
                            ),
                        )
                    }
                ),
                user_data={},
            ),  # type: ignore[arg-type]
        )
    finally:
        bot_module._send_or_update_assignment_progress_message = original_send_progress
        bot_module._send_question = original_send_question

    assert query.edits[0][0] == "Continuing your current session."
    assert sent_progress == ["homework"]
    assert sent_questions == ["Translation: кот"]


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
            AssignmentLaunchView(AssignmentSessionKind.HOMEWORK, False, 0, 0),
        ]
    )

    assert keyboard.inline_keyboard[1][0].text.startswith("🚫")
    assert keyboard.inline_keyboard[1][0].callback_data == "start:disabled:homework"


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
