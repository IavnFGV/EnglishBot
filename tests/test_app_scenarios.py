from pathlib import Path

from englishbot.domain.models import TrainingMode
from tests.support.app_harness import AppHarness, build_import_draft


def test_learning_session_start_shows_topics_and_keeps_state_ready(tmp_path: Path) -> None:
    app = AppHarness(content_dir=tmp_path).when_user_starts_learning()

    assert app.screen is not None
    assert app.screen.kind == "topic_menu"
    assert app.screen.text == "Choose a topic to start training."
    assert [action.label for action in app.screen.actions] == ["Weather", "Seasons"]
    assert app.active_session_info() is None


def test_topic_selection_shows_lesson_list_with_all_words_option(tmp_path: Path) -> None:
    app = AppHarness(content_dir=tmp_path).when_user_starts_learning().when_user_selects_topic(
        "weather"
    )

    assert app.screen is not None
    assert app.screen.kind == "lesson_menu"
    assert [action.label for action in app.screen.actions] == [
        "All Topic Words",
        "Lesson 1",
        "Lesson 2",
    ]


def test_lesson_and_mode_selection_returns_first_question_and_active_session(
    tmp_path: Path,
) -> None:
    app = (
        AppHarness(content_dir=tmp_path)
        .when_user_starts_learning()
        .when_user_selects_topic("weather")
        .when_user_selects_lesson(topic_id="weather", lesson_id="lesson-1")
        .when_user_selects_mode(
            topic_id="weather",
            lesson_id="lesson-1",
            mode=TrainingMode.HARD,
        )
    )

    assert app.screen is not None
    assert app.screen.kind == "question"
    assert app.screen.expects_text_input is True
    assert "Type the English word." in app.screen.text
    active_session = app.active_session_info()
    assert active_session is not None
    assert active_session.topic_id == "weather"
    assert active_session.lesson_id == "lesson-1"
    assert active_session.current_position == 1


def test_answer_flow_handles_correct_and_incorrect_answers_until_summary(tmp_path: Path) -> None:
    app = (
        AppHarness(content_dir=tmp_path)
        .when_user_starts_learning()
        .when_user_selects_topic("weather")
        .when_user_selects_lesson(topic_id="weather", lesson_id="lesson-1")
        .when_user_selects_mode(
            topic_id="weather",
            lesson_id="lesson-1",
            mode=TrainingMode.HARD,
        )
    )

    assert app.screen is not None
    first_prompt = app.screen.text
    first_answer = "sun" if "солнце" in first_prompt else "rain"
    second_answer = "wrong answer"

    app.when_user_answers(first_answer).when_user_answers(second_answer)

    assert app.screen is not None
    assert app.screen.kind == "summary"
    assert "Session completed." in app.screen.text
    assert "Correct: 1/2" in app.screen.text
    assert "Incorrect: 1" in app.screen.text
    assert app.active_session_info() is None


def test_interrupted_session_is_cleared_safely_and_user_can_start_again(tmp_path: Path) -> None:
    app = (
        AppHarness(content_dir=tmp_path)
        .when_user_starts_learning()
        .when_user_selects_topic("weather")
        .when_user_selects_lesson(topic_id="weather", lesson_id="lesson-1")
        .when_user_selects_mode(
            topic_id="weather",
            lesson_id="lesson-1",
            mode=TrainingMode.MEDIUM,
        )
        .when_learning_is_interrupted()
        .when_user_starts_learning()
    )

    assert app.active_session_info() is None
    assert app.screen is not None
    assert app.screen.kind == "topic_menu"


def test_morning_review_trigger_returns_noop_when_nothing_is_due(tmp_path: Path) -> None:
    app = AppHarness(content_dir=tmp_path).when_morning_review_trigger_runs()

    assert app.review is not None
    assert app.review.kind == "noop"
    assert app.review.due_item_ids == ()


def test_morning_review_trigger_returns_proposal_when_due_items_exist(tmp_path: Path) -> None:
    app = (
        AppHarness(content_dir=tmp_path)
        .when_user_starts_learning()
        .when_user_selects_topic("weather")
        .when_user_selects_lesson(topic_id="weather", lesson_id="lesson-1")
        .when_user_selects_mode(
            topic_id="weather",
            lesson_id="lesson-1",
            mode=TrainingMode.HARD,
            session_size=1,
        )
    )
    assert app.screen is not None
    answer = "sun" if "солнце" in app.screen.text else "rain"

    app.when_user_answers(answer).when_morning_review_trigger_runs()
    assert app.review is not None
    assert app.review.kind == "noop"

    app.when_time_advances(hours=13).when_morning_review_trigger_runs()

    assert app.review is not None
    assert app.review.kind == "review_proposal"
    assert len(app.review.due_item_ids) == 1
    assert app.review.topic_ids == ("weather",)


def test_teacher_import_flow_can_be_confirmed_saved_and_reloaded_into_learning(
    tmp_path: Path,
) -> None:
    raw_text = "Fairy Tales\n\nPrincess / Prince — принцесса / принц"
    app = AppHarness(
        content_dir=tmp_path,
        import_drafts=[
            build_import_draft(
                topic_title="Fairy Tales",
                items=[("Princess", "принцесса"), ("Prince", "принц")],
            )
        ],
    )

    app.when_editor_imports_teacher_text(raw_text=raw_text)

    assert app.flow is not None
    assert app.flow.draft_result.validation.is_valid is True
    assert app.last_import_preview is not None
    assert "Draft preview" in app.last_import_preview
    assert "Princess — принцесса" in app.last_import_preview

    output_path = tmp_path / "fairy-tales.json"
    app.when_editor_approves_import(output_path=output_path)

    assert app.approval is not None
    assert output_path.exists()

    app.when_learning_content_is_reloaded().when_user_starts_learning().when_user_selects_topic(
        "fairy-tales"
    )

    assert app.screen is not None
    assert app.screen.kind == "mode_menu"
    assert [action.label for action in app.screen.actions] == ["Easy", "Medium", "Hard"]
