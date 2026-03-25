from englishbot.domain.models import TrainingMode
from tests.support.training_scenarios import ScenarioDriver


def test_regular_user_starts_and_sees_topic_menu() -> None:
    scenario = ScenarioDriver().when_user_starts()

    assert scenario.screen.kind == "topic_menu"
    assert scenario.screen.text == "Choose a topic to start training."
    assert [action.label for action in scenario.screen.actions] == ["Weather", "Seasons"]


def test_user_selects_topic_with_lessons_and_sees_lesson_menu() -> None:
    scenario = ScenarioDriver().when_user_starts().when_user_chooses_topic("weather")

    assert scenario.screen.kind == "lesson_menu"
    assert scenario.screen.text == "Choose a lesson or train all words from the topic."
    assert [action.label for action in scenario.screen.actions] == [
        "All Topic Words",
        "Lesson 1",
        "Lesson 2",
    ]


def test_user_selects_topic_without_lessons_and_sees_mode_menu() -> None:
    scenario = ScenarioDriver().when_user_starts().when_user_chooses_topic("seasons")

    assert scenario.screen.kind == "mode_menu"
    assert scenario.screen.text == "Choose training mode."
    assert [action.label for action in scenario.screen.actions] == ["Easy", "Medium", "Hard"]


def test_user_starts_lesson_flow_and_gets_question_screen() -> None:
    scenario = (
        ScenarioDriver()
        .when_user_starts()
        .when_user_chooses_topic("weather")
        .when_user_chooses_lesson(topic_id="weather", lesson_id="lesson-1")
        .when_user_chooses_mode(
            topic_id="weather",
            lesson_id="lesson-1",
            mode=TrainingMode.HARD,
        )
    )

    assert scenario.screen.kind == "question"
    assert scenario.screen.expects_text_input is True
    assert "Type the English word." in scenario.screen.text


def test_user_completes_short_session_and_sees_summary() -> None:
    scenario = (
        ScenarioDriver()
        .when_user_starts()
        .when_user_chooses_topic("weather")
        .when_user_chooses_lesson(topic_id="weather", lesson_id="lesson-1")
        .when_user_chooses_mode(
            topic_id="weather",
            lesson_id="lesson-1",
            mode=TrainingMode.HARD,
        )
    )

    first_prompt = scenario.screen.text
    first_answer = "sun" if "солнце" in first_prompt else "rain"
    second_answer = "rain" if first_answer == "sun" else "sun"

    scenario.when_user_answers(first_answer).when_user_answers(second_answer)

    assert scenario.screen.kind == "summary"
    assert "Session completed." in scenario.screen.text
    assert "Correct: 2/2" in scenario.screen.text
